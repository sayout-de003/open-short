"""
hype.py - O(1) sliding-window hype and burst detector.
Calculates velocity, chant density, caps ratio, and Z-score in O(1) time complexity.
"""
from __future__ import annotations

import collections
import math
import time
import uuid
from typing import Callable, Counter, Deque, Dict, List, Optional, Set
from .features import extract_message_features
from .spam import SpamFilter
from ..models import ChatMessage, HypeEvent, HypeMetrics


class SecondBucket:
    """Aggregated metrics for a single 1-second time slot."""
    __slots__ = ("sec_epoch", "message_count", "hype_tokens", "total_tokens", "caps_sum", "users", "chants")

    def __init__(self, sec_epoch: int):
        self.sec_epoch = sec_epoch
        self.message_count = 0
        self.hype_tokens = 0
        self.total_tokens = 0
        self.caps_sum = 0.0
        self.users: Set[str] = set()
        self.chants: collections.Counter = collections.Counter()


class FastHypeDetector:
    """
    O(1) sliding window detector maintaining rolling aggregates:
    - Short window (default 5s) for instant reaction detection
    - Long baseline window (default 60s) for mean and variance Z-score calculation
    """

    def __init__(
        self,
        short_window_sec: int = 5,
        baseline_window_sec: int = 60,
        z_score_threshold: float = 2.5,
        min_mps: float = 3.0,
        min_unique_users: int = 2,
        cooldown_sec: float = 30.0,
        on_hype_event: Optional[Callable[[HypeEvent], None]] = None,
    ):
        self.short_window_sec = short_window_sec
        self.baseline_window_sec = baseline_window_sec
        self.z_score_threshold = z_score_threshold
        self.min_mps = min_mps
        self.min_unique_users = min_unique_users
        self.cooldown_sec = cooldown_sec
        self.on_hype_event = on_hype_event

        self.spam_filter = SpamFilter()

        # Deque of SecondBuckets covering up to baseline_window_sec
        self._buckets: Deque[SecondBucket] = collections.deque()
        self._current_bucket: Optional[SecondBucket] = None

        # Rolling aggregates over baseline_window_sec
        self._rolling_msg_count: int = 0
        self._rolling_sq_msg_count: float = 0.0  # For variance: sum(x^2)

        # Rolling aggregates over short_window_sec
        self._short_msg_count: int = 0
        self._short_hype_tokens: int = 0
        self._short_total_tokens: int = 0
        self._short_caps_sum: float = 0.0

        self._last_velocity: float = 0.0
        self._last_trigger_time: float = 0.0

    def add_message(self, msg: ChatMessage) -> Optional[HypeMetrics]:
        """
        Ingests a message in O(1) and updates feature counters.
        """
        # 1. Spam check
        if self.spam_filter.is_spam(msg.user_id, msg.timestamp, msg.text):
            return None

        # 2. Extract features
        h_count, t_count, caps_ratio, chants = extract_message_features(msg.text)

        sec_epoch = int(msg.timestamp)
        self._advance_time(sec_epoch)

        bucket = self._current_bucket
        if bucket is not None:
            bucket.message_count += 1
            bucket.hype_tokens += h_count
            bucket.total_tokens += t_count
            bucket.caps_sum += caps_ratio
            bucket.users.add(msg.user_id)
            bucket.chants.update(chants)

        return self.compute_metrics(sec_epoch)

    def _advance_time(self, current_sec: int):
        """Advances buckets up to current_sec, discarding expired baseline buckets in O(1)."""
        if self._current_bucket is None:
            self._current_bucket = SecondBucket(current_sec)
            self._buckets.append(self._current_bucket)
            return

        if current_sec == self._current_bucket.sec_epoch:
            return

        # Advance through missing seconds if any
        last_sec = self._current_bucket.sec_epoch
        while last_sec < current_sec:
            last_sec += 1
            new_bucket = SecondBucket(last_sec)
            self._buckets.append(new_bucket)
            self._current_bucket = new_bucket

        # Evict buckets older than baseline_window_sec
        cutoff = current_sec - self.baseline_window_sec
        while self._buckets and self._buckets[0].sec_epoch <= cutoff:
            self._buckets.popleft()

    def compute_metrics(self, current_sec: Optional[int] = None) -> HypeMetrics:
        """
        Computes current metrics over short and baseline windows in O(1) (bounded by max 60 buckets).
        """
        if current_sec is None:
            current_sec = int(time.time())
        self._advance_time(current_sec)

        short_cutoff = current_sec - self.short_window_sec
        short_msgs = 0
        short_hype_toks = 0
        short_total_toks = 0
        short_caps_sum = 0.0
        short_users: Set[str] = set()
        short_chants: Counter = collections.Counter()

        baseline_msgs = 0
        n_baseline = 0
        sum_x = 0
        sum_x2 = 0

        for b in self._buckets:
            # Baseline stats from prior history before short window
            if b.sec_epoch <= short_cutoff:
                count = b.message_count
                sum_x += count
                sum_x2 += count * count
                n_baseline += 1
            else:
                # Short window stats
                count = b.message_count
                short_msgs += count
                short_hype_toks += b.hype_tokens
                short_total_toks += b.total_tokens
                short_caps_sum += b.caps_sum
                short_users.update(b.users)
                short_chants.update(b.chants)

        # Velocity in messages per second
        velocity = short_msgs / float(self.short_window_sec)
        acceleration = velocity - self._last_velocity
        self._last_velocity = velocity

        # Baseline mean and std dev (if no baseline yet, use default expected idle rate 0.5 mps)
        mean_mps = (sum_x / float(n_baseline)) if n_baseline > 0 else 0.5
        var = ((sum_x2 / float(n_baseline)) - (mean_mps * mean_mps)) if n_baseline > 0 else 0.25
        std_dev = math.sqrt(max(0.01, var))
        z_score = (velocity - mean_mps) / std_dev

        chant_density = (short_hype_toks / float(short_total_toks)) if short_total_toks > 0 else 0.0
        caps_ratio = (short_caps_sum / float(short_msgs)) if short_msgs > 0 else 0.0
        top_chants = [word for word, _ in short_chants.most_common(5)]

        metrics = HypeMetrics(
            timestamp=float(current_sec),
            message_count=short_msgs,
            velocity_mps=round(velocity, 2),
            acceleration=round(acceleration, 2),
            unique_users=len(short_users),
            chant_density=round(chant_density, 3),
            emote_density=round(chant_density, 3),
            caps_ratio=round(caps_ratio, 3),
            z_score=round(z_score, 2),
            top_chants=top_chants
        )

        # Check hype trigger conditions
        self._evaluate_trigger(metrics)
        return metrics

    def _evaluate_trigger(self, metrics: HypeMetrics):
        now = metrics.timestamp
        if now - self._last_trigger_time < self.cooldown_sec:
            return  # In cooldown

        # Trigger conditions:
        # 1. Z-score indicates abnormal surge (> threshold)
        # 2. Absolute velocity is sufficient (> min_mps)
        # 3. Crowd consensus (> min_unique_users)
        # 4. Either chant density > 20% OR velocity > 2.5x min_mps
        if (
            metrics.z_score >= self.z_score_threshold
            and metrics.velocity_mps >= self.min_mps
            and metrics.unique_users >= self.min_unique_users
            and (metrics.chant_density >= 0.15 or metrics.velocity_mps >= (self.min_mps * 2))
        ):
            self._last_trigger_time = now
            # Assume 3.0s viewer latency reaction offset
            event_ts = now - 3.0
            event = HypeEvent(
                event_id=str(uuid.uuid4())[:8],
                detected_at=now,
                event_timestamp=event_ts,
                peak_velocity=metrics.velocity_mps,
                z_score=metrics.z_score,
                top_chants=metrics.top_chants,
                confidence=min(1.0, metrics.z_score / 4.0)
            )
            if self.on_hype_event:
                self.on_hype_event(event)
