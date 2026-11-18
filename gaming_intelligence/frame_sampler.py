"""
frame_sampler.py - Memory-safe frame extraction and downsampling.
"""
from __future__ import annotations

import os
import subprocess
import cv2
import numpy as np
from typing import Generator, Tuple, Optional, List


class FrameSampler:
    """Samples video frames at controlled intervals (e.g., 1 frame per second)."""

    def __init__(self, target_fps: float = 1.0, max_dimension: int = 480):
        self.target_fps = target_fps
        self.max_dimension = max_dimension

    def sample_generator(
        self, video_path: str, start_sec: float = 0.0, end_sec: Optional[float] = None
    ) -> Generator[Tuple[float, np.ndarray], None, None]:
        """
        Yields (timestamp_sec, resized_frame_bgr) sequentially.
        Does not keep all frames in RAM.
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open video: {video_path}")

        try:
            native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = total_frames / native_fps if native_fps > 0 else 0.0

            if end_sec is None or end_sec > duration:
                end_sec = duration

            frame_interval = max(1, int(round(native_fps / self.target_fps)))
            current_frame_idx = 0

            if start_sec > 0:
                cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)
                current_frame_idx = int(start_sec * native_fps)

            while cap.isOpened():
                pts_sec = current_frame_idx / native_fps
                if end_sec and pts_sec > end_sec:
                    break

                if current_frame_idx % frame_interval == 0:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    h, w = frame.shape[:2]
                    if max(h, w) > self.max_dimension:
                        scale = self.max_dimension / float(max(h, w))
                        new_w, new_h = int(w * scale), int(h * scale)
                        frame_resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    else:
                        frame_resized = frame

                    yield (pts_sec, frame_resized)
                else:
                    if not cap.grab():
                        break

                current_frame_idx += 1
        finally:
            cap.release()

    def extract_key_frames(
        self, video_path: str, timestamps: List[float], output_dir: str
    ) -> List[Tuple[float, str]]:
        """Extract specific keyframe timestamps to disk for Vision AI inspection."""
        os.makedirs(output_dir, exist_ok=True)
        results = []
        cap = cv2.VideoCapture(video_path)
        try:
            for idx, ts in enumerate(timestamps):
                cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, ts * 1000.0))
                ret, frame = cap.read()
                if ret and frame is not None:
                    out_path = os.path.join(output_dir, f"frame_{idx:04d}_{ts:.2f}s.jpg")
                    # Resize to efficient 360p or 480p for vision LLM
                    h, w = frame.shape[:2]
                    scale = min(1.0, 480 / max(h, w))
                    if scale < 1.0:
                        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                    cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    results.append((ts, out_path))
        finally:
            cap.release()
        return results
