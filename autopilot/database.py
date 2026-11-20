"""SQLite database connection, WAL configuration, and schema migrations."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS discovered_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    view_count INTEGER DEFAULT 0,
    concurrent_viewers INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    duration_sec REAL DEFAULT 0.0,
    published_at TEXT,
    game_name TEXT,
    metadata_confidence REAL DEFAULT 100.0,
    score REAL DEFAULT 0.0,
    score_breakdown_json TEXT DEFAULT '{}',
    eligible INTEGER NOT NULL DEFAULT 1,
    eligibility_reason TEXT DEFAULT 'approved',
    discovered_at TEXT NOT NULL,
    UNIQUE(platform, source_id)
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id TEXT PRIMARY KEY,
    source_pk INTEGER NOT NULL REFERENCES discovered_sources(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    source_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority REAL NOT NULL DEFAULT 0.0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_retry_at TEXT,
    locked_at TEXT,
    worker_id TEXT,
    last_error TEXT,
    is_permanent_failure INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(platform, source_id, job_type)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_priority
    ON processing_jobs(status, priority DESC, created_at ASC);

CREATE TABLE IF NOT EXISTS clip_moments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    source_id TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    moment_score REAL DEFAULT 0.0,
    fingerprint TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_moments_source
    ON clip_moments(platform, source_id, start_time, end_time);

CREATE TABLE IF NOT EXISTS rendered_clips (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    moment_id INTEGER REFERENCES clip_moments(id) ON DELETE SET NULL,
    local_path TEXT NOT NULL,
    public_url TEXT,
    duration_sec REAL NOT NULL,
    width INTEGER DEFAULT 1080,
    height INTEGER DEFAULT 1920,
    aspect_ratio TEXT DEFAULT '9:16',
    file_size_bytes INTEGER DEFAULT 0,
    quality_status TEXT NOT NULL DEFAULT 'pending',
    quality_reason TEXT,
    uploaded_at TEXT,
    local_deleted_at TEXT,
    cleanup_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS published_posts (
    id TEXT PRIMARY KEY,
    rendered_clip_id TEXT NOT NULL REFERENCES rendered_clips(id) ON DELETE CASCADE,
    buffer_channel_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    buffer_post_id TEXT,
    publication_status TEXT NOT NULL,
    title TEXT,
    caption TEXT,
    scheduled_at TEXT,
    published_at TEXT,
    last_checked_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(rendered_clip_id, buffer_channel_id)
);

CREATE TABLE IF NOT EXISTS daily_quotas (
    quota_date TEXT NOT NULL,
    buffer_channel_id TEXT NOT NULL,
    posts_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(quota_date, buffer_channel_id)
);

CREATE TABLE IF NOT EXISTS autopilot_runs (
    id TEXT PRIMARY KEY,
    query TEXT,
    status TEXT NOT NULL,
    sources_discovered INTEGER DEFAULT 0,
    sources_approved INTEGER DEFAULT 0,
    sources_rejected INTEGER DEFAULT 0,
    clips_generated INTEGER DEFAULT 0,
    clips_approved INTEGER DEFAULT 0,
    posts_scheduled INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS source_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    policy TEXT NOT NULL, -- 'allow' | 'deny'
    reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(platform, channel_id)
);

CREATE TABLE IF NOT EXISTS cleanup_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rendered_clip_id TEXT REFERENCES rendered_clips(id) ON DELETE SET NULL,
    file_path TEXT NOT NULL,
    reason TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    error TEXT
);
"""


class AutopilotDatabase:
    """Thread-safe SQLite wrapper using WAL mode and explicit transactions."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE;" if immediate else "BEGIN;")
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            try:
                conn.execute("ROLLBACK;")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(SCHEMA_SQL)
        finally:
            conn.close()
