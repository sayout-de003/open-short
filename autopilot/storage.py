"""Local media storage, public HTTPS verification, and safe cleanup lifecycle."""
from __future__ import annotations

import datetime
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

import requests

from .database import AutopilotDatabase
from .exceptions import RetryableError
from .models import PublicationStatus

logger = logging.getLogger("autopilot.storage")


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class LocalMediaStorage:
    """Manages local clip files, public URL verification, and post-publish/24h TTL cleanup."""

    def __init__(
        self,
        db: AutopilotDatabase,
        clips_dir: Path,
        temp_dir: Path,
        public_api_url: Optional[str] = None,
        retention_hours: int = 24,
        delete_after_publish: bool = True,
    ):
        self.db = db
        self.clips_dir = clips_dir
        self.temp_dir = temp_dir
        self.public_api_url = (public_api_url or "").rstrip("/")
        self.retention_hours = retention_hours
        self.delete_after_publish = delete_after_publish
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def register_approved_clip(
        self,
        job_id: str,
        moment_id: Optional[int],
        src_path: Path,
        duration_sec: float,
        width: int,
        height: int,
        file_size_bytes: int,
    ) -> str:
        """Move/copy validated MP4 into clips_dir under an unguessable clip_id and register in SQLite."""
        clip_id = f"clip_{uuid.uuid4().hex}"
        dest = self.clips_dir / f"{clip_id}.mp4"
        if src_path.resolve() != dest.resolve():
            shutil.copy2(src_path, dest)

        public_url = f"{self.public_api_url}/videos/autopilot/{clip_id}" if self.public_api_url else None
        now_iso = _utc_now().isoformat()

        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO rendered_clips (
                    id, job_id, moment_id, local_path, public_url, duration_sec,
                    width, height, aspect_ratio, file_size_bytes, quality_status,
                    quality_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '9:16', ?, 'approved', 'approved', ?)
                """,
                (
                    clip_id,
                    job_id,
                    moment_id,
                    str(dest),
                    public_url,
                    duration_sec,
                    width,
                    height,
                    file_size_bytes,
                    now_iso,
                ),
            )

        # Also sync to output/<job_id> so regular Projects directory and Editor can view/download it
        try:
            output_job_dir = Path("/root/openshort/output") / job_id
            output_job_dir.mkdir(parents=True, exist_ok=True)
            output_clip_dest = output_job_dir / f"{clip_id}.mp4"
            if not output_clip_dest.exists():
                try:
                    os.link(dest, output_clip_dest)
                except OSError:
                    shutil.copy2(dest, output_clip_dest)
            
            meta_path = output_job_dir / f"{job_id}_metadata.json"
            meta_data = {}
            if meta_path.exists():
                try:
                    meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            shorts = meta_data.get("shorts", [])
            shorts.append({
                "clip_id": clip_id,
                "video_url": f"/videos/{job_id}/{clip_id}.mp4",
                "duration": duration_sec,
                "title": f"Highlight #{len(shorts) + 1}",
                "aspect_ratio": "9:16"
            })
            meta_data["shorts"] = shorts
            meta_data["status"] = "completed"
            meta_path.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Could not sync clip to output directory: %s", e)
        return clip_id

    def verify_public_url(self, clip_id: str, timeout: int = 10) -> str:
        """Verify HTTPS GET + Byte-Range access for Buffer before marking uploaded."""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT public_url FROM rendered_clips WHERE id = ?",
                (clip_id,),
            ).fetchone()
        if not row or not row["public_url"]:
            raise RetryableError(f"No public_url configured for clip {clip_id}")

        url = row["public_url"]
        try:
            resp = requests.get(
                url,
                headers={"Range": "bytes=0-1023"},
                timeout=timeout,
                stream=True,
            )
            if resp.status_code not in (200, 206):
                raise RetryableError(f"Public media URL check returned HTTP {resp.status_code} for {url}")
        except requests.RequestException as e:
            raise RetryableError(f"Public media URL unreachable ({url}): {e}") from e

        now_iso = _utc_now().isoformat()
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE rendered_clips SET uploaded_at = ? WHERE id = ?",
                (now_iso, clip_id),
            )
        return url

    def delete_clip_if_published(self, clip_id: str) -> bool:
        """Delete local MP4 only if all associated publication records are PUBLISHED."""
        if not self.delete_after_publish:
            return False

        with self.db.transaction() as conn:
            clip = conn.execute(
                "SELECT local_path, local_deleted_at FROM rendered_clips WHERE id = ?",
                (clip_id,),
            ).fetchone()
            if not clip or clip["local_deleted_at"]:
                return False

            posts = conn.execute(
                "SELECT publication_status FROM published_posts WHERE rendered_clip_id = ?",
                (clip_id,),
            ).fetchall()
            if not posts:
                return False
            if any(p["publication_status"] != PublicationStatus.PUBLISHED.value for p in posts):
                return False

        return self._delete_local_file(clip_id, Path(clip["local_path"]), reason="published")

    def cleanup_expired_media(self) -> int:
        """Delete local clips older than retention_hours only when no active scheduled post needs them."""
        cutoff = (_utc_now() - datetime.timedelta(hours=self.retention_hours)).isoformat()
        deleted_count = 0

        with self.db.transaction() as conn:
            candidates = conn.execute(
                """
                SELECT id, local_path FROM rendered_clips
                WHERE local_deleted_at IS NULL AND created_at < ?
                """,
                (cutoff,),
            ).fetchall()

            to_delete = []
            for c in candidates:
                active = conn.execute(
                    """
                    SELECT 1 FROM published_posts
                    WHERE rendered_clip_id = ?
                      AND publication_status IN (?, ?, ?)
                    LIMIT 1
                    """,
                    (
                        c["id"],
                        PublicationStatus.PENDING_SUBMIT.value,
                        PublicationStatus.CREATED.value,
                        PublicationStatus.SCHEDULED.value,
                    ),
                ).fetchone()
                if active is None:
                    to_delete.append((c["id"], Path(c["local_path"])))

        for cid, fpath in to_delete:
            if self._delete_local_file(cid, fpath, reason="retention_expired_24h"):
                deleted_count += 1

        # Also clean stale temp files older than retention_hours
        cutoff_epoch = (_utc_now() - datetime.timedelta(hours=self.retention_hours)).timestamp()
        for item in self.temp_dir.rglob("*"):
            if item.is_file() and item.stat().st_mtime < cutoff_epoch:
                try:
                    item.unlink()
                except OSError:
                    pass

        return deleted_count

    def _delete_local_file(self, clip_id: str, fpath: Path, reason: str) -> bool:
        now_iso = _utc_now().isoformat()
        err_msg = None
        success = True
        try:
            if fpath.exists():
                fpath.unlink()
        except OSError as e:
            success = False
            err_msg = str(e)
            logger.warning("Failed deleting %s: %s", fpath, e)

        with self.db.transaction(immediate=True) as conn:
            if success:
                conn.execute(
                    "UPDATE rendered_clips SET local_deleted_at = ?, cleanup_reason = ? WHERE id = ?",
                    (now_iso, reason, clip_id),
                )
            conn.execute(
                """
                INSERT INTO cleanup_records (rendered_clip_id, file_path, reason, deleted_at, success, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clip_id, str(fpath), reason, now_iso, 1 if success else 0, err_msg),
            )
        return success
