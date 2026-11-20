"""Three-level deduplication: source, moment, and publication."""
from __future__ import annotations

import hashlib
from typing import Iterable, Optional, Tuple


def compute_moment_fingerprint(
    platform: str,
    source_id: str,
    start_time: float,
    end_time: float,
    bucket_sec: float = 5.0,
) -> str:
    """Deterministic coarse fingerprint for a source time window."""
    s_bucket = int(round(start_time / bucket_sec) * bucket_sec)
    e_bucket = int(round(end_time / bucket_sec) * bucket_sec)
    raw = f"{platform.lower()}:{source_id}:{s_bucket}:{e_bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def windows_overlap(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
    min_overlap_ratio: float = 0.40,
    min_overlap_sec: float = 8.0,
) -> bool:
    """Return True if two [start, end] clip windows overlap significantly."""
    if end_a <= start_a or end_b <= start_b:
        return False
    inter = max(0.0, min(end_a, end_b) - max(start_a, start_b))
    if inter <= 0.0:
        return False
    shorter = min(end_a - start_a, end_b - start_b)
    return inter >= min_overlap_sec or (inter / shorter) >= min_overlap_ratio


def is_duplicate_moment(
    start_time: float,
    end_time: float,
    existing_windows: Iterable[Tuple[float, float, Optional[str]]],
    fingerprint: Optional[str] = None,
    min_overlap_ratio: float = 0.40,
) -> bool:
    """Level-2 check against existing (start, end, fingerprint) moments for the same source."""
    for ex_start, ex_end, ex_fp in existing_windows:
        if fingerprint and ex_fp and fingerprint == ex_fp:
            return True
        if windows_overlap(start_time, end_time, ex_start, ex_end, min_overlap_ratio=min_overlap_ratio):
            return True
    return False
