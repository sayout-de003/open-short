"""Unit tests for VODWorker and LiveWorker integration."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from autopilot.config import AutopilotConfig
from autopilot.database import AutopilotDatabase
from autopilot.models import DiscoveredSource, JobStatus
from autopilot.quality import ClipQualityValidator, QualityResult
from autopilot.queue import PersistentQueue
from autopilot.storage import LocalMediaStorage
from autopilot.workers import LiveWorker, VODWorker


def _make_cfg(tmp_path: Path) -> AutopilotConfig:
    cfg = AutopilotConfig(
        base_dir=tmp_path,
        output_dir=tmp_path / "output",
        clips_dir=tmp_path / "output" / "clips",
        temp_dir=tmp_path / "output" / "temp",
        logs_dir=tmp_path / "output" / "logs",
        database_path=tmp_path / "output" / "autopilot.db",
        public_api_url="https://clips.example.com",
        max_clips_per_source=2,
    )
    cfg.ensure_directories()
    return cfg


def test_vod_worker_caps_clips_and_registers_approved(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    db = AutopilotDatabase(cfg.database_path)
    q = PersistentQueue(db)
    storage = LocalMediaStorage(db, cfg.clips_dir, cfg.temp_dir, cfg.public_api_url)
    quality = MagicMock(spec=ClipQualityValidator)
    quality.validate.return_value = QualityResult(True, "approved", 35.0, 1080, 1920, 200_000, True)

    jid = q.register_source_and_enqueue(
        DiscoveredSource(
            platform="youtube", source_id="vod_1", source_type="vod",
            url="https://youtube.com/watch?v=vod_1", title="VOD", channel_id="c1", channel_name="C1",
        )
    )
    job = q.claim_next_job("w1")
    assert job is not None

    worker = VODWorker(cfg, q, quality, storage)

    def _fake_main(url: str, output_dir: Path) -> None:
        clips = []
        for idx, (st, en) in enumerate([(10.0, 45.0), (100.0, 135.0), (200.0, 235.0)]):
            mp4 = output_dir / f"clip_{idx}.mp4"
            mp4.write_bytes(b"0" * 200_000)
            clips.append({"file_path": str(mp4), "start_time": st, "end_time": en, "score": 90 - idx})
        (output_dir / "vod_metadata.json").write_text(json.dumps({"shorts": clips}), encoding="utf-8")

    with patch.object(worker, "_invoke_main_pipeline", side_effect=_fake_main):
        approved = worker.process_job(job)

    assert len(approved) == 2  # Capped at max_clips_per_source=2
    updated = q.get_job(jid)
    assert updated is not None and updated.status == JobStatus.QUALITY_APPROVED


def test_live_worker_uses_cooldown_and_approves_clips(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    db = AutopilotDatabase(cfg.database_path)
    q = PersistentQueue(db)
    storage = LocalMediaStorage(db, cfg.clips_dir, cfg.temp_dir, cfg.public_api_url)
    quality = MagicMock(spec=ClipQualityValidator)
    quality.validate.return_value = QualityResult(True, "approved", 32.0, 1080, 1920, 200_000, True)

    jid = q.register_source_and_enqueue(
        DiscoveredSource(
            platform="twitch", source_id="live_1", source_type="live",
            url="https://twitch.tv/streamer", title="Live", channel_id="c1", channel_name="streamer",
        )
    )
    job = q.claim_next_job("w1")
    assert job is not None

    rendered = tmp_path / "live_clip.mp4"
    rendered.write_bytes(b"0" * 200_000)

    fake_pipe = MagicMock()
    fake_pipe.detector = MagicMock()
    fake_pipe.scheduler = MagicMock()
    fake_pipe.completed_jobs = [MagicMock(final_path=str(rendered), event=MagicMock(detected_at=100.0, z_score=4.5))]

    async def _noop(*args, **kwargs):
        return None

    fake_pipe.start_twitch = _noop

    with patch("gaming_intelligence.live.pipeline.LiveHypePipeline", return_value=fake_pipe):
        worker = LiveWorker(cfg, q, quality, storage)
        approved = worker.process_job(job)

    assert len(approved) == 1
    assert fake_pipe.detector.cooldown_sec == float(cfg.live_clip_cooldown_seconds)
