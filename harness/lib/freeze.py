"""Schema-freeze logic — operator-level governance for the harness itself.

Where the 5 proposal-level constraints validate someone *using* the harness
(submitting a proposal), the freeze rule validates whether the harness
*itself* may be mutated. See docs/why.md §Operator Rule O1 for the story.

The rule:
  - Reviews are declared in governance/reviews.yaml with closes_at dates
  - When >=2 reviews close within CLUSTER_GAP_DAYS of each other, they form
    a cluster (chained transitively: a-b within gap, b-c within gap => abc
    in one cluster, even if a-c exceeds the gap)
  - For each cluster of >=2 reviews, the freeze window is
    [first.closes_at - PRE_FREEZE_DAYS, last.closes_at + POST_FREEZE_DAYS]
  - During the freeze, mutations to schemas/, bin/, lib/ should be parked
    as hypotheses-with-trigger and re-submitted post-freeze.

This module computes status; enforcement is operator-level (a human running
bin/freeze_status.py before opening their editor on harness/).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml


HARNESS_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REVIEWS_PATH = HARNESS_ROOT / "governance" / "reviews.yaml"

CLUSTER_GAP_DAYS = 7
PRE_FREEZE_DAYS = 7
POST_FREEZE_DAYS = 14


@dataclass
class Review:
    name: str
    closes_at: date
    kind: str = "promotion_review"
    memory: Optional[str] = None


@dataclass
class FreezeWindow:
    start: date
    end: date
    reviews: list[Review] = field(default_factory=list)

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end


@dataclass
class FreezeStatus:
    frozen: bool
    as_of: date
    active_window: Optional[FreezeWindow] = None
    next_window: Optional[FreezeWindow] = None
    days_until_freeze: Optional[int] = None
    days_until_unfreeze: Optional[int] = None


def load_reviews(path: str | Path = DEFAULT_REVIEWS_PATH) -> list[Review]:
    """Load reviews from a YAML file. Schema:
        reviews:
          - name: <str>
            closes_at: <YYYY-MM-DD>
            kind: <str, optional>
            memory: <str, optional>
    """
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    out: list[Review] = []
    for r in data.get("reviews", []):
        closes_at = r["closes_at"]
        if isinstance(closes_at, str):
            closes_at = date.fromisoformat(closes_at)
        out.append(
            Review(
                name=r["name"],
                closes_at=closes_at,
                kind=r.get("kind", "promotion_review"),
                memory=r.get("memory"),
            )
        )
    return out


def compute_clusters(
    reviews: list[Review],
    cluster_gap_days: int = CLUSTER_GAP_DAYS,
) -> list[list[Review]]:
    """Group reviews into clusters chained by <=cluster_gap_days gaps.
    Only clusters with >=2 reviews are returned (solo reviews don't freeze)."""
    if not reviews:
        return []
    sorted_r = sorted(reviews, key=lambda r: r.closes_at)
    clusters: list[list[Review]] = [[sorted_r[0]]]
    for r in sorted_r[1:]:
        prev = clusters[-1][-1]
        if (r.closes_at - prev.closes_at).days <= cluster_gap_days:
            clusters[-1].append(r)
        else:
            clusters.append([r])
    return [c for c in clusters if len(c) >= 2]


def compute_freeze_windows(
    reviews: list[Review],
    pre_days: int = PRE_FREEZE_DAYS,
    post_days: int = POST_FREEZE_DAYS,
    cluster_gap_days: int = CLUSTER_GAP_DAYS,
) -> list[FreezeWindow]:
    return [
        FreezeWindow(
            start=c[0].closes_at - timedelta(days=pre_days),
            end=c[-1].closes_at + timedelta(days=post_days),
            reviews=c,
        )
        for c in compute_clusters(reviews, cluster_gap_days=cluster_gap_days)
    ]


def current_status(now: date, reviews: list[Review]) -> FreezeStatus:
    windows = compute_freeze_windows(reviews)
    active = next((w for w in windows if w.contains(now)), None)
    if active is not None:
        return FreezeStatus(
            frozen=True,
            as_of=now,
            active_window=active,
            days_until_unfreeze=(active.end - now).days,
        )
    upcoming = sorted(
        [w for w in windows if w.start > now],
        key=lambda w: w.start,
    )
    if upcoming:
        nxt = upcoming[0]
        return FreezeStatus(
            frozen=False,
            as_of=now,
            next_window=nxt,
            days_until_freeze=(nxt.start - now).days,
        )
    return FreezeStatus(frozen=False, as_of=now)


def window_to_dict(w: FreezeWindow) -> dict[str, Any]:
    return {
        "start": w.start.isoformat(),
        "end": w.end.isoformat(),
        "reviews": [
            {
                "name": r.name,
                "closes_at": r.closes_at.isoformat(),
                "kind": r.kind,
                "memory": r.memory,
            }
            for r in w.reviews
        ],
    }
