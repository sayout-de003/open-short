"""
scene_detector.py - Scene transitions and shot boundary detection.
"""
from __future__ import annotations

import cv2
import numpy as np
from typing import List, Tuple, Dict


class SceneBoundaryDetector:
    """Detects scene cuts, fast cuts, and shot transitions via histogram correlation."""

    def __init__(self, cut_threshold: float = 0.55):
        self.cut_threshold = cut_threshold

    def detect_cuts(
        self, sampled_frames: List[Tuple[float, np.ndarray]]
    ) -> List[Dict[str, float]]:
        """
        Calculates correlation distance between successive frames.
        Returns list of cut candidates with timestamps and transition scores.
        """
        cuts = []
        if len(sampled_frames) < 2:
            return cuts

        prev_hist = None

        for ts, frame in sampled_frames:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)

            if prev_hist is not None:
                # Compare histograms using correlation (1 = identical, -1 = complete change)
                similarity = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                transition_score = max(0.0, 1.0 - max(0.0, similarity))

                is_cut = similarity < self.cut_threshold
                cuts.append({
                    "timestamp": round(ts, 2),
                    "transition_score": round(transition_score, 4),
                    "is_cut": bool(is_cut)
                })

            prev_hist = hist

        return cuts
