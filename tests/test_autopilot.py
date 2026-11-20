"""End-to-end mocked orchestration and CLI tests for autopilot."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from autopilot.config import AutopilotConfig
from autopilot.models import DiscoveredSource, JobStatus
from autopilot.orchestrator import AutopilotOrchestrator


def test_orchestrator_dry_run_and_vod_slice(tmp_path: Path) -> None:
    cfg = AutopilotConfig(
        base_dir=tmp_path,
        output_dir=tmp_path / "output",
        clips_dir=tmp_path / "output" / "clips",
        temp_dir=tmp_path / "output" / "temp",
        logs_dir=tmp_path / "output" / "logs",
        database_path=tmp_path / "output" / "autopilot.db",
        buffer_access_token="buf_tok",
        public_api_url="https://clips.example.com",
        twitch_discovery_enabled=False,
    )
    cfg.ensure_directories()
    orch = AutopilotOrchestrator(cfg)

    cand = DiscoveredSource(
        platform="youtube", source_id="vod_99", source_type="vod",
        url="https://youtube.com/watch?v=vod_99", title="GTA 6 Gameplay",
        channel_id="ch_99", channel_name="Gamer99", view_count=100000, score=95.0,
    )

    with patch.object(orch, "discover_and_rank", return_value=[cand]):
        dry = orch.run_once(query="GTA 6", dry_run=True)
        assert dry["dry_run"] is True
        assert dry["discovered"] == 1
        assert dry["enqueued"] == 0

    raw_mp4 = tmp_path / "clip.mp4"
    raw_mp4.write_bytes(b"0" * 150_000)
    clip_id = orch.storage.register_approved_clip("dummy_ignore", None, raw_mp4, 34.0, 1080, 1920, 150_000) if False else None

    def _fake_vod_process(job):
        cid = orch.storage.register_approved_clip(job.id, None, raw_mp4, 34.0, 1080, 1920, 150_000)
        orch.queue.transition_job(job.id, JobStatus.CLIPS_GENERATED)
        orch.queue.transition_job(job.id, JobStatus.QUALITY_APPROVED)
        return [cid]

    with patch.object(orch, "discover_and_rank", return_value=[cand]), \
         patch.object(orch.publisher, "reconcile_pending_posts", return_value={"checked": 0, "published": 0, "cleaned": 0}), \
         patch.object(orch.vod_worker, "process_job", side_effect=_fake_vod_process), \
         patch.object(orch.storage, "verify_public_url", side_effect=lambda c: f"https://clips.example.com/videos/autopilot/{c}"), \
         patch.object(orch.publisher, "publish_clip", return_value=[{"buffer_post_id": "bp_1", "status": "SCHEDULED"}]):
        res = orch.run_once(query="GTA 6", max_vods=1, max_live=0)

    assert res["enqueued"] == 1
    assert res["clips_approved"] == 1
    assert res["posts_scheduled"] == 1
