"""
recorder.py - FFmpeg segmented live stream recorder.
Captures incoming stream into lightweight 2-second segments and notifies the buffer.
"""
from __future__ import annotations

import asyncio
import glob
import logging
import os
import shutil
import subprocess
import time
from typing import Callable, Optional
from .buffer import RollingSegmentBuffer
from .timestamps import TimestampSynchronizer

logger = logging.getLogger("live.recorder")


class SegmentedStreamRecorder:
    """Records live video into 2-second segments using FFmpeg segment muxer."""

    def __init__(
        self,
        buffer: RollingSegmentBuffer,
        sync: TimestampSynchronizer,
        segment_time_sec: float = 2.0,
    ):
        self.buffer = buffer
        self.sync = sync
        self.segment_time_sec = segment_time_sec
        self._process: Optional[subprocess.Popen] = None
        self._watcher_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_detected_idx = -1

    async def start_recording(self, stream_url: str):
        """Starts background FFmpeg process to record into rolling segments."""
        if self._running:
            return

        self._running = True
        segment_pattern = os.path.join(self.buffer.buffer_dir, "seg_%05d.ts")

        # Check ffmpeg binary
        ffmpeg_bin = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

        # FFmpeg segmented capture command with low-latency segmenting
        cmd = [
            ffmpeg_bin, "-y", "-nostdin",
            "-i", stream_url,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(self.segment_time_sec),
            "-segment_format", "mpegts",
            "-reset_timestamps", "1",
            segment_pattern
        ]

        logger.info(f"Starting FFmpeg segmented recording: {' '.join(cmd[:6])}...")
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        self._watcher_task = asyncio.create_task(self._watch_segments_loop())

    async def stop_recording(self):
        self._running = False
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    async def _watch_segments_loop(self):
        """Monitors the buffer directory for finished segments and registers them."""
        while self._running:
            try:
                pattern = os.path.join(self.buffer.buffer_dir, "seg_*.ts")
                files = sorted(glob.glob(pattern))

                # Note: The newest file might still be actively writing, so we register all except the very newest
                # unless process is stopped.
                ready_files = files[:-1] if len(files) > 1 else []

                for f in ready_files:
                    try:
                        filename = os.path.basename(f)
                        num_str = filename.replace("seg_", "").replace(".ts", "")
                        idx = int(num_str)
                        if idx > self._last_detected_idx:
                            self._last_detected_idx = idx
                            start_t = idx * self.segment_time_sec
                            end_t = start_t + self.segment_time_sec
                            self.buffer.register_segment(idx, f, start_t, end_t)
                            self.buffer.clean_expired(end_t)
                    except ValueError:
                        continue

                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error watching segments: {e}")
                await asyncio.sleep(1.0)
