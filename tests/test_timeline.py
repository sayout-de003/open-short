"""
tests/test_timeline.py - Test suite for UnifiedTimeline and multi-signal synchronization.
"""
from intelligence.timeline import TimelineEvent, UnifiedTimeline


def test_timeline_add_and_query():
    tl = UnifiedTimeline(duration=60.0)
    tl.add_event(10.0, 15.0, "visual_motion", intensity=0.85, label="high_speed_chase")
    tl.add_event(14.0, 16.0, "audio_peak", intensity=0.92, label="explosion")
    tl.add_event(15.0, 20.0, "speech_token", intensity=0.70, label="streamer_scream")

    # Query window [12, 17]
    events = tl.get_window(12.0, 17.0)
    assert len(events) == 3

    # Query window [0, 5] (empty)
    assert len(tl.get_window(0.0, 5.0)) == 0


def test_timeline_peaks():
    tl = UnifiedTimeline(duration=100.0)
    tl.add_event(10.0, 12.0, "visual_motion", intensity=0.40)
    tl.add_event(25.0, 27.0, "visual_motion", intensity=0.95)
    tl.add_event(50.0, 52.0, "audio_peak", intensity=0.88)

    peaks = tl.find_peaks("visual_motion", min_intensity=0.60)
    assert len(peaks) == 1
    assert peaks[0].intensity == 0.95
    assert peaks[0].start == 25.0


def test_density_scoring():
    tl = UnifiedTimeline(duration=60.0)
    tl.add_event(10.0, 20.0, "visual_motion", intensity=1.0)
    tl.add_event(10.0, 20.0, "audio_peak", intensity=1.0)

    # Window covering the events
    dense_score = tl.score_density(10.0, 20.0)
    assert dense_score > 0.50

    # Window far away
    empty_score = tl.score_density(40.0, 50.0)
    assert empty_score == 0.0


def test_timeline_serialization():
    tl = UnifiedTimeline(duration=30.0)
    tl.add_event(5.0, 10.0, "visual_motion", intensity=0.75, metadata={"fps": 30})

    data = tl.to_dict()
    assert data["duration"] == 30.0
    assert data["total_events"] == 1

    restored = UnifiedTimeline.from_dict(data)
    assert restored.duration == 30.0
    assert len(restored.events) == 1
    assert restored.events[0].event_type == "visual_motion"
    assert restored.events[0].metadata["fps"] == 30
