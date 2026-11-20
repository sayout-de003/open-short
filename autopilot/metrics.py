"""Metrics and status queries for autopilot observability."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .database import AutopilotDatabase


def collect_metrics(db: AutopilotDatabase, clips_dir: Path) -> Dict[str, Any]:
    with db.transaction() as conn:
        jobs_by_status = {
            r["status"]: r["cnt"]
            for r in conn.execute("SELECT status, COUNT(*) AS cnt FROM processing_jobs GROUP BY status").fetchall()
        }
        posts_by_status = {
            r["publication_status"]: r["cnt"]
            for r in conn.execute(
                "SELECT publication_status, COUNT(*) AS cnt FROM published_posts GROUP BY publication_status"
            ).fetchall()
        }
        sources_total = conn.execute("SELECT COUNT(*) AS cnt FROM discovered_sources").fetchone()["cnt"]
        sources_approved = conn.execute(
            "SELECT COUNT(*) AS cnt FROM discovered_sources WHERE eligible = 1"
        ).fetchone()["cnt"]
        clips_total = conn.execute("SELECT COUNT(*) AS cnt FROM rendered_clips").fetchone()["cnt"]
        clips_approved = conn.execute(
            "SELECT COUNT(*) AS cnt FROM rendered_clips WHERE quality_status = 'approved'"
        ).fetchone()["cnt"]
        latest_run = conn.execute(
            "SELECT * FROM autopilot_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

    disk_bytes = sum(f.stat().st_size for f in clips_dir.glob("*.mp4") if f.is_file()) if clips_dir.exists() else 0

    return {
        "sources_discovered": sources_total,
        "sources_approved": sources_approved,
        "sources_rejected": sources_total - sources_approved,
        "jobs_by_status": jobs_by_status,
        "clips_total": clips_total,
        "clips_approved": clips_approved,
        "posts_by_status": posts_by_status,
        "storage_bytes": disk_bytes,
        "latest_run": dict(latest_run) if latest_run else None,
    }


def list_recent_jobs(db: AutopilotDatabase, limit: int = 50) -> List[Dict[str, Any]]:
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM processing_jobs ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_recent_clips(db: AutopilotDatabase, limit: int = 50) -> List[Dict[str, Any]]:
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM rendered_clips ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
