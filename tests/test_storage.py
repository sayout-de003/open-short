"""Unit tests for local media storage, HTTPS verification, and safe cleanup."""
from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from autopilot.database import AutopilotDatabase
from autopilot.models import DiscoveredSource, PublicationStatus
from autopilot.queue import PersistentQueue
from autopilot.storage import LocalMediaStorage


def _setup_clip(tmp_path: Path):
    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)
    job_id = q.register_source_and_enqueue(
        DiscoveredSource(
            platform="youtube", source_id="v1", source_type="vod",
            url="https://youtube.com/watch?v=v1", title="T", channel_id="c1", channel_name="C1",
        )
    )
    storage = LocalMediaStorage(
        db=db,
        clips_dir=tmp_path / "clips",
        temp_dir=tmp_path / "temp",
        public_api_url="https://clips.example.com",
        retention_hours=24,
        delete_after_publish=True,
    )
    raw_mp4 = tmp_path / "raw.mp4"
    raw_mp4.write_bytes(b"mp4bytes" * 20000)
    clip_id = storage.register_approved_clip(job_id, None, raw_mp4, 35.0, 1080, 1920, raw_mp4.stat().st_size)
    return db, q, storage, clip_id


@patch("autopilot.storage.requests.get")
def test_storage_verify_and_post_publish_cleanup(mock_get, tmp_path: Path) -> None:
    db, q, storage, clip_id = _setup_clip(tmp_path)
    mock_get.return_value = MagicMock(status_code=206)

    url = storage.verify_public_url(clip_id)
    assert url == f"https://clips.example.com/videos/autopilot/{clip_id}"

    pub_id = q.create_publication_attempt(clip_id, "ch_yt", "youtube", "T", "C", None)
    assert pub_id is not None

    # Not yet published -> must NOT delete
    assert storage.delete_clip_if_published(clip_id) is False
    assert (tmp_path / "clips" / f"{clip_id}.mp4").exists()

    # Mark PUBLISHED -> deletes local file
    with db.transaction(immediate=True) as conn:
        conn.execute(
            "UPDATE published_posts SET publication_status = ? WHERE id = ?",
            (PublicationStatus.PUBLISHED.value, pub_id),
        )
    assert storage.delete_clip_if_published(clip_id) is True
    assert not (tmp_path / "clips" / f"{clip_id}.mp4").exists()


def test_storage_24h_ttl_skips_scheduled_clips(tmp_path: Path) -> None:
    db, q, storage, clip_id = _setup_clip(tmp_path)
    old_ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=30)).isoformat()
    with db.transaction(immediate=True) as conn:
        conn.execute("UPDATE rendered_clips SET created_at = ? WHERE id = ?", (old_ts, clip_id))

    # Active scheduled post protects clip from premature deletion
    pub_id = q.create_publication_attempt(clip_id, "ch_yt", "youtube", "T", "C", None)
    with db.transaction(immediate=True) as conn:
        conn.execute(
            "UPDATE published_posts SET publication_status = ? WHERE id = ?",
            (PublicationStatus.SCHEDULED.value, pub_id),
        )
    assert storage.cleanup_expired_media() == 0
    assert (tmp_path / "clips" / f"{clip_id}.mp4").exists()

    # Once failed/expired, 24h sweep deletes it
    with db.transaction(immediate=True) as conn:
        conn.execute(
            "UPDATE published_posts SET publication_status = ? WHERE id = ?",
            (PublicationStatus.FAILED.value, pub_id),
        )
    assert storage.cleanup_expired_media() == 1
    assert not (tmp_path / "clips" / f"{clip_id}.mp4").exists()
