"""Unit tests for autopilot centralized configuration and validation."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from autopilot.config import AutopilotConfig
from autopilot.exceptions import ConfigError


def test_config_loads_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join([
            f"OPENSHORT_OUTPUT_DIR={tmp_path / 'out'}",
            "BUFFER_ACCESS_TOKEN=buf_tok_test",
            "PUBLIC_API_URL=https://clips.example.com/",
            "MAX_VODS_PER_RUN=4",
            "CLIP_RETENTION_HOURS=24",
            "DELETE_CLIP_AFTER_PUBLISH=true",
        ]),
        encoding="utf-8",
    )
    for k in (
        "OPENSHORT_OUTPUT_DIR", "BUFFER_ACCESS_TOKEN", "PUBLIC_API_URL",
        "MAX_VODS_PER_RUN", "CLIP_RETENTION_HOURS", "DELETE_CLIP_AFTER_PUBLISH",
        "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET",
    ):
        monkeypatch.delenv(k, raising=False)

    cfg = AutopilotConfig.from_env(env_path=env_file)
    assert cfg.output_dir == tmp_path / "out"
    assert cfg.buffer_access_token == "buf_tok_test"
    assert cfg.public_api_url == "https://clips.example.com"
    assert cfg.max_vods_per_run == 4
    assert cfg.clip_retention_hours == 24
    assert cfg.delete_clip_after_publish is True
    cfg.validate(require_publish=True, require_discovery=False)


def test_config_validation_rejects_non_https_public_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSHORT_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("BUFFER_ACCESS_TOKEN", "buf_tok")
    monkeypatch.setenv("PUBLIC_API_URL", "http://localhost:8000")

    cfg = AutopilotConfig.from_env(env_path=tmp_path / "missing.env")
    with pytest.raises(ConfigError, match="https://"):
        cfg.validate(require_publish=True)


def test_config_validation_rejects_missing_twitch_creds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSHORT_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("TWITCH_DISCOVERY_ENABLED", "true")
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)

    cfg = AutopilotConfig.from_env(env_path=tmp_path / "missing.env")
    with pytest.raises(ConfigError, match="TWITCH_CLIENT_ID"):
        cfg.validate(require_discovery=True)
