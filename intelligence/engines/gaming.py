"""
intelligence/engines/gaming.py - Gameplay Event Intelligence Engine & Boundary Optimizer.

Understands gaming narratives (Setup -> Climax -> Payoff), classifies events across
vehicle chases, combat, skill clutches, and fails, and selects optimal vertical templates.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from intelligence.timeline import TimelineEvent, UnifiedTimeline


class GamingEventCategory:
    VEHICLE_ACTION = "vehicle_action"     # Chases, jumps, drifts, crashes
    COMBAT = "combat"                     # Gunfights, kills, explosions, snipes
    SKILL_CLUTCH = "skill_clutch"         # 1vX, boss fight, perfect execution
    UNEXPECTED_FAIL = "unexpected_fail"   # Glitches, wipeouts, funny deaths
    STREAMER_REACTION = "streamer_reaction"  # Screaming, hype, laughing
    EXPLORATION = "exploration"           # Heists, discoveries, reveals


@dataclass
class GameplayCandidate:
    candidate_id: str
    start: float
    end: float
    duration: float
    category: str
    score: float
    setup_start: float
    climax_start: float
    payoff_end: float
    recommended_template: str
    recommended_layout: str
    has_webcam: bool
    summary: str
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GamingIntelligenceEngine:
    """Detects complete gameplay sequences and maps them to vertical short edit plans."""

    def __init__(
        self,
        min_clip_sec: float = 15.0,
        max_clip_sec: float = 60.0,
        target_clip_count: int = 5,
    ):
        self.min_clip_sec = min_clip_sec
        self.max_clip_sec = max_clip_sec
        self.target_clip_count = target_clip_count

    def analyze_timeline(
        self,
        timeline: UnifiedTimeline,
        has_streamer_webcam: bool = False,
    ) -> List[GameplayCandidate]:
        """
        Scans unified timeline for action peaks, computes Setup -> Climax -> Payoff boundaries,
        scores candidates, and assigns recommended template.
        """
        # Find visual motion peaks and audio/gameplay spikes
        motion_peaks = timeline.find_peaks("visual_motion", min_intensity=0.55)
        audio_peaks = timeline.find_peaks("audio_peak", min_intensity=0.60)
        all_peaks = sorted(motion_peaks + audio_peaks, key=lambda e: e.intensity, reverse=True)

        if not all_peaks and timeline.duration > self.min_clip_sec:
            # Fallback evenly spaced windows if no distinct peak
            step = max(self.min_clip_sec, timeline.duration / max(1, self.target_clip_count))
            curr = 0.0
            idx = 1
            candidates = []
            while curr + self.min_clip_sec <= timeline.duration and len(candidates) < self.target_clip_count:
                end = min(timeline.duration, curr + 30.0)
                candidates.append(GameplayCandidate(
                    candidate_id=f"gaming_clip_{idx:02d}",
                    start=round(curr, 2),
                    end=round(end, 2),
                    duration=round(end - curr, 2),
                    category=GamingEventCategory.VEHICLE_ACTION,
                    score=0.65,
                    setup_start=round(curr, 2),
                    climax_start=round(curr + (end - curr) * 0.5, 2),
                    payoff_end=round(end, 2),
                    recommended_template="streamer_stacked_top" if has_streamer_webcam else "gaming_cinematic",
                    recommended_layout="stacked_top_cam" if has_streamer_webcam else "gameplay_center",
                    has_webcam=has_streamer_webcam,
                    summary="Continuous gameplay sequence",
                    evidence=["Spaced gameplay window"],
                ))
                curr += step
                idx += 1
            return candidates

        raw_candidates: List[GameplayCandidate] = []
        selected_ranges: List[Tuple[float, float]] = []

        for idx, peak in enumerate(all_peaks):
            peak_time = (peak.start + peak.end) / 2.0

            # Suppress overlapping peaks within 10 seconds of already chosen clip
            if any(start - 5.0 <= peak_time <= end + 5.0 for start, end in selected_ranges):
                continue

            # Determine complete narrative boundaries
            setup_dur = 4.0   # Setup before climax
            payoff_dur = 6.0  # Payoff after climax
            clip_start = max(0.0, peak_time - setup_dur)
            clip_end = min(timeline.duration, peak_time + payoff_dur)

            # Ensure min duration
            if (clip_end - clip_start) < self.min_clip_sec:
                needed = self.min_clip_sec - (clip_end - clip_start)
                clip_start = max(0.0, clip_start - (needed / 2.0))
                clip_end = min(timeline.duration, clip_start + self.min_clip_sec)

            # Clamp to max duration
            if (clip_end - clip_start) > self.max_clip_sec:
                clip_end = clip_start + self.max_clip_sec

            clip_dur = clip_end - clip_start
            window_events = timeline.get_window(clip_start, clip_end)

            # Classify event category based on signals
            category, cat_score, evidence = self._classify_event(window_events, peak)

            # Template recommendation
            if has_streamer_webcam:
                # User preference: Top 1/4th streamer webcam, bottom gameplay
                rec_template = "streamer_stacked_top"
                rec_layout = "stacked_top_cam"
            elif category == GamingEventCategory.UNEXPECTED_FAIL:
                rec_template = "gaming_fails"
                rec_layout = "gameplay_center"
            else:
                rec_template = "gaming_cinematic"
                rec_layout = "gameplay_center"

            cand = GameplayCandidate(
                candidate_id=f"gaming_clip_{len(raw_candidates) + 1:02d}",
                start=round(clip_start, 2),
                end=round(clip_end, 2),
                duration=round(clip_dur, 2),
                category=category,
                score=round(cat_score, 2),
                setup_start=round(clip_start, 2),
                climax_start=round(peak_time, 2),
                payoff_end=round(clip_end, 2),
                recommended_template=rec_template,
                recommended_layout=rec_layout,
                has_webcam=has_streamer_webcam,
                summary=f"High-energy {category.replace('_', ' ')} sequence",
                evidence=evidence,
            )
            raw_candidates.append(cand)
            selected_ranges.append((clip_start, clip_end))

            if len(raw_candidates) >= self.target_clip_count:
                break

        # Backfill if target count was not reached and timeline has space
        if len(raw_candidates) < self.target_clip_count and timeline.duration > self.min_clip_sec:
            selected_ranges.sort(key=lambda x: x[0])
            gaps = []
            prev_end = 0.0
            for r_start, r_end in selected_ranges:
                if r_start - prev_end >= self.min_clip_sec:
                    gaps.append((prev_end, r_start))
                prev_end = max(prev_end, r_end)
            if timeline.duration - prev_end >= self.min_clip_sec:
                gaps.append((prev_end, timeline.duration))

            for g_start, g_end in gaps:
                if len(raw_candidates) >= self.target_clip_count:
                    break
                clip_dur = min(self.max_clip_sec, g_end - g_start)
                clip_start = round(g_start, 2)
                clip_end = round(g_start + clip_dur, 2)
                pk_time = round((clip_start + clip_end) / 2.0, 2)
                raw_candidates.append(GameplayCandidate(
                    candidate_id=f"gaming_clip_{len(raw_candidates) + 1:02d}",
                    start=clip_start,
                    end=clip_end,
                    duration=round(clip_dur, 2),
                    category=GamingEventCategory.VEHICLE_ACTION,
                    score=0.70,
                    setup_start=clip_start,
                    climax_start=pk_time,
                    payoff_end=clip_end,
                    recommended_template="streamer_stacked_top" if has_streamer_webcam else "gaming_cinematic",
                    recommended_layout="stacked_top_cam" if has_streamer_webcam else "gameplay_center",
                    has_webcam=has_streamer_webcam,
                    summary="High-energy gameplay sequence",
                    evidence=["Adaptive timeline fill moment"],
                ))
                selected_ranges.append((clip_start, clip_end))

        return sorted(raw_candidates, key=lambda c: c.score, reverse=True)

    def _classify_event(
        self,
        events: List[TimelineEvent],
        peak_event: TimelineEvent,
    ) -> Tuple[str, float, List[str]]:
        evidence = []
        motion_events = [e for e in events if e.event_type == "visual_motion"]
        audio_events = [e for e in events if e.event_type == "audio_peak"]
        speech_events = [e for e in events if e.event_type == "speech_token"]

        max_motion = max([e.intensity for e in motion_events], default=0.0)
        max_audio = max([e.intensity for e in audio_events], default=0.0)

        # Baseline score: 50% motion + 30% audio + 20% completeness
        score = (max_motion * 0.50) + (max_audio * 0.30) + 0.20
        evidence.append(f"Peak motion intensity: {max_motion:.2f}")

        if max_audio > 0.70:
            evidence.append(f"Audio impact peak: {max_audio:.2f}")

        # Distinguish category
        if max_motion >= 0.75 and max_audio <= 0.40:
            # Silent stunt or fast chase
            category = GamingEventCategory.VEHICLE_ACTION
            evidence.append("High visual speed with calm/music audio (Vehicle chase/stunt)")
            score = max(score, 0.88)
        elif max_audio >= 0.75 and max_motion >= 0.60:
            # Combat explosion or clutch
            category = GamingEventCategory.COMBAT
            evidence.append("Synchronized visual & audio impact peak (Combat/Explosion)")
            score = max(score, 0.92)
        elif any("fail" in str(e.metadata).lower() or "wasted" in str(e.metadata).lower() for e in events):
            category = GamingEventCategory.UNEXPECTED_FAIL
            evidence.append("Unexpected fail indicator detected")
            score = max(score, 0.85)
        else:
            category = GamingEventCategory.VEHICLE_ACTION

        return category, min(0.99, score), evidence
