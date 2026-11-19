"""
content_classifier.py - Intelligent content-type classifier for OpenShorts.

Categorizes videos into specialized profiles:
  - 'gaming': High-action gameplay, chases, stunts, kills, fails, streaming reactions.
  - 'podcast': Conversations, interviews, talk shows, multi-speaker dialogue.
  - 'educational': Tutorials, explainers, coding, whiteboard, educational lectures.
  - 'commentary': Reaction videos, vlog, commentary, cultural/media review.
  - 'generic': General/multi-modal fallback.
"""
from __future__ import annotations

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
    """Extract lowercased alphanumeric tokens and multi-word phrases."""
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    return [t.strip() for t in cleaned.split() if t.strip()]


def detect_content_type(
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    duration: float = 0.0,
    words_per_minute: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Detects the content profile from metadata and signals.

    Returns dict with keys:
      - 'profile': 'gaming' | 'podcast' | 'educational' | 'commentary' | 'generic'
      - 'confidence': float (0.0 to 1.0)
      - 'reason': brief explanation
    """
    scores = {
        "gaming": 0.0,
        "educational": 0.0,
        "podcast": 0.0,
        "commentary": 0.0,
    }

    # 1. YouTube Category IDs / Names
    cat_str = str(category or "").strip().lower()
    if cat_str in ("20", "gaming", "video games"):
        scores["gaming"] += 4.0
    elif cat_str in ("27", "education", "educational"):
        scores["educational"] += 4.0
    elif cat_str in ("28", "science & technology", "tech"):
        scores["educational"] += 2.0
    elif cat_str in ("24", "entertainment"):
        scores["commentary"] += 1.0
        scores["gaming"] += 0.5

    # 2. Text Search (Title is weighted highest, followed by tags and description)
    title_text = str(title or "").lower()
    tag_text = " ".join([str(t).lower() for t in (tags or [])])
    desc_sample = str(description or "")[:500].lower()
    combined_text = f"{title_text} {tag_text} {desc_sample}"

    def match_keywords(kws: set) -> float:
        score = 0.0
        for kw in kws:
            if " " in kw:
                if kw in title_text:
                    score += 3.0
                elif kw in combined_text:
                    score += 1.5
            else:
                # Word-boundary check
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, title_text):
                    score += 2.5
                elif re.search(pattern, combined_text):
                    score += 1.0
        return score

    scores["gaming"] += match_keywords(GAMING_KEYWORDS)
    scores["educational"] += match_keywords(EDUCATIONAL_KEYWORDS)
    scores["podcast"] += match_keywords(PODCAST_KEYWORDS)
    scores["commentary"] += match_keywords(COMMENTARY_KEYWORDS)

    # 3. Speech density heuristic
    if words_per_minute is not None:
        if words_per_minute < 35.0:
            # Very sparse speech strongly correlates with gameplay, sports, or silent action
            scores["gaming"] += 2.0
        elif words_per_minute > 130.0:
            # High speech rate correlates with podcasts, commentaries, or lectures
            scores["podcast"] += 1.0
            scores["educational"] += 1.0

    # Pick highest scoring
    best_profile, best_score = max(scores.items(), key=lambda item: item[1])

    if best_score >= 2.0:
        confidence = min(0.98, 0.55 + (best_score * 0.08))
        return {
            "profile": best_profile,
            "confidence": round(confidence, 2),
            "reason": f"Matched {best_profile} keywords/category (score {best_score:.1f})",
        }

    # Default fallback when ambiguous:
    # If duration > 30 mins, likely podcast/stream; if shorter and low metadata, generic
    if duration > 1800:
        return {
            "profile": "podcast",
            "confidence": 0.50,
            "reason": "Duration > 30m with low metadata; default to conversation",
        }

    return {
        "profile": "generic",
        "confidence": 0.40,
        "reason": "Ambiguous metadata; default to multi-modal generic",
    }
