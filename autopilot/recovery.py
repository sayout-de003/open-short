"""Crash recovery, error classification, and exponential backoff with jitter."""
from __future__ import annotations

import datetime
import random

from .exceptions import PermanentError, RateLimitError, RetryableError
from .models import JobStatus
from .queue import PersistentQueue


def compute_backoff_seconds(
    attempt: int,
    base_sec: float = 30.0,
    max_sec: float = 3600.0,
    jitter_ratio: float = 0.20,
) -> float:
    """Exponential backoff: t_n = min(t_max, t_0 * 2^n) + jitter."""
    exp = min(max_sec, base_sec * (2 ** max(0, attempt - 1)))
    jitter = random.uniform(0.0, exp * jitter_ratio)
    return round(exp + jitter, 2)


def is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, PermanentError):
        return False
    if isinstance(exc, RetryableError):
        return True
    msg = str(exc).lower()
    transient_markers = ("timeout", "timed out", "rate limit", "429", "502", "503", "504", "locked", "connection")
    return any(m in msg for m in transient_markers)


class RecoveryManager:
    """Handles startup stale-job recovery and failure retry/dead-letter transitions."""

    def __init__(self, queue: PersistentQueue, stale_lock_minutes: int = 45):
        self.queue = queue
        self.stale_lock_minutes = stale_lock_minutes

    def recover_stale_jobs(self) -> int:
        return self.queue.recover_stale_locks(stale_minutes=self.stale_lock_minutes)

    def handle_job_failure(self, job_id: str, exc: Exception) -> JobStatus:
        job = self.queue.get_job(job_id)
        if not job:
            raise KeyError(f"Job not found: {job_id}")

        retryable = is_retryable_exception(exc) and job.attempt_count < job.max_attempts
        if retryable:
            if isinstance(exc, RateLimitError) and exc.retry_after_sec:
                delay = exc.retry_after_sec
            else:
                delay = compute_backoff_seconds(job.attempt_count)
            next_retry = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delay)
            ).isoformat()
            self.queue.transition_job(
                job_id,
                JobStatus.QUEUED,
                error=str(exc),
                next_retry_at=next_retry,
                permanent_failure=False,
            )
            return JobStatus.QUEUED

        self.queue.transition_job(
            job_id,
            JobStatus.FAILED,
            error=str(exc),
            permanent_failure=True,
        )
        return JobStatus.FAILED

    def manual_retry(self, job_id: str) -> JobStatus:
        with self.queue.db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE processing_jobs SET is_permanent_failure = 0, next_retry_at = NULL WHERE id = ?",
                (job_id,),
            )
        self.queue.transition_job(job_id, JobStatus.QUEUED, error=None)
        return JobStatus.QUEUED
