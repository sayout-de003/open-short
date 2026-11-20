"""
pipeline.py - Master Live Hype Auto-Clipping Pipeline.
Coordinates chat listeners, O(1) hype detector, segmented recorder, and two-stage rendering with p50/p95 latency metrics.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional

from .chat.twitch import TwitchChatListener
from .chat.youtube import YouTubeChatListener
from .clipping.extractor import FastClipExtractor
from .clipping.renderer import FastVerticalRenderer
from .clipping.scheduler import ClipScheduler
from .detection.hype import FastHypeDetector
from .models import ChatMessage, ClipJob, HypeEvent, Platform
from .recording.buffer import RollingSegmentBuffer
from .recording.recorder import SegmentedStreamRecorder
from .recording.timestamps import TimestampSynchronizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("live.pipeline")


class LiveHypePipeline:
    """Master pipeline executing ultra-low-latency chat-driven live video clipping."""

    def __init__(
        self,
        buffer_dir: str = "/tmp/openshorts_live_buffer",
        output_dir: str = "output/live_shorts",
        pre_roll_sec: float = 25.0,
        post_roll_sec: float = 10.0,
    ):
        self.buffer_dir = buffer_dir
        self.output_dir = output_dir
        self.pre_roll_sec = pre_roll_sec
        self.post_roll_sec = post_roll_sec

        os.makedirs(self.buffer_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        self.sync = TimestampSynchronizer()
        self.buffer = RollingSegmentBuffer(self.buffer_dir)
        self.recorder = SegmentedStreamRecorder(self.buffer, self.sync)
        self.extractor = FastClipExtractor(self.output_dir)
        self.renderer = FastVerticalRenderer(self.output_dir)

        # Completed jobs history for latency metrics
        self.completed_jobs: List[ClipJob] = []

        self.scheduler = ClipScheduler(
            buffer=self.buffer,
            sync=self.sync,
            extractor=self.extractor,
            renderer=self.renderer,
            pre_roll_sec=self.pre_roll_sec,
            post_roll_sec=self.post_roll_sec,
            on_clip_ready=self._on_clip_ready,
        )

        self.detector = FastHypeDetector(
            on_hype_event=self.scheduler.on_hype_event
        )

        self.twitch_listener: Optional[TwitchChatListener] = None
        self.youtube_listener: Optional[YouTubeChatListener] = None

    def ingest_message(self, msg: ChatMessage):
        """Hot path message ingestion entry point."""
        self.detector.add_message(msg)

    def _on_clip_ready(self, job: ClipJob):
        self.completed_jobs.append(job)
        m = job.milestones.to_dict()
        print(f"\n✨ [CLIP GENERATED] Job: {job.job_id}")
        print(f"   🎬 Short MP4: {job.final_path}")
        print(f"   📊 Stage Latencies (ms): Extraction: {m['extraction_latency_ms']}ms | Render: {m['render_latency_ms']}ms")
        print(f"   ⏱️ Total Time to Short: {m['total_time_to_clip_sec']}s (Includes {self.post_roll_sec}s physical post-roll)\n")

    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Calculates p50 and p95 latency percentiles across completed jobs."""
        if not self.completed_jobs:
            return {}

        def _percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            data_sorted = sorted(data)
            k = (len(data_sorted) - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return round(data_sorted[int(k)], 2)
            d0 = data_sorted[int(f)] * (c - k)
            d1 = data_sorted[int(c)] * (k - f)
            return round(d0 + d1, 2)

        metrics = ["extraction_latency_ms", "render_latency_ms", "total_time_to_clip_sec"]
        stats = {}
        for m in metrics:
            vals = [j.milestones.to_dict()[m] for j in self.completed_jobs if j.milestones.to_dict().get(m) is not None]
            stats[m] = {
                "p50": _percentile(vals, 0.50),
                "p95": _percentile(vals, 0.95),
                "count": len(vals),
            }
        return stats

    async def start_twitch(self, channel: str, stream_url: Optional[str] = None):
        """Starts live monitoring on a Twitch channel."""
        logger.info(f"Starting Twitch live pipeline on channel: #{channel}")
        if stream_url:
            await self.recorder.start_recording(stream_url)

        self.twitch_listener = TwitchChatListener(channel, on_message=self.ingest_message)
        await self.twitch_listener.start()

    @staticmethod
    def _resolve_youtube_stream_url_sync(video_id_or_url: str) -> Optional[str]:
        yt_dlp = shutil.which("yt-dlp")
        if not yt_dlp:
            return None
        target = video_id_or_url.strip()
        if "youtu" not in target:
            target = f"https://www.youtube.com/watch?v={target}"
        try:
            res = subprocess.run(
                [yt_dlp, "-g", target],
                capture_output=True, text=True, timeout=20,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().splitlines()[0]
        except Exception as e:
            logger.warning(f"Could not resolve YouTube live stream URL via yt-dlp: {e}")
        return None

    async def start_youtube(self, video_id_or_url: str, stream_url: Optional[str] = None, api_key: Optional[str] = None):
        """Starts live monitoring on a YouTube live stream."""
        logger.info(f"Starting YouTube live pipeline on: {video_id_or_url}")
        if not stream_url:
            loop = asyncio.get_running_loop()
            stream_url = await loop.run_in_executor(
                None, lambda: self._resolve_youtube_stream_url_sync(video_id_or_url)
            )
        if stream_url:
            await self.recorder.start_recording(stream_url)

        self.youtube_listener = YouTubeChatListener(
            video_id_or_url,
            on_message=self.ingest_message,
            api_key=api_key
        )
        await self.youtube_listener.start()

    async def stop(self):
        """Gracefully shuts down all listeners and recorder."""
        if self.twitch_listener:
            await self.twitch_listener.stop()
        if self.youtube_listener:
            await self.youtube_listener.stop()
        await self.recorder.stop_recording()
        self.scheduler.close()
        logger.info("Live Hype Pipeline stopped.")
