"""Unit tests for clip quality validator."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from autopilot.quality import ClipQualityValidator


def test_quality_validator_rejects_missing_or_small_file(tmp_path: Path) -> None:
    v = ClipQualityValidator()
    assert v.validate(tmp_path / "missing.mp4").reason == "file_missing"

    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"123")
    assert v.validate(tiny).reason.startswith("file_too_small:")


@patch("autopilot.quality.subprocess.run")
def test_quality_validator_checks_aspect_duration_and_audio(mock_run, tmp_path: Path) -> None:
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"0" * 200_000)

    v = ClipQualityValidator(min_duration=30.0, max_duration=40.0)

    # Valid 9:16 35s clip with audio
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "format": {"duration": "35.0", "format_name": "mov,mp4"},
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920},
                {"codec_type": "audio"},
            ],
        }),
    )
    res = v.validate(mp4, ffprobe_bin="ffprobe")
    assert res.passed is True
    assert res.width == 1080 and res.height == 1920

    # Invalid 16:9 clip rejected
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "format": {"duration": "35.0"},
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080},
                {"codec_type": "audio"},
            ],
        }),
    )
    res_bad = v.validate(mp4, ffprobe_bin="ffprobe")
    assert res_bad.passed is False
    assert "invalid_aspect_ratio" in res_bad.reason
