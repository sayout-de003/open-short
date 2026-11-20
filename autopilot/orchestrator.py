"""Fault-tolerant autopilot orchestrator coordinating discovery, workers, storage, and Buffer."""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional

from gaming_intelligence.discovery import TwitchDiscoveryAdapter, YouTubeDiscoveryAdapter
from gaming_intelligence.ranking import rank_candidates

from .config import AutopilotConfig, configure_logging
from .database import AutopilotDatabase
from .eligibility import EligibilityGate
from .metrics import collect_metrics
from .models import DiscoveredSource, JobStatus
from .publisher import BufferAutopilotPublisher
from .quality import ClipQualityValidator
from .queue import PersistentQueue
from .recovery import RecoveryManager
from .storage import LocalMediaStorage
from .workers import LiveWorker, VODWorker

logger = logging.getLogger("autopilot.orchestrator")


def _utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class AutopilotOrchestrator:
    """Coordinates all independent, recoverable stages of the gaming autopilot."""

    def __init__(self, config: AutopilotConfig):
        self.config = config
        configure_logging(config.logs_dir)
        self.db = AutopilotDatabase(config.database_path)
        self.queue = PersistentQueue(self.db)
        self.eligibility = EligibilityGate(self.db)
        self.quality = ClipQualityValidator(
            min_duration=float(config.clip_min_duration),
            max_duration=float(config.clip_max_duration),
        )
        self.storage = LocalMediaStorage(
            db=self.db,
            clips_dir=config.clips_dir,
            temp_dir=config.temp_dir,
            public_api_url=config.public_api_url,
            retention_hours=config.clip_retention_hours,
            delete_after_publish=config.delete_clip_after_publish,
        )
        self.recovery = RecoveryManager(self.queue, stale_lock_minutes=config.stale_lock_minutes)
        self.publisher = BufferAutopilotPublisher(
            db=self.db,
            queue=self.queue,
            storage=self.storage,
            platforms=config.buffer_platforms,
            posts_per_channel_per_day=config.buffer_posts_per_channel_per_day,
            retention_hours=config.clip_retention_hours,
            buffer_token=config.buffer_access_token,
        )
        self.vod_worker = VODWorker(config, self.queue, self.quality, self.storage)
        self.live_worker = LiveWorker(config, self.queue, self.quality, self.storage)
        self._paused = False

    def discover_and_rank(self, query: Optional[str] = None) -> List[DiscoveredSource]:
        """Discover from enabled YouTube & Twitch adapters, check eligibility, and rank."""
        queries = [query] if query else list(self.config.gaming_categories)
        raw: List[DiscoveredSource] = []

        yt = YouTubeDiscoveryAdapter(api_key=self.config.youtube_api_key) if self.config.youtube_discovery_enabled else None
        tw = (
            TwitchDiscoveryAdapter(self.config.twitch_client_id, self.config.twitch_client_secret)
            if (self.config.twitch_discovery_enabled and self.config.twitch_client_id and self.config.twitch_client_secret)
            else None
        )

        for q in queries:
            if yt:
                try:
                    raw.extend(yt.discover(q, limit=self.config.discovery_top_n, max_age_hours=self.config.discovery_max_age_hours))
                except Exception as e:
                    logger.warning("YouTube discovery failed for %r: %s", q, e)
            if tw:
                try:
                    raw.extend(tw.discover(q, limit=self.config.discovery_top_n))
                except Exception as e:
                    logger.warning("Twitch discovery failed for %r: %s", q, e)

        for src in raw:
            self.eligibility.apply(src)

        return rank_candidates(raw, max_age_hours=self.config.discovery_max_age_hours, top_n=self.config.discovery_top_n)

    def run_once(
        self,
        query: Optional[str] = None,
        dry_run: bool = False,
        max_vods: Optional[int] = None,
        max_live: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute one full, crash-recoverable autopilot cycle."""
        self.config.validate(require_publish=not dry_run, require_discovery=False)
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        started_at = _utc_iso()

        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                "INSERT INTO autopilot_runs (id, query, status, started_at) VALUES (?, ?, 'running', ?)",
                (run_id, query or ",".join(self.config.gaming_categories), started_at),
            )

        stats: Dict[str, Any] = {
            "run_id": run_id,
            "dry_run": dry_run,
            "recovered_stale": 0,
            "reconciled": {},
            "cleaned_expired": 0,
            "discovered": 0,
            "enqueued": 0,
            "clips_approved": 0,
            "posts_scheduled": 0,
        }

        try:
            stats["recovered_stale"] = self.recovery.recover_stale_jobs()
            if not dry_run and self.config.buffer_enabled and self.config.buffer_access_token:
                stats["reconciled"] = self.publisher.reconcile_pending_posts()
            stats["cleaned_expired"] = self.storage.cleanup_expired_media()

            candidates = self.discover_and_rank(query=query)
            stats["discovered"] = len(candidates)

            if dry_run:
                stats["candidates"] = [
                    {
                        "platform": c.platform,
                        "source_id": c.source_id,
                        "type": c.source_type,
                        "score": c.score,
                        "eligible": c.eligible,
                        "title": c.title,
                    }
                    for c in candidates
                ]
                self._finish_run(run_id, "completed", stats)
                return stats

            if self._paused:
                self._finish_run(run_id, "paused", stats)
                return stats

            for c in candidates:
                jid = self.queue.register_source_and_enqueue(c, max_attempts=self.config.max_job_attempts)
                if jid:
                    stats["enqueued"] += 1

            vod_limit = self.config.max_vods_per_run if max_vods is None else max_vods
            live_limit = self.config.max_live_streams if max_live is None else max_live
            clips_budget = self.config.max_clips_per_day

            for _ in range(vod_limit):
                if stats["clips_approved"] >= clips_budget:
                    break
                job = self.queue.claim_next_job(worker_id=run_id, job_type="vod")
                if not job:
                    break
                approved, scheduled = self._execute_job(job, is_live=False)
                stats["clips_approved"] += approved
                stats["posts_scheduled"] += scheduled

            if self.config.live_capture_enabled:
                for _ in range(live_limit):
                    if stats["clips_approved"] >= clips_budget:
                        break
                    job = self.queue.claim_next_job(worker_id=run_id, job_type="live")
                    if not job:
                        break
                    approved, scheduled = self._execute_job(job, is_live=True)
                    stats["clips_approved"] += approved
                    stats["posts_scheduled"] += scheduled

            self._finish_run(run_id, "completed", stats)
            return stats
        except Exception as e:
            self._finish_run(run_id, "failed", stats, error=str(e))
            raise

    def _execute_job(self, job, is_live: bool) -> tuple[int, int]:
        try:
            clip_ids = (
                self.live_worker.process_job(job)
                if is_live
                else self.vod_worker.process_job(job)
            )
            scheduled_count = 0
            with self.db.transaction() as conn:
                src = conn.execute(
                    "SELECT title, channel_name, game_name FROM discovered_sources WHERE id = ?",
                    (job.source_pk,),
                ).fetchone()

            verified_urls: List[tuple[str, str]] = []
            for cid in clip_ids:
                verified_urls.append((cid, self.storage.verify_public_url(cid)))
            self.queue.transition_job(job.id, JobStatus.UPLOADED)

            for idx, (cid, url) in enumerate(verified_urls):
                # 1. Direct YouTube Shorts auto-post if configured
                try:
                    import youtube_publisher
                    if youtube_publisher.is_direct_youtube_configured():
                        with self.db.transaction() as conn:
                            clip_row = conn.execute("SELECT local_path FROM rendered_clips WHERE id = ?", (cid,)).fetchone()
                        if clip_row and os.path.exists(clip_row["local_path"]):
                            yt_title = f"{src['title'][:60]} #Shorts" if src else "Gaming Highlight #Shorts"
                            yt_desc = f"Best gaming clip from {src['channel_name'] if src else 'Streamer'}!\n\n#gaming #shorts #viral #reels"
                            yt_res = youtube_publisher.upload_video_to_youtube(
                                file_path=clip_row["local_path"],
                                title=yt_title,
                                description=yt_desc,
                                tags=["gaming", "shorts", "viral", (src["game_name"] if src and src["game_name"] else "gaming")]
                            )
                            if yt_res.get("success"):
                                scheduled_count += 1
                                post_id = f"post_{uuid.uuid4().hex[:12]}"
                                with self.db.transaction() as conn:
                                    conn.execute("""
                                        INSERT OR REPLACE INTO published_posts 
                                        (id, rendered_clip_id, buffer_channel_id, platform, operation_id, buffer_post_id, publication_status, published_at, created_at, updated_at)
                                        VALUES (?, ?, 'youtube_direct', 'youtube', ?, ?, 'sent', datetime('now'), datetime('now'), datetime('now'))
                                    """, (post_id, cid, yt_res.get("video_id", post_id), yt_res.get("video_id")))
                            elif yt_res.get("quota_exceeded"):
                                logger.warning("YouTube 10k quota reached for today. Clip %s saved locally for manual download/posting.", cid)
                except Exception as ex:
                    logger.warning("Direct YouTube auto-publish failed for clip %s (clip preserved on disk): %s", cid, ex)

                # 2. Buffer auto-post if enabled
                if self.config.buffer_enabled and self.config.buffer_access_token:
                    try:
                        res = self.publisher.publish_clip(
                            clip_id=cid,
                            public_url=url,
                            source_title=src["title"] if src else "Gaming Highlight",
                            channel_name=src["channel_name"] if src else "Creator",
                            game_name=src["game_name"] if src else None,
                            slot_index=idx,
                        )
                        scheduled_count += sum(1 for r in res if "buffer_post_id" in r)
                    except Exception as e:
                        logger.warning("Buffer publish skipped/failed for %s (clip safe on disk): %s", cid, e)

            self.queue.transition_job(job.id, JobStatus.SCHEDULED)
            return len(clip_ids), scheduled_count
        except Exception as exc:
            self.recovery.handle_job_failure(job.id, exc)
            logger.error("Job %s failed: %s", job.id, exc)
            return 0, 0

    def process_job_by_id(self, job_id: str) -> tuple[int, int]:
        """Atomically claim and immediately execute a specific enqueued job."""
        run_id = f"manual_{uuid.uuid4().hex[:8]}"
        job = self.queue.claim_job_by_id(job_id, worker_id=run_id)
        if not job:
            logger.info("Job %s could not be claimed (already processing or missing)", job_id)
            return 0, 0
        is_live = (job.job_type in ("live", "live_stream"))
        return self._execute_job(job, is_live=is_live)

    def delete_job(self, job_id: str) -> bool:
        """Remove a job from the database."""
        return self.queue.delete_job(job_id)

    def _finish_run(self, run_id: str, status: str, stats: Dict[str, Any], error: Optional[str] = None) -> None:
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                UPDATE autopilot_runs
                SET status = ?, sources_discovered = ?, clips_approved = ?, posts_scheduled = ?,
                    finished_at = ?, error = ?
                WHERE id = ?
                """,
                (
                    status,
                    stats.get("discovered", 0),
                    stats.get("clips_approved", 0),
                    stats.get("posts_scheduled", 0),
                    _utc_iso(),
                    error,
                    run_id,
                ),
            )

    def status(self) -> Dict[str, Any]:
        return collect_metrics(self.db, self.config.clips_dir)
