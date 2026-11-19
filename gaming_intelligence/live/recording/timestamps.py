"""
timestamps.py - Synchronizes live stream video PTS timestamps with wall-clock chat epoch.
"""
from __future__ import annotations

import time
from typing import Optional


class TimestampSynchronizer:
    """Maintains mapping between stream playback time (seconds from start) and wall-clock epoch."""

    def __init__(self, stream_start_wall_clock: Optional[float] = None):
        self.stream_start_wall_clock = stream_start_wall_clock or time.time()

    def wall_clock_to_stream_time(self, wall_clock_ts: float) -> float:
        """Converts epoch timestamp (e.g. chat message time) to relative stream seconds."""
        return max(0.0, wall_clock_ts - self.stream_start_wall_clock)

    def stream_time_to_wall_clock(self, stream_time_sec: float) -> float:
        """Converts relative stream seconds to epoch timestamp."""
        return self.stream_start_wall_clock + stream_time_sec
