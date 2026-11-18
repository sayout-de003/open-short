"""
stream_recorder.py - Live capture and segment management for Twitch and YouTube live streams.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Optional, Generator


class StreamRecorder:
    """Manages stream recording and segmented chunk capture from Twitch and YouTube."""

    def __init__(self, output_dir: str = "/tmp/openshorts_streams"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def capture_twitch_stream(
        self, channel_url: str, duration_sec: int = 120, output_name: Optional[str] = None
    ) -> str:
        """
        Captures a live Twitch stream for `duration_sec` using streamlink.
        """
        output_file = os.path.join(
            self.output_dir, output_name or f"twitch_{int(time.time())}.mp4"
        )
        # Check if streamlink is installed
        if not shutil.which("streamlink"):
            raise RuntimeError("streamlink is not installed on the system.")

        cmd = [
            "streamlink",
            channel_url,
            "best",
            "-O"
        ]
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-i", "pipe:0",
            "-t", str(duration_sec),
            "-c", "copy",
            output_file
        ]

        p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        p2 = subprocess.Popen(ffmpeg_cmd, stdin=p1.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p1.stdout.close()
        p2.communicate()

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            raise RuntimeError(f"Failed to record Twitch stream: {channel_url}")

        return output_file

    def capture_youtube_live(
        self, live_url: str, duration_sec: int = 120, output_name: Optional[str] = None
    ) -> str:
        """
        Captures a YouTube live stream using yt-dlp.
        """
        output_file = os.path.join(
            self.output_dir, output_name or f"yt_live_{int(time.time())}.mp4"
        )
        if not shutil.which("yt-dlp"):
            raise RuntimeError("yt-dlp is not installed on the system.")

        cmd = [
            "yt-dlp",
            "--live-from-start",
            "-f", "bv*+ba/b",
            "--merge-output-format", "mp4",
            "-o", output_file,
            live_url
        ]
        # Run with timeout
        try:
            subprocess.run(cmd, timeout=duration_sec + 30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            pass

        if not os.path.exists(output_file):
            raise RuntimeError(f"Failed to capture YouTube live stream: {live_url}")

        return output_file
