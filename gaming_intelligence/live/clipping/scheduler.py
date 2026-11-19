"""
scheduler.py - Asynchronous event scheduler and two-stage clip coordinator.
Pins pre-roll immediately upon hype detection, waits for post-roll, and executes Stage A & B rendering.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Dict, List, Optional
from .extractor import FastClipExtractor
from .renderer import FastVerticalRenderer
from ..models import ClipJob, ClipMode, HypeEvent, LatencyMilestones
from ..recording.buffer import RollingSegmentBuffer
from ..recording.timestamps import TimestampSynchronizer

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
    ):
        self.buffer = buffer
        self.sync = sync
        self.extractor = extractor
        self.renderer = renderer
        self.pre_roll_sec = pre_roll_sec
        self.post_roll_sec = post_roll_sec
        self.on_clip_ready = on_clip_ready

        # Active jobs: job_id -> ClipJob
        self.active_jobs: Dict[str, ClipJob] = {}

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
            if not pinned:
                job.status = "failed"
                job.error = "No segments found in buffer for the requested time range"
                logger.error(f"❌ Job {job.job_id} failed: No segments available")
                self.buffer.unpin(job.job_id)
                return

            # 3. Stage A: Fast Draft Remux (< 1.5s)
            job.status = "extracting_stage_a"
            job.milestones.extract_started_at = time.time()

            # Run in thread pool so FFmpeg subprocess doesn't block the async loop
            loop = asyncio.get_event_loop()
            draft_path = await loop.run_in_executor(
                None,
                lambda: self.extractor.extract_draft_preview(pinned, job.job_id)
            )
            job.draft_path = draft_path
            job.milestones.extract_completed_at = time.time()

            # 4. Stage B: Hardware-Accelerated Vertical Render (< 5.0s)
            job.status = "rendering_stage_b"
            job.milestones.render_started_at = time.time()

            target_duration = job.clip_end_time - job.clip_start_time
            out_filename = f"short_{job.job_id}_{int(time.time())}.mp4"

            final_path = await loop.run_in_executor(
                None,
                lambda: self.renderer.render_vertical_short(
                    draft_path,
                    out_filename,
                    target_duration=target_duration
                )
            )
            job.final_path = final_path
            job.milestones.render_completed_at = time.time()
            job.status = "complete"

            # 5. Unpin segments from buffer now that extraction & render are complete
            self.buffer.unpin(job.job_id)

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
