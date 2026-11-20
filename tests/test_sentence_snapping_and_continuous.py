import pytest
from clip_selection import snap_clip_to_words, shortlist_target, clip_count_targets, dedupe_overlapping


def test_shortlist_target_scales_with_long_videos():
    # 10m -> 8
    assert shortlist_target(600) == 8
    # 30m (1800s) -> 22 (uncapped from old 10)
    assert shortlist_target(1800) == 22
    # 1 hr (3600s) -> 35 (uncapped from old 10)
    assert shortlist_target(3600) == 35


def test_clip_count_targets_scales_with_longform_shortlist():
    # 5 windows -> 4-10
    low, high = clip_count_targets(5)
    assert low >= 3
    assert high >= 5

    # 30 windows on a 1-hour source -> floor 15, ceiling 30
    low_long, high_long = clip_count_targets(30)
    assert low_long >= 12
    assert high_long >= 25


def test_snap_clip_to_words_sentence_boundary_preservation():
    words = [
        {"w": "and", "s": 10.0, "e": 10.2},
        {"w": "welcome", "s": 10.3, "e": 10.7},
        {"w": "to", "s": 10.8, "e": 10.9},
        {"w": "the", "s": 11.0, "e": 11.1},
        {"w": "show.", "s": 11.2, "e": 11.6},
        {"w": "Today", "s": 12.5, "e": 12.9},
        {"w": "we", "s": 13.0, "e": 13.2},
        {"w": "are", "s": 13.3, "e": 13.5},
        {"w": "launching", "s": 13.6, "e": 14.1},
        {"w": "something", "s": 14.2, "e": 14.7},
        {"w": "crazy!", "s": 14.8, "e": 15.3},
        {"w": "So", "s": 15.8, "e": 16.0},
        {"w": "stay", "s": 16.1, "e": 16.4},
        {"w": "tuned.", "s": 16.5, "e": 17.0},
        {"w": "and", "s": 17.5, "e": 17.7},
        {"w": "check", "s": 17.8, "e": 18.2},
        {"w": "this", "s": 18.3, "e": 18.6},
        {"w": "out.", "s": 18.7, "e": 19.2},
        {"w": "Wait,", "s": 25.0, "e": 25.5},
        {"w": "let", "s": 25.6, "e": 25.8},
        {"w": "me", "s": 25.9, "e": 26.1},
        {"w": "explain", "s": 26.2, "e": 26.8},
        {"w": "why.", "s": 26.9, "e": 27.5},
    ]

    # Proposing clip [12.0, 27.0]
    # "Today" is at 12.5, preceded by "show." and a 0.9s pause -> clean sentence start
    # "why." is at 27.5, ending with '.' -> clean sentence end
    s, e = snap_clip_to_words(12.0, 27.0, words, video_duration=60.0, min_duration=10.0, max_duration=30.0)
    assert s <= 12.5  # Leads cleanly before "Today"
    assert e >= 27.5  # Includes "why." and does not cut off before completion
    assert e - s >= 10.0


def test_dedupe_overlapping_allows_distinct_narratives():
    shorts = [
        {"start": 10.0, "end": 40.0, "predicted_score": 90},
        # 30.0 - 60.0 overlaps 10s of 30s (33.3% overlap)
        # With old 0.25 it was dropped; with new 0.40 it is preserved!
        {"start": 30.0, "end": 60.0, "predicted_score": 85},
    ]
    kept = dedupe_overlapping(shorts)
    assert len(kept) == 2
