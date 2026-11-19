"""
content_classifier.py - Multi-Signal Content Intelligence Classifier for OpenShorts.

Evaluates multiple signals to categorize videos into specialized profiles:
  - 'gaming': High-action gameplay, chases, stunts, kills, fails, streaming reactions.
  - 'podcast': Conversations, interviews, talk shows, multi-speaker dialogue.
  - 'educational': Tutorials, explainers, coding, whiteboard, educational lectures.
  - 'commentary': Reaction videos, vlog, commentary, cultural/media review.
  - 'generic': General/multi-modal fallback.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

GAMING_KEYWORDS = {
    "gta", "gta5", "gta6", "grand theft auto", "gameplay", "playthrough",
    "walkthrough", "speedrun", "gaming", "stream", "streamer", "twitch",
    "esports", "fps", "fortnite", "minecraft", "valorant", "call of duty",
    "cod", "warzone", "roblox", "ps5", "xbox", "nintendo", "boss fight",
    "glitch", "kills", "stunt", "heist", "let's play", "lets play",
    "apex legends", "cyberpunk", "red dead", "rdr2", "cs2", "counter-strike",
    "league of legends", "dota", "overwatch", "elden ring", "dark souls",
    "zelda", "fifa", "nba 2k", "rocket league", "pubg", "clutch", "ace",
}

EDUCATIONAL_KEYWORDS = {
    "tutorial", "how to", "how-to", "learn", "guide", "course", "lecture",
    "explained", "explaining", "coding", "programming", "python", "javascript",
    "typescript", "react", "math", "mathematics", "science", "physics",
    "chemistry", "biology", "crash course", "lesson", "step by step",
    "step-by-step", "masterclass", "whiteboard", "deep dive", "documentation",
    "beginner guide", "full course",
}

PODCAST_KEYWORDS = {
    "podcast", "episode", "ep.", "interview", "interviewing", "interviews",
    "conversation", "discussion", "talk show", "roundtable", "debate",
    "dialogue", "show", "fireside", "q&a", "ama",
}

COMMENTARY_KEYWORDS = {
    "reaction", "reacts", "reacting", "commentary", "review", "reviewing",
    "critique", "vlog", "daily vlog", "my thoughts on", "drama", "tea",
    "breakdown", "unboxing",
}


def _tokenize(text: str) -> List[str]:
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    return [t.strip() for t in cleaned.split() if t.strip()]


def _match_keywords(text: str, kws: set) -> Tuple[float, List[str]]:
    matched = []
    score = 0.0
    for kw in kws:
        if " " in kw:
            if kw in text:
                score += 3.0
                matched.append(kw)
        else:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, text):
                score += 2.0
                matched.append(kw)
    return score, matched


def detect_content_type(
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    duration: float = 0.0,
    words_per_minute: Optional[float] = None,
    visual_motion_intensity: Optional[float] = None,
    audio_energy_spikes: Optional[int] = None,
    video_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Multi-signal content classification fusing metadata, transcript, visual, and audio evidence.

    Returns dict with keys:
      - 'primary_profile': 'gaming' | 'podcast' | 'educational' | 'commentary' | 'generic'
      - 'confidence': float (0.0 to 1.0)
      - 'alternatives': List[Dict[str, Any]]
      - 'evidence': List[str]
      - 'reason': str
      - 'profile': (backward-compatible alias of primary_profile)
    """
    scores = {
        "gaming": 0.0,
        "educational": 0.0,
        "podcast": 0.0,
        "commentary": 0.0,
    }
    evidence: List[str] = []

    # 1. Metadata analysis (Title, tags, category, description)
    cat_str = str(category or "").strip().lower()
    if cat_str in ("20", "gaming", "video games"):
        scores["gaming"] += 4.0
        evidence.append("YouTube category indicates Gaming")
    elif cat_str in ("27", "education", "educational"):
        scores["educational"] += 4.0
        evidence.append("YouTube category indicates Education")
    elif cat_str in ("28", "science & technology", "tech"):
        scores["educational"] += 2.0
        evidence.append("YouTube category indicates Tech/Education")
    elif cat_str in ("24", "entertainment"):
        scores["commentary"] += 1.0
        scores["gaming"] += 0.5

    title_text = str(title or "").lower()
    tag_text = " ".join([str(t).lower() for t in (tags or [])])
    desc_sample = str(description or "")[:500].lower()
    combined_text = f"{title_text} {tag_text} {desc_sample}"

    g_score, g_kws = _match_keywords(combined_text, GAMING_KEYWORDS)
    e_score, e_kws = _match_keywords(combined_text, EDUCATIONAL_KEYWORDS)
    p_score, p_kws = _match_keywords(combined_text, PODCAST_KEYWORDS)
    c_score, c_kws = _match_keywords(combined_text, COMMENTARY_KEYWORDS)

    if g_kws:
        scores["gaming"] += g_score
        evidence.append(f"Gaming keywords: {', '.join(g_kws[:3])}")
    if e_kws:
        scores["educational"] += e_score
        evidence.append(f"Educational keywords: {', '.join(e_kws[:3])}")
    if p_kws:
        scores["podcast"] += p_score
        evidence.append(f"Podcast keywords: {', '.join(p_kws[:3])}")
    if c_kws:
        scores["commentary"] += c_score
        evidence.append(f"Commentary keywords: {', '.join(c_kws[:3])}")

    # 2. Speech density heuristic
    if words_per_minute is not None:
        if words_per_minute < 35.0:
            scores["gaming"] += 2.5
            evidence.append(f"Low speech density ({words_per_minute:.1f} wpm) aligns with action/gameplay")
        elif words_per_minute > 130.0:
            scores["podcast"] += 1.5
            scores["educational"] += 1.0
            evidence.append(f"High speech density ({words_per_minute:.1f} wpm) aligns with dialogue/tutorial")

    # 3. Visual motion signal
    if visual_motion_intensity is not None:
        if visual_motion_intensity > 0.65:
            scores["gaming"] += 3.0
            evidence.append(f"High visual motion intensity ({visual_motion_intensity:.2f})")
        elif visual_motion_intensity < 0.25:
            scores["podcast"] += 1.5
            scores["educational"] += 1.0
            evidence.append(f"Low visual motion ({visual_motion_intensity:.2f}) aligns with talking head/slides")

    # 4. Audio energy peaks
    if audio_energy_spikes is not None:
        if audio_energy_spikes > 8:
            scores["gaming"] += 1.5
            evidence.append(f"Frequent audio energy spikes ({audio_energy_spikes})")
        elif audio_energy_spikes < 2:
            scores["educational"] += 1.0

    # 5. Video duration heuristics
    if duration > 1800:  # > 30 mins
        scores["podcast"] += 1.5
        scores["gaming"] += 0.5
        evidence.append("Long form duration (>30m)")

    # Sort profiles by score
    sorted_profiles = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_profile, best_score = sorted_profiles[0]

    # Calculate normalized confidence
    total_score = sum(scores.values())
    if best_score >= 2.0 and total_score > 0:
        confidence = min(0.98, max(0.60, best_score / (total_score + 1.0) + 0.35))
        alternatives = [
            {"type": p, "confidence": round(s / (total_score + 0.001), 2)}
            for p, s in sorted_profiles[1:] if s > 0
        ]
        reason = f"Multi-signal match for {best_profile} (score {best_score:.1f})"
    elif duration > 1800:
        best_profile = "podcast"
        confidence = 0.55
        alternatives = []
        reason = "Duration > 30m with low metadata; default to conversation"
    else:
        best_profile = "generic"
        confidence = 0.40
        alternatives = []
        reason = "Low signal confidence; falling back to generic profile"

    return {
        "primary_profile": best_profile,
        "profile": best_profile,  # Backward compatibility alias
        "confidence": round(confidence, 2),
        "alternatives": alternatives,
        "evidence": evidence,
        "reason": reason,
    }
