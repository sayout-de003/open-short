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
    def _test_encoder(enc: str) -> bool:
        try:
            r = subprocess.run(
                [ffmpeg_bin, "-y", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.05", "-c:v", enc, "-f", "null", "-"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return r.returncode == 0
        except Exception:
            return False

    try:
        # 1. macOS VideoToolbox
        if sys.platform == "darwin" and _test_encoder("h264_videotoolbox"):
            return ["-c:v", "h264_videotoolbox", "-b:v", "6000k"]

        # 2. Linux / Windows NVIDIA NVENC
        if _test_encoder("h264_nvenc"):
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
        self.ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
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

        # Check if webcam inset is detected for 20% Top Streamer + 80% Gameplay stacked layout
        inset_box = None
        orig_w, orig_h = 1920, 1080
        try:
            import camera_inset
            import cv2
            cap = cv2.VideoCapture(draft_video_path)
            if cap.isOpened():
                orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
                orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
                cap.release()
            inset_box = camera_inset.detect(draft_video_path)
        except Exception as e:
            logger.debug(f"Fast camera inset detection skipped: {e}")

        cmd = [
            self.ffmpeg_bin, "-y", "-nostdin",
            "-i", draft_video_path,
        ]

        if target_duration:
            cmd.extend(["-t", str(target_duration)])

        if inset_box:
            graph = camera_inset.inset_filtergraph(
                orig_w, orig_h, 1080, 1920, inset_box,
                camera_ratio=0.20, cam_position="top",
                add_divider=True, fill_screen=True
            )
            cmd.extend([
                "-filter_complex", graph,
                "-map", "[v]",
                "-map", "0:a?",
                *self.encoder_args,
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                final_path
            ])
        else:
            # Fallback 9:16 Crop filter: center gameplay crop to 1080x1920
            vf_filter = (
                "crop=ih*9/16:ih:(iw-ow)/2:0,"
                "scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
            )
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
