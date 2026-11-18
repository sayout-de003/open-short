"""
motion_detector.py - Quantifies visual action, camera speed, stunts, and combat motion.
"""
from __future__ import annotations

import cv2
import numpy as np
from typing import List, Tuple, Dict


class MotionDetector:
    """Computes motion scores across consecutive sampled frames."""

    def __init__(self, blur_kernel: Tuple[int, int] = (21, 21), threshold_val: int = 25):
        self.blur_kernel = blur_kernel
        self.threshold_val = threshold_val

    def analyze_frames(
        self, sampled_frames: List[Tuple[float, np.ndarray]]
    ) -> List[Dict[str, float]]:
        """
        Takes list of (timestamp, bgr_frame).
        Returns list of {'timestamp': ts, 'motion_score': score, 'delta_norm': val}.
        """
        results = []
        if not sampled_frames:
            return results

        prev_gray = None
        raw_scores = []

        for ts, frame in sampled_frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, self.blur_kernel, 0)

            if prev_gray is None:
                motion_val = 0.0
            else:
                frame_diff = cv2.absdiff(prev_gray, gray)
                _, thresh = cv2.threshold(frame_diff, self.threshold_val, 255, cv2.THRESH_BINARY)
                total_pixels = thresh.shape[0] * thresh.shape[1]
                motion_pixels = cv2.countNonZero(thresh)
                motion_val = float(motion_pixels) / float(total_pixels) if total_pixels > 0 else 0.0

            raw_scores.append((ts, motion_val))
            prev_gray = gray

        # Normalize scores to 0.0 - 1.0 based on distribution
        values = [v for _, v in raw_scores]
        max_val = max(values) if values else 1.0
        if max_val < 1e-5:
            max_val = 1.0

        for ts, val in raw_scores:
            normalized = min(1.0, val / max_val)
            results.append({
                "timestamp": round(ts, 2),
                "motion_score": round(normalized, 4),
                "raw_motion": round(val, 4)
            })

        return results
