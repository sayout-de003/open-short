"""
buffer.py - Rolling segmented video buffer with segment pinning.
Keeps a 5-minute rolling window of video segments and prevents pinned segments from being deleted.
"""
from __future__ import annotations

import collections
import logging
import os
import shutil
import time
from typing import Dict, List, Optional, Set
from ..models import VideoSegment

logger = logging.getLogger("live.buffer")


class RollingSegmentBuffer:
    """
    Tracks and manages segmented video files on disk.
    - Evicts unpinned segments older than max_retention_sec (default: 300s / 5 mins).
    - Protects pinned segments requested by active clip jobs.
    """

    def __init__(self, buffer_dir: str, max_retention_sec: float = 300.0):
        self.buffer_dir = buffer_dir
        self.max_retention_sec = max_retention_sec
        os.makedirs(self.buffer_dir, exist_ok=True)

        # In-memory index of segments: segment_index -> VideoSegment
        self._segments: Dict[int, VideoSegment] = {}
        # job_id -> set of pinned segment indices
        self._pinned_by_job: Dict[str, Set[int]] = collections.defaultdict(set)

    def register_segment(
        self,
        segment_index: int,
        filepath: str,
        start_time: float,
        end_time: float
    ) -> VideoSegment:
        """Registers a newly written video segment into the in-memory index."""
        duration = max(0.1, end_time - start_time)
        seg = VideoSegment(
            segment_index=segment_index,
            filepath=filepath,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            created_at=time.time()
        )
        self._segments[segment_index] = seg
        return seg

    def pin_range(self, start_time: float, end_time: float, job_id: str) -> List[VideoSegment]:
        """
        Immediately pins all available segments that overlap [start_time, end_time].
        Pinned segments are protected from deletion until job unpins them.
        """
        matched: List[VideoSegment] = []
        for idx, seg in sorted(self._segments.items()):
            # Non-zero duration overlap condition: segment start < range end and segment end > range start
            if seg.start_time < end_time and seg.end_time > start_time:
                matched.append(seg)
                self._pinned_by_job[job_id].add(idx)

        logger.info(f"📌 Job {job_id}: Pinned {len(matched)} segments for [{start_time:.1f}s - {end_time:.1f}s]")
        return matched

    def unpin(self, job_id: str):
        """Releases the segment lock for a completed or failed job."""
        if job_id in self._pinned_by_job:
            del self._pinned_by_job[job_id]
            logger.info(f"🔓 Job {job_id}: Unpinned all segments")

    def get_pinned_segments(self, job_id: str) -> List[VideoSegment]:
        indices = self._pinned_by_job.get(job_id, set())
        return [self._segments[idx] for idx in sorted(indices) if idx in self._segments]

    def is_pinned(self, segment_index: int) -> bool:
        for indices in self._pinned_by_job.values():
            if segment_index in indices:
                return True
        return False

    def clean_expired(self, current_stream_time: float) -> int:
        """
        Deletes unpinned segments that fall outside the max_retention_sec window.
        Returns count of removed segments.
        """
        cutoff = current_stream_time - self.max_retention_sec
        to_remove = []

        for idx, seg in self._segments.items():
            if seg.end_time < cutoff:
                if not self.is_pinned(idx):
                    to_remove.append(idx)

        deleted = 0
        for idx in to_remove:
            seg = self._segments.pop(idx, None)
            if seg and os.path.exists(seg.filepath):
                try:
                    os.remove(seg.filepath)
                    deleted += 1
                except OSError as e:
                    logger.warning(f"Failed to remove expired segment {seg.filepath}: {e}")

        return deleted

    def clear_all(self):
        """Cleans all files and resets index."""
        self._segments.clear()
        self._pinned_by_job.clear()
        if os.path.exists(self.buffer_dir):
            shutil.rmtree(self.buffer_dir, ignore_errors=True)
            os.makedirs(self.buffer_dir, exist_ok=True)
