"""
tests/test_gaming_engine.py - Test suite for GamingIntelligenceEngine and streamer top-cam routing.
"""
from intelligence.engines.gaming import GamingEventCategory, GamingIntelligenceEngine
from intelligence.timeline import UnifiedTimeline


def test_gaming_engine_with_top_streamer_webcam():
    timeline = UnifiedTimeline(duration=120.0)
    # Simulate a GTA 6 high-speed pursuit climax at t=45s
    timeline.add_event(40.0, 48.0, "visual_motion", intensity=0.94, label="chase_drift")
    timeline.add_event(44.0, 46.0, "audio_peak", intensity=0.88, label="bridge_jump_impact")
    timeline.add_event(46.0, 50.0, "streamer_reaction", intensity=0.91, label="streamer_screaming")

    engine = GamingIntelligenceEngine(min_clip_sec=15.0, max_clip_sec=45.0, target_clip_count=3)
    candidates = engine.analyze_timeline(timeline, has_streamer_webcam=True)

    assert len(candidates) >= 1
    top_cand = candidates[0]

    # Verify Setup -> Climax -> Payoff boundaries
    assert top_cand.setup_start < top_cand.climax_start < top_cand.payoff_end
    assert 15.0 <= top_cand.duration <= 45.0

    # Verify streamer top-cam recommendation
    assert top_cand.has_webcam is True
    assert top_cand.recommended_template == "streamer_stacked_top"
    assert top_cand.recommended_layout == "stacked_top_cam"
    assert top_cand.score >= 0.85


def test_zero_speech_stunt_scoring():
    timeline = UnifiedTimeline(duration=90.0)
    # Silent stunt: high motion, minimal/no speech or audio
    timeline.add_event(30.0, 36.0, "visual_motion", intensity=0.95, label="silent_stunt_jump")

    engine = GamingIntelligenceEngine(min_clip_sec=15.0, max_clip_sec=40.0)
    candidates = engine.analyze_timeline(timeline, has_streamer_webcam=False)

    assert len(candidates) >= 1
    stunt_cand = candidates[0]

    # Must score high despite complete absence of dialogue
    assert stunt_cand.category == GamingEventCategory.VEHICLE_ACTION
    assert stunt_cand.score >= 0.80
    assert stunt_cand.recommended_template == "gaming_cinematic"
    assert stunt_cand.recommended_layout == "gameplay_center"
