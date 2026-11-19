"""
tests/test_clip_validator.py - Test suite for Automated Quality Assurance clip validator.
"""
import os
import pytest
from quality.clip_validator import ClipValidator, validate_clip

DEMO_VIDEO = os.path.join(os.path.dirname(__file__), "..", "demo-openshorts.mp4")


@pytest.mark.skipif(not os.path.exists(DEMO_VIDEO), reason="demo-openshorts.mp4 not found")
def test_validate_real_clip():
    validator = ClipValidator(
        min_duration=1.0,
        max_duration=60.0,
        expected_aspect_ratio="16:9",  # Demo video is landscape
        require_audio=True,
    )
    report = validator.validate(DEMO_VIDEO)

    assert report.clip_path == DEMO_VIDEO
    assert report.duration > 0.0
    assert report.width > 0
    assert report.height > 0
    assert report.has_audio is True
    assert report.quality_score >= 0.80
    assert report.status in ("passed", "warning")


def test_validate_nonexistent_file():
    validator = ClipValidator()
    report = validator.validate("does_not_exist.mp4")
    assert report.status == "failed"
    assert report.quality_score == 0.0
    assert "File does not exist" in report.issues[0]


def test_validate_clip_helper_dict():
    res = validate_clip(DEMO_VIDEO, min_duration=1.0, max_duration=60.0, expected_aspect_ratio="16:9")
    assert isinstance(res, dict)
    assert "quality_score" in res
    assert "status" in res
    assert "metrics" in res
