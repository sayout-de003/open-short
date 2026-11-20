"""Persistent SQLite job queue with atomic claiming, state validation, and 3-level deduplication."""
from __future__ import annotations

import datetime
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from gaming_intelligence.deduplication import compute_moment_fingerprint, is_duplicate_moment

from .database import AutopilotDatabase
from .models import DiscoveredSource, JobStatus, ProcessingJob, PublicationStatus, validate_transition


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _utc_iso(dt: Optional[datetime.datetime] = None) -> str:
    return (dt or _utc_now()).isoformat()


class PersistentQueue:
    """Manages sources, jobs, moments, clips, publications, and daily quotas in SQLite."""

    def __init__(self, db: AutopilotDatabase):
        self.db = db

    # --- Level 1: Source & Job Enqueue ---

    def register_source_and_enqueue(
        self,
        source: DiscoveredSource,
        job_type: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Optional[str]:
        """Insert source + QUEUED job atomically. Returns job_id, or None if duplicate/ineligible."""
        now_iso = _utc_iso()
        jtype = job_type or source.source_type
        with self.db.transaction(immediate=True) as conn:
            existing = conn.execute(
                "SELECT id FROM discovered_sources WHERE platform = ? AND source_id = ?",
                (source.platform, source.source_id),
            ).fetchone()
            if existing is not None:
                return None

            cur = conn.execute(
                """
                INSERT INTO discovered_sources (
                    platform, source_id, source_type, url, title, channel_id, channel_name,
                    view_count, concurrent_viewers, like_count, comment_count, duration_sec,
                    published_at, game_name, metadata_confidence, score, score_breakdown_json,
                    eligible, eligibility_reason, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.platform,
                    source.source_id,
                    source.source_type,
                    source.url,
                    source.title,
                    source.channel_id,
                    source.channel_name,
                    source.view_count,
                    source.concurrent_viewers,
                    source.like_count,
                    source.comment_count,
                    source.duration_sec,
                    source.published_at,
                    source.game_name,
                    source.metadata_confidence,
                    source.score,
                    json.dumps(source.score_breakdown),
                    1 if source.eligible else 0,
                    source.eligibility_reason,
                    now_iso,
                ),
            )
            source_pk = cur.lastrowid

            if not source.eligible:
                return None

            job_id = f"job_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO processing_jobs (
                    id, source_pk, platform, source_id, job_type, status, priority,
                    attempt_count, max_attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    job_id,
                    source_pk,
                    source.platform,
                    source.source_id,
                    jtype,
                    JobStatus.QUEUED.value,
                    source.score,
                    max_attempts,
                    now_iso,
                    now_iso,
                ),
            )
            return job_id

    # --- Atomic Job Claiming & State Transitions ---

    def claim_next_job(self, worker_id: str, job_type: Optional[str] = None) -> Optional[ProcessingJob]:
        """Atomically claim the highest-priority ready QUEUED job."""
        now_iso = _utc_iso()
        with self.db.transaction(immediate=True) as conn:
            type_clause = "AND job_type = ?" if job_type else ""
            params: List[Any] = [JobStatus.QUEUED.value, now_iso]
            if job_type:
                params.append(job_type)

            row = conn.execute(
                f"""
                SELECT * FROM processing_jobs
                WHERE status = ?
                  AND is_permanent_failure = 0
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                  {type_clause}
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                params,
            ).fetchone()

            if row is None:
                return None

            validate_transition(row["status"], JobStatus.PROCESSING)
            updated = conn.execute(
                """
                UPDATE processing_jobs
                SET status = ?, locked_at = ?, worker_id = ?, attempt_count = attempt_count + 1, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    JobStatus.PROCESSING.value,
                    now_iso,
                    worker_id,
                    now_iso,
                    row["id"],
                    JobStatus.QUEUED.value,
                ),
            )
            if updated.rowcount != 1:
                return None

            claimed = conn.execute("SELECT * FROM processing_jobs WHERE id = ?", (row["id"],)).fetchone()
            return self._row_to_job(claimed)

    def transition_job(
        self,
        job_id: str,
        target_status: JobStatus,
        error: Optional[str] = None,
        next_retry_at: Optional[str] = None,
        permanent_failure: bool = False,
    ) -> ProcessingJob:
        """Validate and persist a job state transition."""
        now_iso = _utc_iso()
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")

            nxt = validate_transition(row["status"], target_status)
            completed_at = now_iso if nxt == JobStatus.PUBLISHED else row["completed_at"]
            locked_at = None if nxt != JobStatus.PROCESSING else row["locked_at"]
            worker_id = None if nxt != JobStatus.PROCESSING else row["worker_id"]

            conn.execute(
                """
                UPDATE processing_jobs
                SET status = ?, last_error = ?, next_retry_at = ?, locked_at = ?, worker_id = ?,
                    is_permanent_failure = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    nxt.value,
                    error,
                    next_retry_at,
                    locked_at,
                    worker_id,
                    1 if permanent_failure else row["is_permanent_failure"],
                    now_iso,
                    completed_at,
                    job_id,
                ),
            )
            updated = conn.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job(updated)

    def recover_stale_locks(self, stale_minutes: int = 45) -> int:
        """Return jobs stuck in PROCESSING longer than stale_minutes back to QUEUED."""
        cutoff = (_utc_now() - datetime.timedelta(minutes=stale_minutes)).isoformat()
        now_iso = _utc_iso()
        with self.db.transaction(immediate=True) as conn:
            res = conn.execute(
                """
                UPDATE processing_jobs
                SET status = ?, locked_at = NULL, worker_id = NULL,
                    last_error = COALESCE(last_error, 'Recovered from stale PROCESSING lock'),
                    updated_at = ?
                WHERE status = ? AND locked_at IS NOT NULL AND locked_at < ?
                """,
                (JobStatus.QUEUED.value, now_iso, JobStatus.PROCESSING.value, cutoff),
            )
            return res.rowcount

    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job(row) if row else None

    # --- Level 2: Moment Deduplication ---

    def record_moment_if_unique(
        self,
        job_id: str,
        platform: str,
        source_id: str,
        start_time: float,
        end_time: float,
        moment_score: float = 0.0,
        reason: str = "",
        fingerprint: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a moment if it does not overlap/match an existing moment for (platform, source_id)."""
        fp = fingerprint or compute_moment_fingerprint(platform, source_id, start_time, end_time)
        now_iso = _utc_iso()
        with self.db.transaction(immediate=True) as conn:
            rows = conn.execute(
                "SELECT start_time, end_time, fingerprint FROM clip_moments WHERE platform = ? AND source_id = ?",
                (platform, source_id),
            ).fetchall()
            existing = [(r["start_time"], r["end_time"], r["fingerprint"]) for r in rows]
            if is_duplicate_moment(start_time, end_time, existing, fingerprint=fp):
                return None

            cur = conn.execute(
                """
                INSERT INTO clip_moments (
                    job_id, platform, source_id, start_time, end_time, moment_score, fingerprint, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, platform, source_id, start_time, end_time, moment_score, fp, reason, now_iso),
            )
            return cur.lastrowid

    # --- Level 3: Publication Deduplication & Quotas ---

    def create_publication_attempt(
        self,
        rendered_clip_id: str,
        buffer_channel_id: str,
        platform: str,
        title: str,
        caption: str,
        scheduled_at: Optional[str],
    ) -> Optional[str]:
        """Insert a PENDING_SUBMIT publication attempt; returns pub_id or None if duplicate."""
        pub_id = f"pub_{uuid.uuid4().hex[:12]}"
        op_id = f"op_{uuid.uuid4().hex[:16]}"
        now_iso = _utc_iso()
        try:
            with self.db.transaction(immediate=True) as conn:
                conn.execute(
                    """
                    INSERT INTO published_posts (
                        id, rendered_clip_id, buffer_channel_id, platform, operation_id,
                        publication_status, title, caption, scheduled_at, attempt_count,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        pub_id,
                        rendered_clip_id,
                        buffer_channel_id,
                        platform,
                        op_id,
                        PublicationStatus.PENDING_SUBMIT.value,
                        title,
                        caption,
                        scheduled_at,
                        now_iso,
                        now_iso,
                    ),
                )
            return pub_id
        except sqlite3.IntegrityError:
            return None

    def get_daily_quota_count(self, quota_date: str, buffer_channel_id: str) -> int:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT posts_count FROM daily_quotas WHERE quota_date = ? AND buffer_channel_id = ?",
                (quota_date, buffer_channel_id),
            ).fetchone()
            return int(row["posts_count"]) if row else 0

    def increment_daily_quota(self, quota_date: str, buffer_channel_id: str) -> int:
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO daily_quotas (quota_date, buffer_channel_id, posts_count)
                VALUES (?, ?, 1)
                ON CONFLICT(quota_date, buffer_channel_id)
                DO UPDATE SET posts_count = posts_count + 1
                """,
                (quota_date, buffer_channel_id),
            )
            row = conn.execute(
                "SELECT posts_count FROM daily_quotas WHERE quota_date = ? AND buffer_channel_id = ?",
                (quota_date, buffer_channel_id),
            ).fetchone()
            return int(row["posts_count"])

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> ProcessingJob:
        return ProcessingJob(
            id=row["id"],
            source_pk=row["source_pk"],
            platform=row["platform"],
            source_id=row["source_id"],
            job_type=row["job_type"],
            status=JobStatus(row["status"]),
            priority=float(row["priority"]),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            next_retry_at=row["next_retry_at"],
            locked_at=row["locked_at"],
            worker_id=row["worker_id"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )
