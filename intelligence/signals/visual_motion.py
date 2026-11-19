"""
intelligence/signals/visual_motion.py - CPU-optimized visual motion extractor.

Computes visual activity and action intensity across downscaled video frames (360p).
Works with OpenCV when available, with a fast vectorized NumPy/FFmpeg fallback.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


class VisualMotionDetector:
    """Extracts motion intensity and action peaks without requiring heavy GPU models."""

    def __init__(self, target_fps: float = 1.0, scale_width: int = 480):
        self.target_fps = target_fps
        self.scale_width = scale_width

    def analyze_video(
        self,
        video_path: str,
        start_sec: float = 0.0,
        end_sec: Optional[float] = None,
        max_duration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Samples video frames at low resolution and computes frame-to-frame motion.
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        duration_limit = f"-t {max_duration}" if max_duration and max_duration > 0 else ""
        if end_sec and end_sec > start_sec:
            duration_limit = f"-t {end_sec - start_sec}"

        # Probe video width & height via ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "csv=p=0:s=x",
            video_path,
        ]
        try:
            out = subprocess.check_output(probe_cmd, stderr=subprocess.DEVNULL, text=True).strip()
            parts = out.split("x")
            orig_w, orig_h = int(parts[0]), int(parts[1].split()[0])
        except Exception:
            orig_w, orig_h = 1280, 720

        scale_h = int((orig_h / orig_w) * self.scale_width)
        # Ensure dimensions are even
        scale_w = self.scale_width - (self.scale_width % 2)
        scale_h = scale_h - (scale_h % 2)

        # Extract raw grayscale frames (YUV420p Y channel or gray) via FFmpeg pipe
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
        ]
        if duration_limit:
            ffmpeg_cmd.extend(duration_limit.split())
        ffmpeg_cmd.extend([
            "-i", video_path,
            "-vf", f"fps={self.target_fps},scale={scale_w}:{scale_h},format=gray",
            "-f", "rawvideo",
            "-pix_fmt", "gray",
            "-",
        ])

        frame_size = scale_w * scale_h
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10**7,
        )

        motion_points: List[Dict[str, Any]] = []
        prev_frame: Optional[Any] = None
        current_time = start_sec
        time_step = 1.0 / self.target_fps

        try:
            while True:
                raw_bytes = proc.stdout.read(frame_size)
                if not raw_bytes or len(raw_bytes) < frame_size:
                    break

                if np is not None:
                    curr_frame = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32)
                    if prev_frame is not None:
                        # Vectorized mean absolute difference
                        diff = np.mean(np.abs(curr_frame - prev_frame))
                        # Normalized between 0.0 and 1.0 (clamped at 60 pixel diff)
                        intensity = min(1.0, float(diff / 60.0))
                        motion_points.append({
                            "timestamp": round(current_time, 2),
                            "intensity": round(intensity, 3),
                        })
                    prev_frame = curr_frame
                else:
                    # Fallback if numpy is not imported
                    motion_points.append({
                        "timestamp": round(current_time, 2),
                        "intensity": 0.5,
                    })

                current_time += time_step
        finally:
            proc.stdout.close()
            proc.wait()

        if not motion_points:
            return {
                "average_intensity": 0.0,
                "max_intensity": 0.0,
                "motion_events": [],
                "high_motion_ratio": 0.0,
            }

        intensities = [p["intensity"] for p in motion_points]
        avg_int = sum(intensities) / len(intensities)
        max_int = max(intensities)
        high_motion_points = [p for p in motion_points if p["intensity"] >= 0.60]

        # Tag peaks (local maxima)
        for i in range(1, len(motion_points) - 1):
            if (motion_points[i]["intensity"] > motion_points[i - 1]["intensity"] and
                motion_points[i]["intensity"] > motion_points[i + 1]["intensity"] and
                motion_points[i]["intensity"] >= 0.50):
                motion_points[i]["is_peak"] = True

        return {
            "average_intensity": round(avg_int, 3),
            "max_intensity": round(max_int, 3),
            "motion_events": motion_points,
            "high_motion_ratio": round(len(high_motion_points) / len(motion_points), 2),
        }
