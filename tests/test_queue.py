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
