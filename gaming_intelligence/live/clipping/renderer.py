"""
renderer.py - Stage B: High-speed hardware-accelerated 9:16 vertical short renderer.
Automatically uses VideoToolbox (Mac), NVENC (NVIDIA), or ultrafast libx264 (CPU).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional

logger = logging.getLogger("live.renderer")


def detect_best_encoder(ffmpeg_bin: str) -> List[str]:
    """Detects available hardware-accelerated H.264 encoder in priority order."""
    try:
        res = subprocess.run(
            [ffmpeg_bin, "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        output = res.stdout.lower()

        # 1. macOS VideoToolbox
        if sys.platform == "darwin" and "h264_videotoolbox" in output:
            return ["-c:v", "h264_videotoolbox", "-b:v", "6000k"]

        # 2. Linux / Windows NVIDIA NVENC
        if "h264_nvenc" in output:
            return ["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll", "-b:v", "6000k"]

    except Exception:
        pass

    # 3. CPU Ultrafast fallback
    return ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-crf", "22"]


class FastVerticalRenderer:
    """Encodes draft clips into 1080x1920 9:16 vertical shorts in under 5 seconds."""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.ffmpeg_bin = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
        self.encoder_args = detect_best_encoder(self.ffmpeg_bin)
        logger.info(f"Video Encoder selected for Stage B: {' '.join(self.encoder_args)}")

    def render_vertical_short(
        self,
        draft_video_path: str,
        output_filename: str,
        target_duration: Optional[float] = None,
    ) -> str:
        """
        Takes the draft video and applies 9:16 vertical cropping/scaling.
        Returns the absolute path to the rendered 9:16 Short MP4.
        """
        if not os.path.exists(draft_video_path):
            raise FileNotFoundError(f"Draft video not found: {draft_video_path}")

        final_path = os.path.join(self.output_dir, output_filename)

        # 9:16 Crop filter: center gameplay crop to 1080x1920
        # crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2
        vf_filter = (
            "crop=ih*9/16:ih:(iw-ow)/2:0,"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        )

        cmd = [
            self.ffmpeg_bin, "-y", "-nostdin",
            "-i", draft_video_path,
        ]

        if target_duration:
            cmd.extend(["-t", str(target_duration)])

        cmd.extend([
            "-vf", vf_filter,
            *self.encoder_args,
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            final_path
        ])

        t0 = time.time()
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        elapsed = time.time() - t0

        if res.returncode != 0 or not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
            err_msg = res.stderr.decode("utf-8", errors="replace")[-500:]
            raise RuntimeError(f"Stage B vertical rendering failed: {err_msg}")

        logger.info(f"🚀 [Stage B] 9:16 Vertical Short rendered in {elapsed:.3f}s: {final_path} ({os.path.getsize(final_path) / 1024:.1f} KB)")
        return final_path
