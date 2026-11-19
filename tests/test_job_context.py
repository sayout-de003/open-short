"""
tests/test_job_context.py - Test suite for JobContext immutable dataclass and isolation.
"""
import pytest
from intelligence.job_context import JobContext, ContentProfile


def test_job_context_defaults():
    ctx = JobContext(job_id="job_abc123")
    assert ctx.job_id == "job_abc123"
    assert ctx.content_type == ContentProfile.AUTO
    assert ctx.resolved_profile == ContentProfile.GENERIC
    assert ctx.profile_confidence == 1.0
    assert ctx.aspect_ratio == "9:16"
    assert ctx.clip_count == 5


def test_job_context_immutability():
    ctx = JobContext(job_id="job_abc123")
    with pytest.raises(Exception):
        ctx.resolved_profile = "gaming"  # type: ignore


def test_job_context_with_resolved_profile():
    ctx = JobContext(job_id="job_abc123", content_type="auto")
    updated = ctx.with_resolved_profile("gaming", confidence=0.95, reason="GTA detection")
    assert ctx.resolved_profile == "generic"  # Original unchanged
    assert updated.resolved_profile == "gaming"
    assert updated.profile_confidence == 0.95
    assert updated.profile_reason == "GTA detection"
    assert updated.job_id == ctx.job_id


def test_profile_normalization():
    assert ContentProfile.normalize("gameplay") == ContentProfile.GAMING
    assert ContentProfile.normalize("TALK") == ContentProfile.PODCAST
    assert ContentProfile.normalize("tutorial") == ContentProfile.EDUCATIONAL
    assert ContentProfile.normalize("unknown_genre") == ContentProfile.GENERIC
    assert ContentProfile.normalize(None) == ContentProfile.AUTO


def test_subprocess_env_isolation():
    ctx = JobContext(
        job_id="job_test_456",
        content_type="auto",
        resolved_profile="gaming",
        profile_confidence=0.92,
        profile_reason="HUD detected",
        aspect_ratio="9:16",
        template_id="gaming_cinematic",
    )
    env = ctx.to_subprocess_env({"EXISTING_KEY": "kept"})
    assert env["EXISTING_KEY"] == "kept"
    assert env["JOB_ID"] == "job_test_456"
    assert env["CLIPPING_PROFILE"] == "gaming"
    assert env["CONTENT_TYPE"] == "auto"
    assert env["PROFILE_CONFIDENCE"] == "0.92"
    assert env["TEMPLATE_ID"] == "gaming_cinematic"
