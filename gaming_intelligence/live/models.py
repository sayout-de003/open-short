"""
models.py - Data models for ultra-low-latency live hype clipping.
Optimized with __slots__ for minimal memory allocation and O(1) performance.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class Platform(str, Enum):
    TWITCH = "twitch"
    YOUTUBE = "youtube"
    MOCK = "mock"


class ClipMode(str, Enum):
    INSTANT_PREVIEW = "instant_preview"  # Stage A fast remux (source aspect)
    AUTO_SHORT = "auto_short"            # Stage B 9:16 vertical render
    SMART_SHORT = "smart_short"          # Mode 3 with captions/AI title


@dataclass(slots=True)
class ChatMessage:
    timestamp: float          # Unix epoch seconds (float)
    user_id: str              # Platform unique user ID or username
    text: str                 # Message text
    platform: Platform        # Platform enum
    is_subscriber: bool = False
    bits_or_superchat: float = 0.0


@dataclass(slots=True)
class HypeMetrics:
    timestamp: float
    message_count: int
    velocity_mps: float       # Messages per second
    acceleration: float       # Rate of change in velocity
    unique_users: int         # Count of distinct users
    chant_density: float      # Ratio of hype/chant tokens to total tokens
    emote_density: float      # Ratio of emotes to total tokens
    caps_ratio: float         # Ratio of uppercase letters
    z_score: float            # Velocity Z-score against 60s baseline
    top_chants: List[str] = field(default_factory=list)


@dataclass(slots=True)
class HypeEvent:
    event_id: str
    detected_at: float        # Wall clock time when trigger fired
    event_timestamp: float    # Estimated on-stream occurrence time (adjusted for reaction delay)
    peak_velocity: float
    z_score: float
    top_chants: List[str]
    confidence: float = 1.0


@dataclass(slots=True)
class VideoSegment:
    segment_index: int
    filepath: str
    start_time: float         # Stream time (seconds)
    end_time: float           # Stream time (seconds)
    duration: float
    created_at: float         # Wall clock epoch


@dataclass(slots=True)
class LatencyMilestones:
    chat_received_at: float = 0.0
    hype_detected_at: float = 0.0
    pre_roll_pinned_at: float = 0.0
    post_roll_ready_at: float = 0.0
    extract_started_at: float = 0.0
    extract_completed_at: float = 0.0
    render_started_at: float = 0.0
    render_completed_at: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        det_lat = (self.hype_detected_at - self.chat_received_at) * 1000 if self.chat_received_at else 0
        pin_lat = (self.pre_roll_pinned_at - self.hype_detected_at) * 1000 if self.hype_detected_at else 0
        ext_lat = (self.extract_completed_at - self.extract_started_at) * 1000 if self.extract_started_at else 0
        ren_lat = (self.render_completed_at - self.render_started_at) * 1000 if self.render_started_at else 0
        total_time_to_clip = (self.render_completed_at - self.hype_detected_at) if self.hype_detected_at and self.render_completed_at else 0

        return {
            "detection_latency_ms": round(max(0.0, det_lat), 2),
            "pinning_latency_ms": round(max(0.0, pin_lat), 2),
            "extraction_latency_ms": round(max(0.0, ext_lat), 2),
            "render_latency_ms": round(max(0.0, ren_lat), 2),
            "total_time_to_clip_sec": round(max(0.0, total_time_to_clip), 2),
        }


@dataclass
class ClipJob:
    job_id: str
    event: HypeEvent
    clip_start_time: float    # Video stream start (e.g. T_event - 25s)
    clip_end_time: float      # Video stream end (e.g. T_event + 10s)
    mode: ClipMode = ClipMode.AUTO_SHORT
    pinned_segments: List[str] = field(default_factory=list)
    draft_path: Optional[str] = None
    final_path: Optional[str] = None
    status: str = "pending"   # pending, waiting_postroll, extracting, rendering, complete, failed
    error: Optional[str] = None
    milestones: LatencyMilestones = field(default_factory=LatencyMilestones)
