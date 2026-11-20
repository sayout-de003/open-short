"""Unit tests for Buffer publisher, per-channel quotas, idempotency, and reconciliation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from autopilot.database import AutopilotDatabase
from autopilot.models import DiscoveredSource, PublicationStatus
from autopilot.publisher import BufferAutopilotPublisher
from autopilot.queue import PersistentQueue
from autopilot.storage import LocalMediaStorage


@patch("autopilot.publisher.fetch_buffer_post_status")
@patch("autopilot.publisher.buffer_publisher.create_post")
@patch("autopilot.publisher.buffer_publisher.list_channels")
def test_publisher_quotas_idempotency_and_reconciliation(
    mock_list_channels,
    mock_create_post,
    mock_fetch_status,
    tmp_path: Path,
) -> None:
    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)
    storage = LocalMediaStorage(
        db=db,
        clips_dir=tmp_path / "clips",
        temp_dir=tmp_path / "temp",
        public_api_url="https://clips.example.com",
    )

    mock_list_channels.return_value = [
        {"id": "ch_yt", "service": "youtube", "name": "YT", "isDisconnected": False, "isLocked": False},
        {"id": "ch_ig", "service": "instagram", "name": "IG", "isDisconnected": False, "isLocked": False},
    ]
    mock_create_post.side_effect = [
        {"success": True, "post": {"id": "buf_1", "status": "scheduled"}},
        {"success": True, "post": {"id": "buf_2", "status": "scheduled"}},
    ]

    job_id = q.register_source_and_enqueue(
        DiscoveredSource(
            platform="youtube", source_id="v1", source_type="vod",
            url="https://youtube.com/watch?v=v1", title="GTA 6 Moment", channel_id="c1", channel_name="Streamer",
        )
    )
    raw = tmp_path / "c.mp4"
    raw.write_bytes(b"0" * 150_000)
    clip_id = storage.register_approved_clip(job_id, None, raw, 35.0, 1080, 1920, raw.stat().st_size)

    pub = BufferAutopilotPublisher(
        db=db, queue=q, storage=storage, platforms=["youtube", "instagram"],
        posts_per_channel_per_day=1, retention_hours=24, buffer_token="tok",
    )

    res = pub.publish_clip(clip_id, f"https://clips.example.com/videos/autopilot/{clip_id}", "GTA 6 Moment", "Streamer", "GTA 6")
    assert len(res) == 2
    assert res[0]["status"] == PublicationStatus.SCHEDULED.value

    # Re-publishing same clip is blocked by Level-3 dedup/quota
    res2 = pub.publish_clip(clip_id, f"https://clips.example.com/videos/autopilot/{clip_id}", "GTA 6 Moment", "Streamer", "GTA 6")
    assert all("skipped" in r for r in res2)

    # Reconcile marks PUBLISHED and deletes local MP4
    mock_fetch_status.return_value = "sent"
    rec = pub.reconcile_pending_posts()
    assert rec["published"] == 2
    assert rec["cleaned"] == 1
    assert not (tmp_path / "clips" / f"{clip_id}.mp4").exists()
