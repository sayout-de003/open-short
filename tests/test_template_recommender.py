"""
tests/test_template_recommender.py - Test suite for Template Recommendation Engine.
"""
from template_library.recommender import recommend_template


def test_recommend_gaming_streamer_webcam():
    rec = recommend_template(
        content_profile="gaming",
        event_category="vehicle_action",
        has_webcam=True,
    )
    assert rec["recommended_template_id"] == "streamer_stacked_top"
    assert rec["template"]["layout"] == "stacked_top_cam"
    assert rec["confidence"] >= 0.90
    assert "streamer_reaction" in rec["alternatives"]


def test_recommend_gaming_cinematic_no_webcam():
    rec = recommend_template(
        content_profile="gaming",
        event_category="vehicle_action",
        has_webcam=False,
    )
    assert rec["recommended_template_id"] == "gaming_cinematic"
    assert rec["template"]["layout"] == "gameplay_center"


def test_recommend_gaming_fail():
    rec = recommend_template(
        content_profile="gaming",
        event_category="unexpected_fail",
        has_webcam=False,
    )
    assert rec["recommended_template_id"] == "gaming_fails"


def test_recommend_podcast_two_speakers():
    rec = recommend_template(
        content_profile="podcast",
        speaker_count=2,
    )
    assert rec["recommended_template_id"] == "podcast_split"
    assert rec["template"]["layout"] == "split_two_speaker"


def test_recommend_educational_code():
    rec = recommend_template(
        content_profile="educational",
        event_category="code_tutorial",
    )
    assert rec["recommended_template_id"] == "code_tutorial"
    assert rec["confidence"] >= 0.90


def test_recommend_commentary_reaction():
    rec = recommend_template(
        content_profile="commentary",
        event_category="reaction",
    )
    assert rec["recommended_template_id"] == "reaction_punch"
