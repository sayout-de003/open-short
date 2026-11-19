"""Persistent Scheduler & Auto-Post Engine for OpenShorts.

Schedules individual clips or entire projects for automated publishing to YouTube Shorts
and other social platforms at specified dates and times.

Storage:
    /root/openshort/output/.scheduled_posts.json
"""

import asyncio
import datetime
import hashlib
import json
import os
import time
import uuid
from typing import Dict, Any, List, Optional

SCHEDULE_FILE = "/root/openshort/output/.scheduled_posts.json"
_scheduler_task = None

# Peak engagement time windows (UTC): Morning, Afternoon, Evening
PEAK_WINDOWS = [
    (10, 0),   # Window 1: Morning ~10:00 AM UTC
    (15, 0),   # Window 2: Afternoon ~03:00 PM UTC
    (19, 30),  # Window 3: Evening ~07:30 PM UTC
]


def generate_smart_jitter_schedule(
    clip_count: int,
    start_time: Optional[str] = None,
    posts_per_day: int = 1,
    jitter_seed: Optional[str] = None,
) -> List[datetime.datetime]:
    """Generate dynamic, varied schedule timestamps rotating across peak engagement windows with natural jitter.
    
    Ensures posts do not go out at identical times everyday, cycling through high-engagement
    windows with +/- 20 to 25 minutes of organic jitter.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    posts_per_day = max(1, posts_per_day)

    if start_time:
        try:
            base_dt = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            base_dt = now + datetime.timedelta(hours=1)
    else:
        base_dt = now + datetime.timedelta(hours=1)

    timestamps = []
    base_day = base_dt.date()

    for i in range(clip_count):
        day_offset = i // posts_per_day
        slot_in_day = i % posts_per_day
        # Cycle through peak windows so day n has a different slot than day n+1
        window_idx = (day_offset * 2 + slot_in_day) % len(PEAK_WINDOWS)

        hour, minute = PEAK_WINDOWS[window_idx]
        target_date = base_day + datetime.timedelta(days=day_offset)

        # Deterministic organic jitter based on seed and index
        seed_str = f"{jitter_seed or 'openshort'}_{i}_{day_offset}"
        seed_val = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:6], 16)
        jitter_minutes = (seed_val % 45) - 20   # -20 to +24 minutes
        jitter_seconds = seed_val % 60

        scheduled_dt = datetime.datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            jitter_seconds,
            tzinfo=datetime.timezone.utc,
        ) + datetime.timedelta(minutes=jitter_minutes)

        if scheduled_dt <= now:
            scheduled_dt = now + datetime.timedelta(minutes=15 + (i * 30))

        timestamps.append(scheduled_dt)

    return timestamps


def _load_schedules() -> List[Dict[str, Any]]:
    if not os.path.exists(SCHEDULE_FILE):
        return []
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error reading {SCHEDULE_FILE}: {e}")
        return []


def _save_schedules(posts: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(SCHEDULE_FILE), exist_ok=True)
    temp_file = f"{SCHEDULE_FILE}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)
    os.replace(temp_file, SCHEDULE_FILE)


def schedule_clip_post(
    job_id: str,
    clip_index: int,
    scheduled_at: str,
    platforms: Optional[List[str]] = None,
    provider: Optional[str] = "auto",
    buffer_channels: Optional[List[str]] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    privacy_status: Optional[str] = "public",
    scheduling_mode: Optional[str] = "smart_jitter",
) -> Dict[str, Any]:
    """Schedule a specific clip to be auto-posted at scheduled_at (ISO datetime string)."""
    # Parse and validate datetime
    try:
        dt = datetime.datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
    except Exception as e:
        raise ValueError(f"Invalid scheduled_at datetime format: {scheduled_at} ({e})")

    posts = _load_schedules()

    # Remove existing pending schedule for this exact clip if present
    posts = [
        p for p in posts
        if not (p.get("job_id") == job_id and p.get("clip_index") == clip_index and p.get("status") == "pending")
    ]

    post_id = f"sched_{uuid.uuid4().hex[:8]}"
    entry = {
        "id": post_id,
        "job_id": job_id,
        "clip_index": clip_index,
        "scheduled_at": dt.isoformat(),
        "platforms": platforms or ["instagram", "youtube"],
        "provider": provider or "auto",
        "buffer_channels": buffer_channels or [],
        "title": title,
        "description": description,
        "privacy_status": privacy_status or "public",
        "scheduling_mode": scheduling_mode or "smart_jitter",
        "status": "pending",
        "created_at": time.time(),
        "result": None,
        "error": None,
    }
    posts.append(entry)
    _save_schedules(posts)
    print(f"📅 [Scheduler] Scheduled clip {clip_index} of {job_id} for auto-posting at {dt.isoformat()} (provider: {provider}, mode: {scheduling_mode})")
    return entry


def auto_schedule_project(
    job_id: str,
    clips: List[Dict[str, Any]],
    start_time: Optional[str] = None,
    interval_hours: float = 4.0,
    scheduling_mode: str = "smart_jitter",
    posts_per_day: int = 1,
    platforms: Optional[List[str]] = None,
    provider: Optional[str] = "auto",
    buffer_channels: Optional[List[str]] = None,
    privacy_status: str = "public",
) -> List[Dict[str, Any]]:
    """Automatically schedule all clips in a project spaced out across days/hours with varied times or buffer queue."""
    if not clips:
        return []

    target_platforms = platforms or ["instagram", "youtube"]
    now = datetime.datetime.now(datetime.timezone.utc)

    if scheduling_mode == "smart_jitter":
        schedule_times = generate_smart_jitter_schedule(
            clip_count=len(clips),
            start_time=start_time,
            posts_per_day=posts_per_day,
            jitter_seed=job_id,
        )
    elif scheduling_mode == "buffer_queue":
        # Queue directly to Buffer's native calendar sequence
        schedule_times = [now + datetime.timedelta(seconds=5 * i) for i in range(len(clips))]
    else:
        # Standard fixed interval mode
        if start_time:
            try:
                base_dt = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except Exception:
                base_dt = now + datetime.timedelta(minutes=10)
        else:
            base_dt = now + datetime.timedelta(minutes=15)
        schedule_times = [base_dt + datetime.timedelta(hours=i * interval_hours) for i in range(len(clips))]

    scheduled_entries = []
    for i, clip in enumerate(clips):
        clip_time = schedule_times[i] if i < len(schedule_times) else (now + datetime.timedelta(hours=i * interval_hours))
        clip_title = clip.get("video_title_for_youtube_short") or clip.get("title") or f"Short #{i+1}"
        clip_desc = (
            clip.get("video_description_for_instagram")
            or clip.get("video_description_for_tiktok")
            or clip_title
        )
        entry = schedule_clip_post(
            job_id=job_id,
            clip_index=i,
            scheduled_at=clip_time.isoformat(),
            platforms=target_platforms,
            provider=provider or "auto",
            buffer_channels=buffer_channels,
            title=clip_title,
            description=clip_desc,
            privacy_status=privacy_status,
            scheduling_mode=scheduling_mode,
        )
        scheduled_entries.append(entry)

    print(f"🚀 [Scheduler] Auto-scheduled {len(scheduled_entries)} clips for job {job_id} (mode: {scheduling_mode}, platforms: {target_platforms})")
    return scheduled_entries


def list_schedules(job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all scheduled posts, optionally filtered by job_id."""
    posts = _load_schedules()
    if job_id:
        return [p for p in posts if p.get("job_id") == job_id]
    return posts


def cancel_schedule(post_id: str) -> bool:
    """Cancel a scheduled post by ID."""
    posts = _load_schedules()
    initial_len = len(posts)
    posts = [p for p in posts if p.get("id") != post_id]
    if len(posts) < initial_len:
        _save_schedules(posts)
        print(f"🗑️ [Scheduler] Cancelled schedule {post_id}")
        return True
    return False


async def execute_due_posts(app_module):
    """Check and execute any posts whose scheduled_at has arrived."""
    posts = _load_schedules()
    now = datetime.datetime.now(datetime.timezone.utc)
    updated = False

    for post in posts:
        if post.get("status") != "pending":
            continue

        scheduled_at_str = post.get("scheduled_at")
        if not scheduled_at_str:
            continue

        try:
            scheduled_dt = datetime.datetime.fromisoformat(scheduled_at_str)
            if scheduled_dt.tzinfo is None:
                scheduled_dt = scheduled_dt.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            continue

        if now >= scheduled_dt:
            print(f"⏰ [Scheduler] Auto-posting due clip {post.get('clip_index')} of {post.get('job_id')}...")
            post["status"] = "processing"
            updated = True
            _save_schedules(posts)

            # Execute publishing
            try:
                job_id = post["job_id"]
                clip_index = post["clip_index"]
                platforms = post.get("platforms", ["youtube"])

                import youtube_publisher
                import buffer_publisher

                job = app_module.jobs.get(job_id)
                if not job:
                    job = app_module._job_view_from_disk(job_id)
                if not job:
                    raise RuntimeError(f"Job {job_id} not found on server")

                clip, file_path, filename = app_module._resolve_clip_video_file(job, job_id, clip_index)
                title = post.get("title") or clip.get("video_title_for_youtube_short") or "Short"
                description = post.get("description") or clip.get("video_description_for_instagram") or ""
                results_collected = {}
                provider = post.get("provider", "auto")
                use_youtube = provider in ("youtube", "both", "auto")
                use_buffer = provider in ("buffer", "both", "auto")

                # 1. Direct YouTube Publishing
                if use_youtube and "youtube" in platforms and youtube_publisher.is_direct_youtube_configured():
                    try:
                        yt_result = await asyncio.to_thread(
                            youtube_publisher.upload_video_to_youtube,
                            file_path=file_path,
                            title=title,
                            description=description,
                            privacy_status=post.get("privacy_status", "public"),
                        )
                        results_collected["youtube"] = {
                            "video_id": yt_result.get("video_id"),
                            "url": yt_result.get("url"),
                            "shorts_url": yt_result.get("shorts_url"),
                        }
                        print(f"✅ [Scheduler] Auto-posted to YouTube successfully: {yt_result.get('shorts_url')}")
                    except Exception as yt_err:
                        print(f"❌ [Scheduler] YouTube upload failed: {yt_err}")
                        results_collected["youtube_error"] = str(yt_err)

                # 2. Buffer Publishing across connected social channels
                buffer_channels = post.get("buffer_channels")
                if use_buffer and buffer_publisher.is_buffer_configured():
                    try:
                        all_buffer_channels = await asyncio.to_thread(buffer_publisher.list_channels)
                        channels_to_post = []
                        if buffer_channels:
                            channels_to_post = [c for c in all_buffer_channels if c.get("id") in buffer_channels]
                        else:
                            if provider == "buffer":
                                # Post to all matching or all available Buffer channels
                                target_services = set(p.lower() for p in platforms)
                                channels_to_post = [c for c in all_buffer_channels if c.get("service", "").lower() in target_services]
                                if not channels_to_post:
                                    channels_to_post = all_buffer_channels
                            else:
                                # For "both" or "auto", only include youtube if direct youtube was not used
                                yt_handled = "youtube" in results_collected
                                target_services = set(p.lower() for p in platforms if p != "youtube" or not yt_handled)
                                channels_to_post = [c for c in all_buffer_channels if c.get("service", "").lower() in target_services]

                        if channels_to_post:
                            video_url = clip.get("video_url")
                            base_url = (
                                (job.get("base_url") if isinstance(job, dict) else None)
                                or os.environ.get("PUBLIC_API_URL")
                                or os.environ.get("PUBLIC_APP_URL")
                                or ""
                            ).rstrip("/")

                            if not video_url or (not video_url.startswith("http://") and not video_url.startswith("https://")):
                                rel_path = f"/videos/{job_id}/{filename}"
                                video_url = f"{base_url}{rel_path}" if base_url else rel_path

                            sched_mode = post.get("scheduling_mode", "smart_jitter")
                            buffer_mode = "addToQueue" if sched_mode == "buffer_queue" else "shareNow"

                            buf_results = await asyncio.to_thread(
                                buffer_publisher.publish_to_buffer_channels,
                                channels=channels_to_post,
                                text=description or title,
                                video_url=video_url,
                                mode=buffer_mode,
                                title=title,
                            )
                            results_collected["buffer"] = buf_results
                            print(f"✅ [Scheduler] Auto-posted to Buffer channels: {len(buf_results)}")

                            # Handle Buffer Plan Queue Limit (10 items on Free Plan)
                            queue_limited = any(
                                ("queue" in str(r.get("error", "")).lower() or "limit" in str(r.get("error", "")).lower())
                                for r in buf_results
                                if not r.get("success")
                            )
                            if queue_limited and all(not r.get("success") for r in buf_results):
                                post["status"] = "pending"
                                post["scheduled_at"] = (now + datetime.timedelta(hours=1)).isoformat()
                                post["error"] = "Buffer queue limit reached (plan constraint); auto-postponed 1 hour"
                                print(f"⏳ [Scheduler] Buffer queue limit hit for {post.get('id')}; retrying in 1 hour")
                                updated = True
                                continue
                    except Exception as buf_err:
                        print(f"❌ [Scheduler] Buffer posting failed: {buf_err}")
                        results_collected["buffer_error"] = str(buf_err)

                if not results_collected or (all(k.endswith("_error") for k in results_collected)):
                    err_msg = "; ".join(f"{k}: {v}" for k, v in results_collected.items()) if results_collected else "No active provider for selected platforms"
                    raise RuntimeError(err_msg)

                post["status"] = "completed"
                post["result"] = results_collected

            except Exception as e:
                print(f"❌ [Scheduler] Auto-posting failed for {post.get('id')}: {e}")
                post["status"] = "failed"
                post["error"] = str(e)

            updated = True

    if updated:
        _save_schedules(posts)


async def run_scheduler_background_loop(app_module):
    """Background polling loop that checks for due scheduled posts every 20 seconds."""
    print("⏰ [Scheduler] Background auto-post scheduler loop started.")
    while True:
        try:
            await execute_due_posts(app_module)
        except Exception as e:
            print(f"⚠️ [Scheduler] Loop exception: {e}")
        await asyncio.sleep(20)
