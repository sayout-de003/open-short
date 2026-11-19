"""
intelligence/signals - CPU-optimized multi-modal signal extraction module.
"""
from .visual_motion import VisualMotionDetector
from .audio_energy import AudioEnergyDetector

__all__ = ["VisualMotionDetector", "AudioEnergyDetector"]
