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
