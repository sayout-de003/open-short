"""Normalized candidate ranking separating live and VOD metrics."""
from __future__ import annotations

import datetime
import math
from typing import Dict, List

from autopilot.models import DiscoveredSource


def calculate_score(
    popularity: float,
    engagement: float,
    recency: float,
    growth: float,
    confidence: float,
) -> float:
    """Weighted score in [0, 100]: S = 0.30P + 0.25E + 0.20R + 0.15F + 0.10Q."""
    return round(
        0.30 * popularity
        + 0.25 * engagement
        + 0.20 * recency
        + 0.15 * growth
        + 0.10 * confidence,
        2,
    )


def _age_hours(published_at: str | None, now: datetime.datetime) -> float:
    if not published_at:
        return 48.0
    try:
        s = published_at.strip()
        if len(s) == 8 and s.isdigit():
            dt = datetime.datetime.strptime(s, "%Y%m%d").replace(tzinfo=datetime.timezone.utc)
        else:
            dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
        return max(0.0, (now - dt).total_seconds() / 3600.0)
    except Exception:
        return 48.0


def _percentile_scores(values: List[float]) -> List[float]:
    if not values:
        return []
    n = len(values)
    if n == 1:
        return [100.0 if values[0] > 0 else 0.0]
    sorted_vals = sorted(values)
    max_v = sorted_vals[-1]
    if max_v <= 0:
        return [0.0] * n
    out = []
    for v in values:
        rank = sum(1 for x in sorted_vals if x <= v)
        out.append(round(100.0 * (rank / n), 2))
    return out


def _score_cohort(cohort: List[DiscoveredSource], is_live: bool, max_age_hours: int) -> None:
    if not cohort:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    raw_pop = [float(s.concurrent_viewers if is_live else s.view_count) for s in cohort]
    pop_pcts = _percentile_scores(raw_pop)

    for idx, src in enumerate(cohort):
        p = pop_pcts[idx]
        age_h = _age_hours(src.published_at, now)
        r = round(max(0.0, 100.0 * (1.0 - min(age_h, float(max_age_hours)) / float(max(1, max_age_hours)))), 2)

        if is_live:
            # Live engagement/growth proxy from viewer concentration and active freshness
            e = round(min(100.0, p * 0.85 + 15.0) if src.concurrent_viewers > 0 else 0.0, 2)
            f = round(min(100.0, math.log1p(src.concurrent_viewers) * 10.0), 2)
        else:
            views = max(1, src.view_count)
            eng_ratio = (src.like_count + src.comment_count * 2.0) / views
            e = round(min(100.0, eng_ratio * 1500.0), 2)
            velocity = views / max(1.0, age_h)
            f = round(min(100.0, math.log1p(velocity) * 12.0), 2)

        q = round(max(0.0, min(100.0, src.metadata_confidence)), 2)
        src.score_breakdown = {
            "popularity": p,
            "engagement": e,
            "recency": r,
            "growth": f,
            "confidence": q,
        }
        src.score = calculate_score(p, e, r, f, q)


def rank_candidates(
    candidates: List[DiscoveredSource],
    max_age_hours: int = 72,
    top_n: int = 10,
) -> List[DiscoveredSource]:
    """Normalize live and VOD cohorts separately, then merge and return top_n by score."""
    live = [c for c in candidates if c.source_type == "live"]
    vods = [c for c in candidates if c.source_type != "live"]

    _score_cohort(live, is_live=True, max_age_hours=max_age_hours)
    _score_cohort(vods, is_live=False, max_age_hours=max_age_hours)

    combined = sorted(live + vods, key=lambda c: c.score, reverse=True)
    return combined[:top_n] if top_n > 0 else combined
