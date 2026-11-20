"""Unit tests for normalized candidate ranking."""
from __future__ import annotations

import datetime

from autopilot.models import DiscoveredSource
from gaming_intelligence.ranking import calculate_score, rank_candidates


def test_calculate_score_weights() -> None:
    assert calculate_score(100, 100, 100, 100, 100) == 100.0
    assert calculate_score(0, 0, 0, 0, 0) == 0.0


def test_rank_candidates_normalizes_live_and_vod_separately() -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    candidates = [
        DiscoveredSource(
            platform="twitch", source_id="l1", source_type="live", url="u1", title="Live 1",
            channel_id="c1", channel_name="C1", concurrent_viewers=8000, published_at=now,
        ),
        DiscoveredSource(
            platform="youtube", source_id="v1", source_type="vod", url="u2", title="VOD 1",
            channel_id="c2", channel_name="C2", view_count=500000, like_count=25000, comment_count=1000, published_at=now,
        ),
        DiscoveredSource(
            platform="youtube", source_id="v2", source_type="vod", url="u3", title="VOD 2",
            channel_id="c3", channel_name="C3", view_count=1000, like_count=5, comment_count=0, published_at=now,
        ),
    ]
    ranked = rank_candidates(candidates, top_n=10)
    assert len(ranked) == 3
    assert all("popularity" in c.score_breakdown for c in ranked)
    assert ranked[0].score >= ranked[1].score >= ranked[2].score
    assert ranked[-1].source_id == "v2"
