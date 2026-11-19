"""
intelligence/signals/audio_energy.py - Fast CPU-based audio RMS energy and excitement peak extractor.

Computes windowed loudness, dynamic range, and volume spikes from video or audio files
using FFmpeg raw PCM streaming into vectorized NumPy buffers.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


class AudioEnergyDetector:
    """Computes RMS loudness and excitement spikes without requiring heavy neural audio models."""

    def __init__(self, sample_rate: int = 16000, window_sec: float = 0.5):
        self.sample_rate = sample_rate
        self.window_sec = window_sec

    def analyze_audio(
        self,
        media_path: str,
        start_sec: float = 0.0,
        max_duration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Extracts mono 16-bit PCM and computes windowed RMS energy.
        """
        if not os.path.isfile(media_path):
            raise FileNotFoundError(f"Media file not found: {media_path}")

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
        ]
        if max_duration and max_duration > 0:
            ffmpeg_cmd.extend(["-t", str(max_duration)])
        ffmpeg_cmd.extend([
            "-i", media_path,
            "-vn",
            "-ac", "1",
            "-ar", str(self.sample_rate),
            "-f", "s16le",
            "-",
        ])

        samples_per_window = int(self.sample_rate * self.window_sec)
        bytes_per_window = samples_per_window * 2  # 16-bit = 2 bytes per sample

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10**7,
        )

        windows: List[Dict[str, Any]] = []
        current_time = start_sec

        try:
            while True:
                raw_bytes = proc.stdout.read(bytes_per_window)
                if not raw_bytes or len(raw_bytes) < 4:
                    break

                if np is not None:
                    samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    rms = float(np.sqrt(np.mean(samples**2)))
                else:
                    rms = 0.05

                windows.append({
                    "timestamp": round(current_time, 2),
                    "rms": round(rms, 4),
                })
                current_time += self.window_sec
        finally:
            proc.stdout.close()
            proc.wait()

        if not windows:
            return {
                "average_rms": 0.0,
                "max_rms": 0.0,
                "spike_count": 0,
                "windows": [],
            }

        rms_values = [w["rms"] for w in windows]
        avg_rms = sum(rms_values) / len(rms_values)
        max_rms = max(rms_values)

        # Spikes: windows whose RMS exceeds 2.2x the average and > 0.08
        spike_threshold = max(0.08, avg_rms * 2.2)
        spike_count = 0
        for w in windows:
            if w["rms"] >= spike_threshold:
                w["is_spike"] = True
                spike_count += 1
            else:
                w["is_spike"] = False

        return {
            "average_rms": round(avg_rms, 4),
            "max_rms": round(max_rms, 4),
            "spike_count": spike_count,
            "windows": windows,
        }
