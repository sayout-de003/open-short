"""
spam.py - High-speed in-memory spam and bot filter.
Prevents single users or automated bot floods from artificially triggering hype.
"""
from __future__ import annotations

import collections
import time
from typing import Dict


class SpamFilter:
    """Tracks per-user message frequencies and drops spam messages in O(1)."""

    def __init__(self, max_user_mps: int = 5, window_sec: float = 3.0):
        self.max_user_mps = max_user_mps
        self.window_sec = window_sec
        # user_id -> deque of recent message timestamps
        self._user_history: Dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self._last_cleanup = time.time()

    def is_spam(self, user_id: str, timestamp: float, text: str) -> bool:
        """Returns True if the message should be ignored as spam/flood."""
        dq = self._user_history[user_id]
        cutoff = timestamp - self.window_sec

        # Drop old timestamps
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= self.max_user_mps:
            return True

        dq.append(timestamp)

        # Periodic cleanup of empty users every 30 seconds
        if timestamp - self._last_cleanup > 30.0:
            self._cleanup(cutoff)
            self._last_cleanup = timestamp

        return False

    def _cleanup(self, cutoff: float):
        to_del = []
        for uid, dq in self._user_history.items():
            while dq and dq[0] < cutoff:
                dq.popleft()
            if not dq:
                to_del.append(uid)
        for uid in to_del:
            del self._user_history[uid]
