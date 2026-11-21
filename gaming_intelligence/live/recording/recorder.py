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
        url_refresher: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.buffer = buffer
        self.sync = sync
        self.segment_time_sec = segment_time_sec
        self.url_refresher = url_refresher
        self._process: Optional[subprocess.Popen] = None
        self._stderr_file = None
        self._watcher_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_detected_idx = -1
        self._stream_url: Optional[str] = None
        self._restart_count = 0
        self._last_healthy_segment_at = 0.0
        self._calibrated_sync = False

    def _spawn_ffmpeg(self, stream_url: str) -> subprocess.Popen:
        segment_pattern = os.path.join(self.buffer.buffer_dir, "seg_%05d.ts")
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        start_num = max(0, self._last_detected_idx + 1)
        input_opts = [
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "-fflags", "+nobuffer+genpts",
            "-rw_timeout", "10000000",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",
        ]
        u_lower = stream_url.lower()
        if "m3u8" in u_lower or "manifest" in u_lower:
            input_opts.extend(["-live_start_index", "-1"])
        cmd = [
            ffmpeg_bin, "-y", "-nostdin",
            *input_opts,
            "-i", stream_url,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(self.segment_time_sec),
            "-segment_format", "mpegts",
            "-segment_start_number", str(start_num),
            "-reset_timestamps", "1",
            segment_pattern
        ]
        logger.info(f"Starting FFmpeg segmented recording (start_num={start_num}): {' '.join(cmd[:6])}...")
        log_path = os.path.join(self.buffer.buffer_dir, "ffmpeg_recorder.log")
        if self._stderr_file:
            try:
                self._stderr_file.close()
            except OSError:
                pass
        self._stderr_file = open(log_path, "wb")
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=self._stderr_file)

    async def start_recording(self, stream_url: str):
        """Starts background FFmpeg process to record into rolling segments."""
        if self._running:
            return

        self._running = True
        self._stream_url = stream_url
        self._restart_count = 0
        self._process = self._spawn_ffmpeg(stream_url)
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
        if self._stderr_file:
            try:
                self._stderr_file.close()
            except OSError:
                pass
            self._stderr_file = None

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
                            now = time.time()
                            if not self._calibrated_sync:
                                self._calibrated_sync = True
                                self.sync.stream_start_wall_clock = now - (idx + 1) * self.segment_time_sec
                            if self._last_healthy_segment_at and (now - self._last_healthy_segment_at) < 30.0:
                                self._restart_count = 0
                            self._last_healthy_segment_at = now
                            start_t = idx * self.segment_time_sec
                            end_t = start_t + self.segment_time_sec
                            self.buffer.register_segment(idx, f, start_t, end_t)
                            self.buffer.clean_expired(end_t)
                    except ValueError:
                        continue

                if self._process and self._process.poll() is not None and self._running and self._stream_url:
                    self._restart_count += 1
                    delay = min(15.0, float(self._restart_count) * 1.5)
                    logger.warning(
                        f"FFmpeg segmenter exited (code={self._process.returncode}); "
                        f"restarting (attempt {self._restart_count}) in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    if self._running:
                        if self.url_refresher is not None:
                            try:
                                loop = asyncio.get_running_loop()
                                fresh_url = await loop.run_in_executor(None, self.url_refresher)
                                if fresh_url:
                                    self._stream_url = fresh_url
                            except Exception as ref_err:
                                logger.warning(f"Stream URL refresh failed: {ref_err}")
                        self._process = self._spawn_ffmpeg(self._stream_url)

                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error watching segments: {e}")
                await asyncio.sleep(1.0)
