"""
gaming_intelligence: Multi-modal local intelligence layer for OpenShorts.
Enables fully local video understanding for gaming, podcasts, interviews, and streams
without reliance on external paid APIs.
"""

from .frame_sampler import FrameSampler
from .motion_detector import MotionDetector
from .scene_detector import SceneBoundaryDetector
from .audio_event_detector import AudioEventDetector
from .vision_analyzer import VisionAnalyzer
from .transcript_analyzer import TranscriptAnalyzer
from .event_scorer import EventScorer
from .clip_selector import ClipSelector
from .stream_recorder import StreamRecorder

__all__ = [
    "FrameSampler",
    "MotionDetector",
    "SceneBoundaryDetector",
    "AudioEventDetector",
    "VisionAnalyzer",
    "TranscriptAnalyzer",
    "EventScorer",
    "ClipSelector",
    "StreamRecorder",
]
