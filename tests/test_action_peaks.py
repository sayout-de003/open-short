"""Unit tests for multi-modal gameplay action peak extraction and fusion."""
import os
import pytest
from clip_selection import extract_action_peaks, fuse_action_peaks_into_windows


def test_fuse_action_peaks_into_windows_basic():
    windows = [
        {"id": "w1", "start": 0.0, "end": 60.0, "text": "driving in los santos"},
        {"id": "w2", "start": 60.0, "end": 120.0, "text": "car chase ramp jump crash"},
        {"id": "w3", "start": 120.0, "end": 180.0, "text": "talking to character"},
    ]

    action_peaks = [
        {"start": 75.0, "end": 90.0, "intensity": 0.92, "type": "action_climax"},
        {"start": 95.0, "end": 105.0, "intensity": 0.78, "type": "motion_peak"},
    ]

    fused = fuse_action_peaks_into_windows(windows, action_peaks)

    # w1 has no overlap
    assert fused[0]["action_intensity"] == 0.0
    assert fused[0]["action_moments"] == []

    # w2 has both peaks
    assert fused[1]["action_intensity"] == 0.92
    assert len(fused[1]["action_moments"]) == 2
    assert fused[1]["action_moments"][0]["type"] == "action_climax"

    # w3 has no overlap
    assert fused[2]["action_intensity"] == 0.0
    assert fused[2]["action_moments"] == []


def test_fuse_action_peaks_empty():
    assert fuse_action_peaks_into_windows([], []) == []
    windows = [{"id": "w1", "start": 0.0, "end": 30.0}]
    fused = fuse_action_peaks_into_windows(windows, None)
    assert fused[0]["action_intensity"] == 0.0
    assert fused[0]["action_moments"] == []


def test_extract_action_peaks_nonexistent_file():
    peaks = extract_action_peaks("nonexistent_video_path_123.mp4", duration=60.0)
    assert peaks == []


def test_gaming_prompts_format():
    import gemini_worker
    score_p = gemini_worker.GAMING_SCORE_PROMPT_TEMPLATE.format(
        video_duration=120,
        language="en",
        windows_json='[{"id": "w1"}]'
    )
    assert "GAMING SELECTION CRITERIA" in score_p
    assert "HIGH ACTION & STUNTS" in score_p
    assert "120" in score_p

    detail_p = gemini_worker.GAMING_DETAIL_PROMPT_TEMPLATE.format(
        video_duration=120,
        language="en",
        min_clips=2,
        max_clips=5,
        min_secs=15.0,
        max_secs=60.0,
        windows_json='[{"id": "w1"}]'
    )
    assert "GAMING PACING & TIMING CONTRACT" in score_p or "GAMING PACING & TIMING CONTRACT" in detail_p
    assert "SETUP (start 2–4s before the action)" in detail_p
    assert "PAYOFF & REACTION" in detail_p
    assert "Bro thought he could escape 5 stars" in detail_p

    visual_p = gemini_worker.GAMING_VISUAL_PROMPT_TEMPLATE.format(
        video_duration=120,
        language="en",
        min_clips=2,
        max_clips=5,
        min_secs=15.0,
        max_secs=60.0
    )
    assert "gameplay" in visual_p.lower()
    assert "stunt" in visual_p.lower()


def test_clip_selector_adaptive_backfill_short_video():
    """Verify that a 120s video/live window requesting 5 clips delivers 5 clips instead of 2."""
    from gaming_intelligence.clip_selector import ClipSelector
    # Construct a 120s timeline
    timeline = []
    for sec in range(120):
        # Add intermittent energy spikes
        comp = 0.85 if sec in (15, 16, 45, 46, 75, 76, 100, 101) else 0.40
        timeline.append({
            "timestamp": float(sec),
            "composite_score": comp,
            "hook": f"Action moment at {sec}s" if comp > 0.5 else ""
        })

    selector = ClipSelector(min_duration=25.0, max_duration=60.0, max_clips=5, min_gap_sec=8.0)
    shorts = selector.select_clips(timeline, profile_name="gaming")

    # Before fix, it only returned 2 clips. With adaptive backfill, it delivers all 5!
    assert len(shorts) == 5
    for s in shorts:
        assert s["end"] <= 120.0
        assert s["start"] < s["end"]
        assert (s["end"] - s["start"]) >= 15.0


def test_generate_clips_from_windows_and_peaks_fallback():
    from clip_selection import generate_clips_from_windows_and_peaks
    windows = [
        {"id": "w1", "start": 0.0, "end": 60.0, "text": "driving around waiting"},
        {"id": "w2", "start": 60.0, "end": 120.0, "text": "oh no cops are here look at that crash", "action_intensity": 0.95,
         "action_moments": [{"start": 75.0, "end": 90.0, "intensity": 0.95, "type": "action_climax"}]},
        {"id": "w3", "start": 120.0, "end": 180.0, "text": "insane stunt jump over the building", "action_intensity": 0.88,
         "action_moments": [{"start": 135.0, "end": 150.0, "intensity": 0.88, "type": "motion_peak"}]},
    ]
    words = [
        {"w": "Driving", "s": 0.0, "e": 0.5},
        {"w": "around.", "s": 0.5, "e": 1.0},
        {"w": "Oh", "s": 65.0, "e": 65.4},
        {"w": "no,", "s": 65.4, "e": 65.8},
        {"w": "cops", "s": 65.8, "e": 66.2},
        {"w": "are", "s": 66.2, "e": 66.5},
        {"w": "here.", "s": 66.5, "e": 67.0},
        {"w": "Look", "s": 75.0, "e": 75.4},
        {"w": "at", "s": 75.4, "e": 75.6},
        {"w": "that", "s": 75.6, "e": 75.9},
        {"w": "crash!", "s": 75.9, "e": 76.5},
        {"w": "Done.", "s": 95.0, "e": 95.5},
        {"w": "Insane", "s": 135.0, "e": 135.5},
        {"w": "jump!", "s": 135.5, "e": 136.0},
        {"w": "Ended.", "s": 165.0, "e": 165.5},
    ]

    shorts = generate_clips_from_windows_and_peaks(
        windows=windows,
        action_peaks=[],
        words=words,
        video_duration=180.0,
        min_clips=2,
        max_clips=3,
        min_secs=25.0,
        max_secs=45.0,
        is_gaming=True,
    )

    assert len(shorts) >= 2
    for s in shorts:
        assert s["start"] < s["end"]
        assert s["predicted_score"] >= 70
        assert s["video_title_for_youtube_short"]
        assert s["viral_hook_text"]
        assert s["video_description_for_tiktok"]
        assert s["video_description_for_instagram"]

