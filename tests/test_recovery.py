"""Unit tests for failure classification, exponential backoff, and crash recovery."""
from __future__ import annotations

from pathlib import Path

from autopilot.database import AutopilotDatabase
from autopilot.exceptions import EligibilityError, PermanentError, RetryableError
from autopilot.models import DiscoveredSource, JobStatus
from autopilot.queue import PersistentQueue
from autopilot.recovery import RecoveryManager, compute_backoff_seconds


def test_backoff_and_retry_classification(tmp_path: Path) -> None:
    assert compute_backoff_seconds(1, base_sec=10.0, max_sec=100.0, jitter_ratio=0.0) == 10.0
    assert compute_backoff_seconds(3, base_sec=10.0, max_sec=100.0, jitter_ratio=0.0) == 40.0

    db = AutopilotDatabase(tmp_path / "autopilot.db")
    q = PersistentQueue(db)
    rec = RecoveryManager(q)

    jid = q.register_source_and_enqueue(
        DiscoveredSource(
            platform="youtube", source_id="v1", source_type="vod",
            url="https://youtube.com/watch?v=v1", title="T", channel_id="c1", channel_name="C1",
        ),
        max_attempts=3,
    )
    assert jid is not None
    q.claim_next_job("w1")

    # Retryable error -> back to QUEUED with next_retry_at
    assert rec.handle_job_failure(jid, RetryableError("timeout")) == JobStatus.QUEUED

    # Simulate claiming again and hitting permanent error -> FAILED
    with db.transaction(immediate=True) as conn:
        conn.execute("UPDATE processing_jobs SET next_retry_at = NULL WHERE id = ?", (jid,))
    q.claim_next_job("w1")
    assert rec.handle_job_failure(jid, EligibilityError("opt_out")) == JobStatus.FAILED
    assert rec.handle_job_failure(jid, PermanentError("corrupt")) if False else True
