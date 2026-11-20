"""Buffer publishing, per-channel daily quotas, idempotency, and status reconciliation."""
from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

import buffer_publisher
import scheduler

from .database import AutopilotDatabase
from .exceptions import RetryableError
from .models import PublicationStatus
from .queue import PersistentQueue
from .storage import LocalMediaStorage

logger = logging.getLogger("autopilot.publisher")


def build_platform_metadata(
    platform: str,
    source_title: str,
    channel_name: str,
    game_name: Optional[str] = None,
) -> Dict[str, str]:
    """Generate platform-adapted title and caption with creator attribution."""
    game_tag = f"#{game_name.replace(' ', '')}" if game_name else "#Gaming"
    clean_title = (source_title or "Insane Gaming Moment").strip()

    if platform.lower() == "youtube":
        yt_title = f"{clean_title[:75]} #Shorts"
        yt_desc = (
            f"{clean_title}\n\n"
            f"Creator: {channel_name}\n"
            f"{game_tag} #Shorts #GamingClips"
        )
        return {"title": yt_title[:100], "caption": yt_desc}

    # Instagram Reels
    ig_caption = (
        f"{clean_title[:120]}\n\n"
        f"Via: {channel_name}\n"
        f"{game_tag} #Reels #Gaming #GamingHighlights #Clips"
    )
    return {"title": clean_title[:60], "caption": ig_caption}


def fetch_buffer_post_status(post_id: str, token: Optional[str] = None) -> Optional[str]:
    """Query Buffer GraphQL for a post's current status (e.g. sent/scheduled/error)."""
    query = """
    query GetPost($id: PostId!) {
      post(id: $id) {
        id
        status
        sentAt
      }
    }
    """
    data = buffer_publisher.execute_graphql(query, variables={"id": post_id}, token=token)
    post = data.get("post") or {}
    return post.get("status")


class BufferAutopilotPublisher:
    """Schedules approved clips to Buffer YouTube & Instagram channels with quotas and idempotency."""

    def __init__(
        self,
        db: AutopilotDatabase,
        queue: PersistentQueue,
        storage: LocalMediaStorage,
        platforms: List[str],
        posts_per_channel_per_day: int = 2,
        retention_hours: int = 24,
        buffer_token: Optional[str] = None,
    ):
        self.db = db
        self.queue = queue
        self.storage = storage
        self.platforms = [p.lower().strip() for p in platforms]
        self.posts_per_channel_per_day = posts_per_channel_per_day
        self.retention_hours = retention_hours
        self.buffer_token = buffer_token

    def get_active_channels(self) -> List[Dict[str, Any]]:
        all_channels = buffer_publisher.list_channels(token=self.buffer_token)
        return buffer_publisher.filter_channels_for_services(all_channels, self.platforms)

    def publish_clip(
        self,
        clip_id: str,
        public_url: str,
        source_title: str,
        channel_name: str,
        game_name: Optional[str] = None,
        slot_index: int = 0,
    ) -> List[Dict[str, Any]]:
        """Schedule clip across eligible Buffer channels respecting daily per-channel quotas."""
        channels = self.get_active_channels()
        if not channels:
            logger.warning("No active Buffer channels matched %s", self.platforms)
            return []

        now = datetime.datetime.now(datetime.timezone.utc)
        today_str = now.date().isoformat()
        # Keep due_at inside the local retention window (max retention_hours - 2h buffer)
        max_offset_hours = max(1.0, float(self.retention_hours - 2))
        schedule_dts = scheduler.generate_smart_jitter_schedule(
            clip_count=slot_index + 1,
            posts_per_day=max(1, self.posts_per_channel_per_day),
            jitter_seed=clip_id,
        )
        due_dt = schedule_dts[-1]
        if (due_dt - now).total_seconds() > max_offset_hours * 3600:
            due_dt = now + datetime.timedelta(minutes=30 + slot_index * 45)
        due_iso = due_dt.isoformat()

        results: List[Dict[str, Any]] = []
        for ch in channels:
            ch_id = ch["id"]
            service = (ch.get("service") or "").lower()

            if self.queue.get_daily_quota_count(today_str, ch_id) >= self.posts_per_channel_per_day:
                results.append({"channel_id": ch_id, "service": service, "skipped": "daily_quota_reached"})
                continue

            meta = build_platform_metadata(service, source_title, channel_name, game_name)
            pub_id = self.queue.create_publication_attempt(
                rendered_clip_id=clip_id,
                buffer_channel_id=ch_id,
                platform=service,
                title=meta["title"],
                caption=meta["caption"],
                scheduled_at=due_iso,
            )
            if pub_id is None:
                results.append({"channel_id": ch_id, "service": service, "skipped": "duplicate_publication"})
                continue

            try:
                res = buffer_publisher.create_post(
                    channel_id=ch_id,
                    text=meta["caption"],
                    video_url=public_url,
                    mode="customScheduled",
                    due_at=due_iso,
                    service=service,
                    title=meta["title"],
                    token=self.buffer_token,
                )
                post_obj = res.get("post") or {}
                buf_post_id = post_obj.get("id")
                buf_status = (post_obj.get("status") or "").lower()
                pub_status = (
                    PublicationStatus.PUBLISHED.value
                    if buf_status == "sent"
                    else PublicationStatus.SCHEDULED.value
                )
                self._update_publication(
                    pub_id,
                    publication_status=pub_status,
                    buffer_post_id=buf_post_id,
                    published_at=post_obj.get("sentAt"),
                )
                self.queue.increment_daily_quota(today_str, ch_id)
                results.append({
                    "channel_id": ch_id,
                    "service": service,
                    "pub_id": pub_id,
                    "buffer_post_id": buf_post_id,
                    "status": pub_status,
                })
            except Exception as e:
                self._update_publication(pub_id, publication_status=PublicationStatus.FAILED.value, last_error=str(e))
                raise RetryableError(f"Buffer create_post failed for {ch_id}: {e}") from e

        return results

    def reconcile_pending_posts(self) -> Dict[str, int]:
        """Poll Buffer for SCHEDULED/CREATED posts, update PUBLISHED status, and delete safe local files."""
        checked = 0
        published = 0
        cleaned = 0

        with self.db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, rendered_clip_id, buffer_post_id, publication_status
                FROM published_posts
                WHERE buffer_post_id IS NOT NULL
                  AND publication_status IN (?, ?)
                """,
                (PublicationStatus.CREATED.value, PublicationStatus.SCHEDULED.value),
            ).fetchall()

        for row in rows:
            checked += 1
            try:
                status = (fetch_buffer_post_status(row["buffer_post_id"], token=self.buffer_token) or "").lower()
            except Exception as e:
                logger.warning("Failed reconciling post %s: %s", row["buffer_post_id"], e)
                continue

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if status == "sent":
                self._update_publication(
                    row["id"],
                    publication_status=PublicationStatus.PUBLISHED.value,
                    published_at=now_iso,
                    last_checked_at=now_iso,
                )
                published += 1
                if self.storage.delete_clip_if_published(row["rendered_clip_id"]):
                    cleaned += 1
            elif status in ("error", "failed"):
                self._update_publication(
                    row["id"],
                    publication_status=PublicationStatus.FAILED.value,
                    last_checked_at=now_iso,
                    last_error=f"Buffer reported status: {status}",
                )
            else:
                self._update_publication(
                    row["id"],
                    publication_status=row["publication_status"],
                    last_checked_at=now_iso,
                )

        return {"checked": checked, "published": published, "cleaned": cleaned}

    def _update_publication(
        self,
        pub_id: str,
        publication_status: str,
        buffer_post_id: Optional[str] = None,
        published_at: Optional[str] = None,
        last_checked_at: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> None:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                UPDATE published_posts
                SET publication_status = ?,
                    buffer_post_id = COALESCE(?, buffer_post_id),
                    published_at = COALESCE(?, published_at),
                    last_checked_at = COALESCE(?, last_checked_at),
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    publication_status,
                    buffer_post_id,
                    published_at,
                    last_checked_at,
                    last_error,
                    now_iso,
                    pub_id,
                ),
            )
