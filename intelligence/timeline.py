"""
intelligence/timeline.py - Unified millisecond timeline for multi-signal fusion.

Synchronizes visual motion, scene cuts, audio RMS/peaks, and transcript tokens
into a shared temporal structure for event reasoning and boundary optimization.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class TimelineEvent:
    start: float
    end: float
    event_type: str  # visual_motion | scene_cut | audio_peak | speech_token | gameplay_action | streamer_reaction
    intensity: float = 1.0  # 0.0 to 1.0
    label: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def overlaps(self, start: float, end: float) -> bool:
        return max(self.start, start) <= min(self.end, end)

    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TimelineEvent:
        return cls(
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            event_type=str(data.get("event_type", "unknown")),
            intensity=float(data.get("intensity", 1.0)),
            label=str(data.get("label", "")),
            metadata=dict(data.get("metadata") or {}),
        )


class UnifiedTimeline:
    """Manages multi-modal signals on a shared synchronized millisecond timeline."""

    def __init__(self, duration: float = 0.0):
        self.duration = float(duration)
        self.events: List[TimelineEvent] = []

    def add_event(
        self,
        start: float,
        end: float,
        event_type: str,
        intensity: float = 1.0,
        label: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimelineEvent:
        ev = TimelineEvent(
            start=round(float(start), 3),
            end=round(float(end), 3),
            event_type=str(event_type),
            intensity=round(float(intensity), 3),
            label=str(label),
            metadata=metadata or {},
        )
        self.events.append(ev)
        if ev.end > self.duration:
            self.duration = ev.end
        return ev

    def get_window(
        self,
        start: float,
        end: float,
        event_types: Optional[Set[str]] = None,
    ) -> List[TimelineEvent]:
        """Returns all events active within the [start, end] window."""
        res = []
        for ev in self.events:
            if event_types and ev.event_type not in event_types:
                continue
            if ev.overlaps(start, end):
                res.append(ev)
        return sorted(res, key=lambda e: e.start)

    def get_events_at(self, timestamp: float) -> List[TimelineEvent]:
        """Returns all events active at a single point in time."""
        return [ev for ev in self.events if ev.start <= timestamp <= ev.end]

    def find_peaks(
        self,
        event_type: Optional[str] = None,
        min_intensity: float = 0.6,
    ) -> List[TimelineEvent]:
        """Finds candidate high-energy event peaks."""
        peaks = [
            ev for ev in self.events
            if (not event_type or ev.event_type == event_type) and ev.intensity >= min_intensity
        ]
        return sorted(peaks, key=lambda e: e.intensity, reverse=True)

    def score_density(
        self,
        start: float,
        end: float,
        weights: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Calculates multi-signal fusion density for a given time window:
        S = sum(weight_i * intensity_i * duration_i) / window_duration
        """
        w = weights or {
            "visual_motion": 0.35,
            "gameplay_action": 0.30,
            "audio_peak": 0.20,
            "streamer_reaction": 0.15,
            "speech_token": 0.10,
        }
        window_dur = max(0.001, end - start)
        score = 0.0

        for ev in self.get_window(start, end):
            weight = w.get(ev.event_type, 0.05)
            # Portion of event overlapping this window
            overlap = max(0.0, min(ev.end, end) - max(ev.start, start))
            score += weight * ev.intensity * (overlap / window_dur)

        return min(1.0, score)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duration": round(self.duration, 3),
            "total_events": len(self.events),
            "events": [ev.to_dict() for ev in sorted(self.events, key=lambda e: e.start)],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UnifiedTimeline:
        tl = cls(duration=float(data.get("duration", 0.0)))
        for ev_data in data.get("events", []):
            tl.events.append(TimelineEvent.from_dict(ev_data))
        return tl
