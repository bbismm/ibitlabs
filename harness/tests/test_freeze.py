"""Smoke tests for harness/lib/freeze.py.

Run with: python3 -m pytest harness/tests/test_freeze.py
Or:       python3 harness/tests/test_freeze.py  (no pytest dep)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.lib.freeze import (
    Review,
    compute_clusters,
    compute_freeze_windows,
    current_status,
)


# Real 2026-05-14 review schedule from governance/reviews.yaml
SAMPLE_REVIEWS = [
    Review("24h_compound_shadow", date(2026, 5, 23), "shadow_review"),
    Review("rule_f_promotion", date(2026, 5, 31), "promotion_review"),
    Review("sl_hypotheses_h1_h2_h3", date(2026, 6, 1), "promotion_review"),
    Review("gate_4_review", date(2026, 6, 5), "promotion_review"),
    Review("h4_sideways_paper_auto_retire", date(2026, 6, 14), "auto_retire"),
]


def test_solo_reviews_do_not_cluster():
    """5-23 and 6-14 are >7d from their nearest neighbor, so they're solo."""
    clusters = compute_clusters(SAMPLE_REVIEWS)
    flat_names = {r.name for c in clusters for r in c}
    assert "24h_compound_shadow" not in flat_names
    assert "h4_sideways_paper_auto_retire" not in flat_names


def test_main_cluster_5_31_to_6_5():
    """5-31, 6-01, 6-05 chain by <=7d gaps -> single 3-review cluster."""
    clusters = compute_clusters(SAMPLE_REVIEWS)
    assert len(clusters) == 1
    c = clusters[0]
    assert [r.name for r in c] == [
        "rule_f_promotion",
        "sl_hypotheses_h1_h2_h3",
        "gate_4_review",
    ]


def test_freeze_window_padding():
    """Window = [first - 7d, last + 14d] = [2026-05-24, 2026-06-19]."""
    windows = compute_freeze_windows(SAMPLE_REVIEWS)
    assert len(windows) == 1
    w = windows[0]
    assert w.start == date(2026, 5, 24)
    assert w.end == date(2026, 6, 19)


def test_today_is_unfrozen_5_14():
    """As of 2026-05-14, freeze starts 5-24, so we're unfrozen with 10d to go."""
    s = current_status(date(2026, 5, 14), SAMPLE_REVIEWS)
    assert s.frozen is False
    assert s.next_window is not None
    assert s.next_window.start == date(2026, 5, 24)
    assert s.days_until_freeze == 10


def test_inside_freeze_5_31():
    """5-31 is inside the freeze window."""
    s = current_status(date(2026, 5, 31), SAMPLE_REVIEWS)
    assert s.frozen is True
    assert s.active_window is not None
    assert s.active_window.start == date(2026, 5, 24)
    assert s.active_window.end == date(2026, 6, 19)
    assert s.days_until_unfreeze == 19


def test_just_before_freeze_5_23():
    """5-23 (the boundary day before freeze) — still unfrozen."""
    s = current_status(date(2026, 5, 23), SAMPLE_REVIEWS)
    assert s.frozen is False
    assert s.days_until_freeze == 1


def test_just_after_freeze_6_20():
    """6-20 (day after freeze ends) — unfrozen, no upcoming cluster (h4 is solo)."""
    s = current_status(date(2026, 6, 20), SAMPLE_REVIEWS)
    assert s.frozen is False
    assert s.next_window is None


def test_empty_reviews():
    s = current_status(date(2026, 5, 14), [])
    assert s.frozen is False
    assert s.next_window is None


def test_two_reviews_exactly_at_cluster_boundary():
    """Two reviews exactly 7 days apart — should cluster (gap inclusive)."""
    reviews = [
        Review("a", date(2026, 5, 1), "promotion_review"),
        Review("b", date(2026, 5, 8), "promotion_review"),
    ]
    clusters = compute_clusters(reviews)
    assert len(clusters) == 1
    assert len(clusters[0]) == 2


def test_two_reviews_8_days_apart_no_cluster():
    """Two reviews 8 days apart — no cluster (gap exclusive at 8)."""
    reviews = [
        Review("a", date(2026, 5, 1), "promotion_review"),
        Review("b", date(2026, 5, 9), "promotion_review"),
    ]
    clusters = compute_clusters(reviews)
    assert clusters == []


if __name__ == "__main__":
    # No-pytest mode: run each test function, print pass/fail
    import inspect
    mod = sys.modules[__name__]
    tests = [(n, fn) for n, fn in inspect.getmembers(mod, inspect.isfunction) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  pass  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(0 if failed == 0 else 1)
