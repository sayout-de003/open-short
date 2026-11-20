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


def test_vod_worker_invokes_pipeline_with_gaming_env(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    db = AutopilotDatabase(cfg.database_path)
    q = PersistentQueue(db)
    storage = LocalMediaStorage(db, cfg.clips_dir, cfg.temp_dir, cfg.public_api_url)
    quality = MagicMock(spec=ClipQualityValidator)

    worker = VODWorker(cfg, q, quality, storage)
    captured_env = {}

    def _mock_run(cmd, env=None, **kwargs):
        captured_env.update(env or {})
        mock_res = MagicMock()
        mock_res.returncode = 0
        return mock_res

    with patch("subprocess.run", side_effect=_mock_run):
        worker._invoke_main_pipeline("https://youtube.com/watch?v=sample", tmp_path / "out")

    assert captured_env.get("CONTENT_PROFILE") == "gaming"
    assert captured_env.get("CLIPPING_PROFILE") == "gaming"
    assert captured_env.get("TEMPLATE_ID") == "streamer_stacked_top"
    assert captured_env.get("STREAMER_CAM_POSITION") == "top"


def test_fast_vertical_renderer_uses_20_80_when_inset_detected(tmp_path: Path) -> None:
    from gaming_intelligence.live.clipping.renderer import FastVerticalRenderer
    import camera_inset

    out_dir = str(tmp_path / "rendered")
    renderer = FastVerticalRenderer(output_dir=out_dir)

    dummy_video = tmp_path / "dummy_draft.mp4"
    dummy_video.write_bytes(b"0" * 1000)

    captured_cmds = []

    def _mock_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        # Create output file so renderer succeeds
        final_mp4 = Path(cmd[-1])
        final_mp4.parent.mkdir(parents=True, exist_ok=True)
        final_mp4.write_bytes(b"0" * 2000)
        res = MagicMock()
        res.returncode = 0
        return res

    with patch("camera_inset.detect", return_value=(1500, 880, 350, 200)), \
         patch("cv2.VideoCapture") as mock_cap, \
         patch("subprocess.run", side_effect=_mock_run):
        cap_instance = MagicMock()
        cap_instance.isOpened.return_value = True
        cap_instance.get.side_effect = lambda prop: 1920 if prop == 3 else 1080
        mock_cap.return_value = cap_instance

        res_path = renderer.render_vertical_short(str(dummy_video), "out_short.mp4")

    assert Path(res_path).exists()
    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert "-filter_complex" in cmd
    fc_idx = cmd.index("-filter_complex")
    graph = cmd[fc_idx + 1]
    assert "scale=1080:384[cam]" in graph
    assert "scale=1080:1536[screen]" in graph
    assert "[cam][screen]vstack" in graph
    assert "drawbox=x=0:y=383:w=1080:h=2:color=white@0.5:t=fill" in graph
