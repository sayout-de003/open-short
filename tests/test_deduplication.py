"""Unit tests for 3-level deduplication helpers."""
from __future__ import annotations

from gaming_intelligence.deduplication import (
    compute_moment_fingerprint,
    is_duplicate_moment,
    windows_overlap,
)


def test_windows_overlap_detects_significant_overlap() -> None:
    # 00:10:00-00:10:35 vs 00:10:20-00:10:55 => 15s overlap
    assert windows_overlap(600.0, 635.0, 620.0, 655.0) is True


def test_windows_overlap_allows_disjoint_clips() -> None:
    assert windows_overlap(100.0, 135.0, 200.0, 235.0) is False


def test_is_duplicate_moment_matches_fingerprint_or_overlap() -> None:
    fp = compute_moment_fingerprint("youtube", "vid123", 60.0, 95.0)
    existing = [(60.0, 95.0, fp)]
    assert is_duplicate_moment(62.0, 96.0, existing) is True
    assert is_duplicate_moment(200.0, 235.0, existing, fingerprint=fp) is True
    assert is_duplicate_moment(200.0, 235.0, existing, fingerprint="other_fp") is False
