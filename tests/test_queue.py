"""Unit tests for SQLite persistent queue, atomic claiming, state machine, and 3-level deduplication."""
from __future__ import annotations

import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from autopilot.database import AutopilotDatabase
from autopilot.models import DiscoveredSource, JobStatus
from autopilot.queue import PersistentQueue


def _make_source(source_id: str = "vid_1", eligible: bool = True, score: float = 85.0) -> DiscoveredSource:
    return DiscoveredSource(
        platform="youtube",
        source_id=source_id,
        source_type="vod",
        url=f"https://www.youtube.com/watch?v={source_id}",
        title="GTA 6 Trailer Breakdown",
        channel_id="chan_1",
        channel_name="GamerOne",
        view_count=50000,
        score=score,
        eligible=eligible,
        eligibility_reason="approved" if eligible else "opt_out",
    )


def test_source_deduplication_and_eligibility(tmp_path: Path) -> None:
    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)

    job1 = q.register_source_and_enqueue(_make_source("vid_1"))
    assert job1 is not None

    # Duplicate source rejected
    assert q.register_source_and_enqueue(_make_source("vid_1")) is None

    # Ineligible source recorded in discovered_sources but not enqueued
    assert q.register_source_and_enqueue(_make_source("vid_2", eligible=False)) is None


def test_atomic_job_claiming_concurrency(tmp_path: Path) -> None:
    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)
    q.register_source_and_enqueue(_make_source("vid_1", score=90.0))

    def _claim(worker: str):
        return q.claim_next_job(worker_id=worker)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_claim, ["w1", "w2", "w3", "w4"]))

    claimed = [r for r in results if r is not None]
    assert len(claimed) == 1
    assert claimed[0].status == JobStatus.PROCESSING
    assert claimed[0].attempt_count == 1


def test_state_machine_validation_and_stale_recovery(tmp_path: Path) -> None:
    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)
    job_id = q.register_source_and_enqueue(_make_source("vid_1"))
    assert job_id is not None

    # Cannot jump QUEUED -> PUBLISHED
    with pytest.raises(ValueError, match="Invalid job state transition"):
        q.transition_job(job_id, JobStatus.PUBLISHED)

    claimed = q.claim_next_job("w1")
    assert claimed is not None

    # Force locked_at into the past and recover
    old_ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=60)).isoformat()
    with db.transaction(immediate=True) as conn:
        conn.execute("UPDATE processing_jobs SET locked_at = ? WHERE id = ?", (old_ts, job_id))

    recovered = q.recover_stale_locks(stale_minutes=45)
    assert recovered == 1
    job = q.get_job(job_id)
    assert job is not None and job.status == JobStatus.QUEUED


def test_moment_and_publication_deduplication(tmp_path: Path) -> None:
    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)
    job_id = q.register_source_and_enqueue(_make_source("vid_1"))
    assert job_id is not None

    # Level 2: overlapping moments blocked
    m1 = q.record_moment_if_unique(job_id, "youtube", "vid_1", 100.0, 135.0, moment_score=90.0)
    assert m1 is not None
    m2 = q.record_moment_if_unique(job_id, "youtube", "vid_1", 115.0, 150.0, moment_score=80.0)
    assert m2 is None
    m3 = q.record_moment_if_unique(job_id, "youtube", "vid_1", 300.0, 335.0, moment_score=85.0)
    assert m3 is not None

    # Insert rendered_clip and test Level 3 publication deduplication
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """
            INSERT INTO rendered_clips (id, job_id, moment_id, local_path, duration_sec, quality_status, created_at)
            VALUES ('clip_1', ?, ?, '/tmp/clip_1.mp4', 35.0, 'approved', '2026-11-20T00:00:00+00:00')
            """,
            (job_id, m1),
        )

    pub1 = q.create_publication_attempt("clip_1", "ch_yt_1", "youtube", "Title", "Caption", None)
    assert pub1 is not None
    # Same (clip_1, ch_yt_1) blocked
    assert q.create_publication_attempt("clip_1", "ch_yt_1", "youtube", "Title", "Caption", None) is None
    # Different channel allowed
    pub2 = q.create_publication_attempt("clip_1", "ch_ig_1", "instagram", "Title", "Caption", None)
    assert pub2 is not None


def test_job_status_case_insensitivity_and_claim_by_id(tmp_path: Path) -> None:
    # Test case insensitivity of JobStatus
    assert JobStatus("queued") == JobStatus.QUEUED
    assert JobStatus("Queued") == JobStatus.QUEUED
    assert JobStatus("processing") == JobStatus.PROCESSING

    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)

    # Insert lowercase 'queued' directly to simulate legacy or external writes
    with db.transaction(immediate=True) as conn:
        conn.execute("""
            INSERT INTO discovered_sources (platform, source_id, source_type, url, title, channel_id, channel_name, discovered_at)
            VALUES ('youtube', 'vid_case_1', 'vod', 'http://yt.com/1', 'Test Case', 'ch1', 'Chan', '2026-11-20T00:00:00+00:00')
        """)
        src_pk = conn.execute("SELECT id FROM discovered_sources WHERE source_id='vid_case_1'").fetchone()["id"]
        conn.execute("""
            INSERT INTO processing_jobs (id, source_pk, platform, source_id, job_type, status, priority, created_at, updated_at)
            VALUES ('job_case_1', ?, 'youtube', 'vid_case_1', 'vod', 'queued', 10.0, '2026-11-20T00:00:00+00:00', '2026-11-20T00:00:00+00:00')
        """, (src_pk,))

    # claim_next_job handles lowercase 'queued'
    claimed = q.claim_next_job("worker_test")
    assert claimed is not None
    assert claimed.id == "job_case_1"
    assert claimed.status == JobStatus.PROCESSING

    # Enqueue a second job and test claim_job_by_id
    job2_id = q.register_source_and_enqueue(_make_source("vid_case_2"))
    assert job2_id is not None
    claimed_by_id = q.claim_job_by_id(job2_id, "worker_specific")
    assert claimed_by_id is not None
    assert claimed_by_id.id == job2_id
    assert claimed_by_id.status == JobStatus.PROCESSING


def test_delete_job_cleans_database(tmp_path: Path) -> None:
    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)
    job_id = q.register_source_and_enqueue(_make_source("vid_del_1"))
    assert job_id is not None

    m = q.record_moment_if_unique(job_id, "youtube", "vid_del_1", 10.0, 45.0)
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """
            INSERT INTO rendered_clips (id, job_id, moment_id, local_path, duration_sec, quality_status, created_at)
            VALUES ('clip_del_1', ?, ?, '/tmp/clip_del.mp4', 35.0, 'approved', '2026-11-20T00:00:00+00:00')
            """,
            (job_id, m),
        )
    q.create_publication_attempt("clip_del_1", "ch_del_1", "youtube", "Title", "Caption", None)

    # Delete job
    assert q.delete_job(job_id) is True

    # Verify all tables are cleared of this job
    with db.transaction(immediate=True) as conn:
        assert conn.execute("SELECT COUNT(*) as cnt FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()["cnt"] == 0
        assert conn.execute("SELECT COUNT(*) as cnt FROM clip_moments WHERE job_id = ?", (job_id,)).fetchone()["cnt"] == 0
        assert conn.execute("SELECT COUNT(*) as cnt FROM rendered_clips WHERE job_id = ?", (job_id,)).fetchone()["cnt"] == 0
        assert conn.execute("SELECT COUNT(*) as cnt FROM published_posts WHERE rendered_clip_id = 'clip_del_1'").fetchone()["cnt"] == 0
