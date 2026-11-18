"""
event_scorer.py - Multi-modal scoring engine: S = w_v*V + w_a*A + w_t*T + w_c*C
"""
from __future__ import annotations

import os
import yaml
from typing import Dict, List, Optional


class EventScorer:
    """Combines Visual, Audio, Transcript, and Context signals into weighted composite scores."""

    def __init__(self, profile_name: str = "gaming", custom_weights: Optional[Dict[str, float]] = None):
        self.profile_name = profile_name
        self.config = self._load_profile(profile_name)
        self.weights = custom_weights or self.config.get("weights", {
            "visual": 0.35,
            "audio": 0.35,
            "transcript": 0.20,
            "context": 0.10
        })

    def _load_profile(self, name: str) -> Dict[str, any]:
        base_dir = os.path.dirname(__file__)
        prof_path = os.path.join(base_dir, "profiles", f"{name}.yaml")
        if os.path.exists(prof_path):
            try:
                with open(prof_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        return {}

    def score_timeline(
        self,
        duration: float,
        step_sec: float = 1.0,
        motion_events: Optional[List[Dict[str, any]]] = None,
        audio_events: Optional[List[Dict[str, any]]] = None,
        transcript_events: Optional[List[Dict[str, any]]] = None,
        scene_cuts: Optional[List[Dict[str, any]]] = None,
    ) -> List[Dict[str, any]]:
        """
        Creates a uniform time-series score across the entire duration.
        """
        motion_map = {int(round(e["timestamp"])): e["motion_score"] for e in (motion_events or [])}
        audio_map = {int(round(e["timestamp"])): e["peak_score"] for e in (audio_events or [])}
        cut_set = {int(round(e["timestamp"])) for e in (scene_cuts or []) if e.get("is_cut")}

        # Transcript map covers interval [start, end]
        t_events = transcript_events or []

        timeline = []
        total_steps = int(duration // step_sec)

        wv = self.weights.get("visual", 0.35)
        wa = self.weights.get("audio", 0.35)
        wt = self.weights.get("transcript", 0.20)
        wc = self.weights.get("context", 0.10)

        for step in range(total_steps):
            sec = step * step_sec
            sec_int = int(round(sec))

            # Visual score V
            v_val = motion_map.get(sec_int, 0.0)

            # Audio score A
            a_val = audio_map.get(sec_int, 0.0)

            # Transcript score T
            t_val = 0.0
            t_hook = ""
            for te in t_events:
                if te["start"] <= sec <= te["end"]:
                    t_val = max(t_val, te.get("transcript_score", 0.0))
                    if not t_hook:
                        t_hook = te.get("hook", "")

            # Context score C: scene cut bonus, sudden pacing shift
            c_val = 0.15 if sec_int in cut_set else 0.05

            # If there is no speech (silent video / pure gameplay), re-weight dynamically
            if not t_events or max([te.get("transcript_score", 0) for te in t_events], default=0) < 0.1:
                norm_wv = wv / (wv + wa + wc)
                norm_wa = wa / (wv + wa + wc)
                norm_wc = wc / (wv + wa + wc)
                composite = (norm_wv * v_val) + (norm_wa * a_val) + (norm_wc * c_val)
            else:
                composite = (wv * v_val) + (wa * a_val) + (wt * t_val) + (wc * c_val)

            timeline.append({
                "timestamp": round(sec, 2),
                "composite_score": round(min(1.0, max(0.0, composite)), 4),
                "visual_score": round(v_val, 4),
                "audio_score": round(a_val, 4),
                "transcript_score": round(t_val, 4),
                "context_score": round(c_val, 4),
                "hook": t_hook
            })

        return timeline
