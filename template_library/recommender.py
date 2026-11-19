"""
template_library/recommender.py - Intelligent Template Recommendation Engine.

Selects the best editing template based on detected content profile, specific events,
webcam presence, speaker count, and platform aspect ratio.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from template_library.models import get_template_store


def recommend_template(
    content_profile: str,
    event_category: Optional[str] = None,
    has_webcam: bool = False,
    speaker_count: int = 1,
    aspect_ratio: str = "9:16",
    duration: float = 30.0,
) -> Dict[str, Any]:
    """
    Selects the optimal template matching content characteristics.

    Returns:
      {
        "recommended_template_id": str,
        "template": Dict[str, Any],
        "confidence": float,
        "reason": str,
        "alternatives": List[str]
      }
    """
    store = get_template_store()
    prof = str(content_profile or "generic").lower().strip()
    ev = str(event_category or "").lower().strip()

    recommended_id = "gaming_cinematic"
    confidence = 0.85
    reason = "Default standard template"
    alternatives = []

    if prof in ("gaming", "gameplay", "action"):
        if has_webcam:
            recommended_id = "streamer_stacked_top"
            confidence = 0.95
            reason = "Streamer webcam detected: optimized with top-cam vertical stacked layout"
            alternatives = ["streamer_reaction", "gaming_meme", "gaming_cinematic"]
        elif ev in ("unexpected_fail", "fail", "glitch"):
            recommended_id = "gaming_fails"
            confidence = 0.92
            reason = "Gaming fail detected: freeze frame and record scratch effects"
            alternatives = ["gaming_meme", "gaming_cinematic"]
        elif ev in ("skill_clutch", "combat", "kills"):
            recommended_id = "esports_highlights"
            confidence = 0.90
            reason = "High-skill combat/clutch moment: fast cuts and score indicators"
            alternatives = ["gaming_cinematic", "streamer_stacked_top"]
        elif ev in ("gta", "story", "heist"):
            recommended_id = "gta_story"
            confidence = 0.91
            reason = "Atmospheric narrative gaming sequence: cinematic subtitles & letterbox"
            alternatives = ["gaming_cinematic"]
        else:
            recommended_id = "gaming_cinematic"
            confidence = 0.88
            reason = "Action-dense gameplay sequence: center viewport focus & impact cuts"
            alternatives = ["streamer_stacked_top", "esports_highlights"]

    elif prof in ("podcast", "interview", "talk"):
        if speaker_count >= 2:
            recommended_id = "podcast_split"
            confidence = 0.94
            reason = "Multi-speaker dialogue detected: two-way split screen with name tags"
            alternatives = ["podcast_kinetic", "podcast_cinematic"]
        elif ev in ("controversial", "debate", "opinion"):
            recommended_id = "controversial_opinion"
            confidence = 0.91
            reason = "Strong opinion detected: dramatic hook headline banner"
            alternatives = ["podcast_kinetic", "podcast_cinematic"]
        else:
            recommended_id = "podcast_kinetic"
            confidence = 0.90
            reason = "Focused monologue/interview: word-by-word karaoke typography"
            alternatives = ["podcast_cinematic", "podcast_reaction"]

    elif prof in ("educational", "tutorial", "code", "explainer"):
        if ev in ("code", "programming", "developer") or "code" in ev:
            recommended_id = "code_tutorial"
            confidence = 0.96
            reason = "Code screen recording detected: viewport zoom & syntax callouts"
            alternatives = ["edu_explainer", "step_by_step"]
        elif ev in ("step_by_step", "steps", "list"):
            recommended_id = "step_by_step"
            confidence = 0.93
            reason = "Sequential instructional steps: progress badges & checklist"
            alternatives = ["edu_explainer", "whiteboard"]
        elif ev in ("whiteboard", "math", "diagram"):
            recommended_id = "whiteboard"
            confidence = 0.92
            reason = "Whiteboard explanation: draw reveal & pen tracker highlights"
            alternatives = ["edu_explainer"]
        else:
            recommended_id = "edu_explainer"
            confidence = 0.89
            reason = "General educational explainer: structured bullet points & progress bar"
            alternatives = ["step_by_step", "code_tutorial"]

    elif prof in ("commentary", "vlog", "reaction"):
        if ev in ("reaction", "punch", "funny"):
            recommended_id = "reaction_punch"
            confidence = 0.92
            reason = "Expressive reaction moment: dynamic snap zooms and popup emojis"
            alternatives = ["story_vlog", "lifestyle_minimal"]
        elif ev in ("news", "review", "headline"):
            recommended_id = "commentary_news"
            confidence = 0.90
            reason = "Media commentary & review: lower-third headline overlays"
            alternatives = ["story_vlog", "reaction_punch"]
        else:
            recommended_id = "story_vlog"
            confidence = 0.88
            reason = "Narrative vlog flow: warm modern subtitles & film dissolves"
            alternatives = ["lifestyle_minimal", "reaction_punch"]

    elif prof in ("fitness", "workout", "sports"):
        recommended_id = "fitness_intense" if ev != "highlight" else "sports_highlight"
        confidence = 0.90
        reason = f"Athletic motion detected: {recommended_id.replace('_', ' ')} layout"
        alternatives = ["sports_highlight" if recommended_id == "fitness_intense" else "fitness_intense"]

    elif prof in ("business", "finance"):
        recommended_id = "business_premium"
        confidence = 0.89
        reason = "Business & executive presentation: clean corporate motion typography"
        alternatives = ["business_explainer"]

    elif prof in ("music", "dance"):
        recommended_id = "music_visualizer" if ev != "dance" else "dance_beat_sync"
        confidence = 0.90
        reason = "Music & rhythm content: beat-synchronized graphics"
        alternatives = ["dance_beat_sync"]

    elif prof in ("news", "documentary"):
        recommended_id = "news_bulletin"
        confidence = 0.90
        reason = "News format: breaking ticker & live broadcast graphics"
        alternatives = ["mini_documentary"]

    # Fetch full template object from registry
    template_obj = store.get_template(recommended_id) or store.get_template("gaming_cinematic")

    return {
        "recommended_template_id": recommended_id,
        "template": template_obj,
        "confidence": confidence,
        "reason": reason,
        "alternatives": alternatives,
    }
