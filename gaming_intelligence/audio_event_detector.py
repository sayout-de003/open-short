"""
audio_event_detector.py - Audio activity, peak energy, shouting, explosions, and silence detection.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import numpy as np
from typing import List, Dict, Optional


class AudioEventDetector:
    """Analyzes audio energy and spikes from video files."""

    def __init__(self, sample_rate: int = 16000, window_sec: float = 1.0):
        self.sample_rate = sample_rate
        self.window_sec = window_sec

    def analyze_audio(self, video_path: str) -> List[Dict[str, float]]:
        """
        Extracts mono PCM audio and computes RMS energy per window.
        Returns list of {'timestamp': ts, 'rms_energy': rms, 'peak_score': norm_score}.
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as raw_file:
            raw_path = raw_file.name

        try:
            # Extract mono 16-bit 16kHz raw PCM using ffmpeg
            cmd = [
                "ffmpeg", "-y", "-nostdin",
                "-i", video_path,
                "-vn", "-ac", "1", "-ar", str(self.sample_rate),
                "-f", "s16le",
                raw_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode != 0 or not os.path.exists(raw_path) or os.path.getsize(raw_path) == 0:
                # No audio track or extraction failed
                return []

            # Read PCM samples
            data = np.fromfile(raw_path, dtype=np.int16).astype(np.float32)
            if len(data) == 0:
                return []

            # Compute RMS per window
            samples_per_window = int(self.sample_rate * self.window_sec)
            num_windows = int(len(data) // samples_per_window)

            results = []
            rms_list = []

            for i in range(num_windows):
                segment = data[i * samples_per_window : (i + 1) * samples_per_window]
                rms = float(np.sqrt(np.mean(segment ** 2)))
                rms_list.append(rms)

            if not rms_list:
                return []

            max_rms = max(rms_list) if rms_list else 1.0
            if max_rms < 1.0:
                max_rms = 1.0

            # Dynamic thresholding based on 80th percentile
            p80 = float(np.percentile(rms_list, 80))

            for i, rms in enumerate(rms_list):
                ts = i * self.window_sec
                # Peak score normalized, with boost for exceeding p80
                base_norm = min(1.0, rms / max_rms)
                is_spike = rms > p80
                peak_boost = 1.2 if is_spike else 1.0
                peak_score = min(1.0, base_norm * peak_boost)

                results.append({
                    "timestamp": round(ts, 2),
                    "rms_energy": round(rms, 2),
                    "peak_score": round(peak_score, 4),
                    "is_spike": bool(is_spike)
                })

            return results
        finally:
            if os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except Exception:
                    pass
