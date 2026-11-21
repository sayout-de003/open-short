"""
scheduler.py - Asynchronous event scheduler and two-stage clip coordinator.
Pins pre-roll immediately upon hype detection, waits for post-roll, and executes Stage A & B rendering.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import time
from typing import Callable, Dict, List, Optional
from .extractor import FastClipExtractor
from .renderer import FastVerticalRenderer
from ..models import ClipJob, ClipMode, HypeEvent, LatencyMilestones
from ..recording.buffer import RollingSegmentBuffer
from ..recording.timestamps import TimestampSynchronizer

try:
    import resource_guard
except ImportError:
    resource_guard = None

logger = logging.getLogger("live.scheduler")


class ClipScheduler:
    """Coordinates clip extraction and rendering without blocking chat monitoring."""

    def __init__(
        self,
        buffer: RollingSegmentBuffer,
        sync: TimestampSynchronizer,
        extractor: FastClipExtractor,
        renderer: FastVerticalRenderer,
        pre_roll_sec: float = 25.0,
        post_roll_sec: float = 10.0,
        on_clip_ready: Optional[Callable[[ClipJob], None]] = None,
        max_concurrent_renders: Optional[int] = None,
        min_free_ram_mb: Optional[int] = None,
    ):
        self.buffer = buffer
        self.sync = sync
        self.extractor = extractor
        self.renderer = renderer
        self.pre_roll_sec = pre_roll_sec
        self.post_roll_sec = post_roll_sec
        self.on_clip_ready = on_clip_ready
        self.max_concurrent_renders = max(
            1,
            max_concurrent_renders
            if max_concurrent_renders is not None
            else int(os.environ.get("MAX_LIVE_CLIP_RENDERS", "2")),
        )
        self.min_free_ram_mb = (
            min_free_ram_mb
            if min_free_ram_mb is not None
            else int(os.environ.get("RAM_EDIT_MIN_FREE_MB", "1024"))
        )
        self._render_semaphore = asyncio.Semaphore(self.max_concurrent_renders)
        self._render_executor = ThreadPoolExecutor(
            max_workers=self.max_concurrent_renders,
            thread_name_prefix="live-render",
        )
        self._active_renders = 0

        # Active jobs: job_id -> ClipJob
        self.active_jobs: Dict[str, ClipJob] = {}

    def close(self):
        self._render_executor.shutdown(wait=False)

    def on_hype_event(self, event: HypeEvent):
        """
        Hot path entry point when hype detector fires.
        Executes immediately in O(1) without blocking.
        """
        t_detect = time.time()
        milestones = LatencyMilestones(
            chat_received_at=event.detected_at,
            hype_detected_at=t_detect
        )

        stream_event_time = self.sync.wall_clock_to_stream_time(event.event_timestamp)
        clip_start = max(0.0, stream_event_time - self.pre_roll_sec)
        clip_end = stream_event_time + self.post_roll_sec

        job = ClipJob(
            job_id=event.event_id,
            event=event,
            clip_start_time=clip_start,
            clip_end_time=clip_end,
            status="pinned_preroll",
            milestones=milestones
        )

        # 1. Immediately pin all pre-roll segments currently in the buffer
        pinned = self.buffer.pin_range(clip_start, clip_end, job.job_id)
        job.pinned_segments = [s.filepath for s in pinned]
        milestones.pre_roll_pinned_at = time.time()

        self.active_jobs[job.job_id] = job
        logger.info(f"⚡ [P0 Capture] Job {job.job_id} scheduled: stream window [{clip_start:.1f}s - {clip_end:.1f}s]. Pre-roll pinned.")

        # 2. Launch background task to wait for post-roll and render
        asyncio.create_task(self._execute_job_pipeline(job))

    async def _execute_job_pipeline(self, job: ClipJob):
        """Asynchronously executes post-roll wait, Stage A draft, and Stage B final render."""
        try:
            # 1. Determine how long we must physically wait for the post-roll to be recorded
            current_stream_time = self.sync.wall_clock_to_stream_time(time.time())
            needed_postroll_wait = max(0.0, job.clip_end_time - current_stream_time)

            if needed_postroll_wait > 0:
                logger.info(f"⏳ Job {job.job_id}: Waiting {needed_postroll_wait:.1f}s for physical post-roll video to record...")
                await asyncio.sleep(needed_postroll_wait + 0.5)  # +0.5s margin for segment write flush

            job.milestones.post_roll_ready_at = time.time()

            # 2. Re-pin to include any newly written post-roll segments
            pinned = self.buffer.pin_range(job.clip_start_time, job.clip_end_time, job.job_id)
            if not pinned and self.buffer._segments:
                # Fallback if segment clock drifted slightly from wall-clock
                wanted_dur = max(10.0, job.clip_end_time - job.clip_start_time)
                all_segs = [s for _, s in sorted(self.buffer._segments.items())]
                acc = 0.0
                fallback_segs = []
                for s in reversed(all_segs):
                    fallback_segs.append(s)
                    acc += s.duration
                    if acc >= wanted_dur:
                        break
                pinned = list(reversed(fallback_segs))
                if pinned:
                    self.buffer.pin_range(pinned[0].start_time, pinned[-1].end_time, job.job_id)
            if not pinned:
                job.status = "failed"
                job.error = "No segments found in buffer for the requested time range"
                logger.error(f"❌ Job {job.job_id} failed: No segments available")
                self.buffer.unpin(job.job_id)
                return

            # 3. Bound concurrent renders and check RAM before running FFmpeg Stage A & B
            async with self._render_semaphore:
                if resource_guard is not None and self.min_free_ram_mb > 0:
                    has_ram = await resource_guard.wait_for_ram(
                        self.min_free_ram_mb,
                        active_count_fn=lambda: self._active_renders,
                        timeout_sec=60.0,
                    )
                    if not has_ram:
                        raise RuntimeError(
                            f"Insufficient system RAM (< {self.min_free_ram_mb} MiB free) for live clip render"
                        )

                self._active_renders += 1
                try:
                    # Stage A: Fast Draft Remux (< 1.5s)
                    job.status = "extracting_stage_a"
                    job.milestones.extract_started_at = time.time()

                    loop = asyncio.get_running_loop()
                    draft_path = await loop.run_in_executor(
                        self._render_executor,
                        lambda: self.extractor.extract_draft_preview(pinned, job.job_id)
                    )
                    job.draft_path = draft_path
                    job.milestones.extract_completed_at = time.time()

                    # Stage B: Hardware-Accelerated Vertical Render (< 5.0s)
                    job.status = "rendering_stage_b"
                    job.milestones.render_started_at = time.time()

                    target_duration = job.clip_end_time - job.clip_start_time
                    out_filename = f"short_{job.job_id}_{int(time.time())}.mp4"

                    final_path = await loop.run_in_executor(
                        self._render_executor,
                        lambda: self.renderer.render_vertical_short(
                            draft_path,
                            out_filename,
                            target_duration=target_duration
                        )
                    )
                finally:
                    self._active_renders = max(0, self._active_renders - 1)
            job.final_path = final_path
            job.milestones.render_completed_at = time.time()
            job.status = "complete"

            # 5. Unpin segments from buffer now that extraction & render are complete
            self.buffer.unpin(job.job_id)
            if os.environ.get("LIVE_CLEANUP_DRAFT") == "1" and job.draft_path and os.path.exists(job.draft_path):
                try:
                    os.remove(job.draft_path)
                except OSError:
                    pass

            logger.info(
                f"🎉 [Clip Ready] Job {job.job_id} completed! "
                f"Milestones: {job.milestones.to_dict()} | Output: {final_path}"
            )

            if self.on_clip_ready:
                self.on_clip_ready(job)

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            logger.error(f"❌ Job {job.job_id} processing failed: {e}")
            self.buffer.unpin(job.job_id)
