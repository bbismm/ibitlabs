#!/usr/bin/env python3
"""
Rolling Sortino + Sharpe analyzer for the iBitLabs live trade log.

Reads from /api/live-status (read-only — does NOT touch the trading bot,
DB schema, or any executor state). Computes:

  • Overall Sharpe (downside + upside deviation)
  • Overall Sortino (downside-only deviation)
  • Sortino / Sharpe ratio  ← @RiskOfficer_Bot's falsifier:
                              > 1.5x sustained 30d = structure
                              < 1.5x          = variance bailed you out
  • Rolling Sortino / Sharpe over a window (default 30 trades, since we only
    have 62 closed)
  • Min trade count for the ratio to stabilize within ±0.1 of its 62-trade value
    (bootstrap resampling — answers TM#2 Q1)

Writes:
  • web/public/data/trade_stats.json     (machine-readable, for /signals widget)
  • stdout summary

Usage:
  python3 scripts/compute_sortino.py
  python3 scripts/compute_sortino.py --window 20 --bootstrap 500
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import urllib.request
from pathlib import Path
from typing import Any

LIVE_STATUS_URL = "https://www.ibitlabs.com/api/live-status"
OUT_PATH = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "trade_stats.json"


def fetch_trade_history() -> list[dict[str, Any]]:
    req = urllib.request.Request(
        LIVE_STATUS_URL,
        headers={"User-Agent": "iBitLabs-sortino-analyzer/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    th = data.get("trade_history") or []
    if not th:
        sys.exit("trade_history is empty in live-status response")
    # live-status returns most-recent first; reverse to chronological for rolling windows
    return list(reversed(th))


def downside_dev(returns: list[float], target: float = 0.0) -> float:
    """Standard deviation of returns *below* the target (downside deviation)."""
    below = [min(r - target, 0.0) for r in returns]
    if len(below) < 2:
        return 0.0
    return math.sqrt(sum(b * b for b in below) / (len(below) - 1))


def upside_dev(returns: list[float], target: float = 0.0) -> float:
    above = [max(r - target, 0.0) for r in returns]
    if len(above) < 2:
        return 0.0
    return math.sqrt(sum(a * a for a in above) / (len(above) - 1))


def sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = statistics.fmean(returns)
    sd = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
    return (mean / sd) if sd > 0 else 0.0


def sortino(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = statistics.fmean(returns)
    dd = downside_dev(returns)
    return (mean / dd) if dd > 0 else 0.0


def rolling(returns: list[float], window: int, fn) -> list[float]:
    out = []
    for i in range(window, len(returns) + 1):
        out.append(fn(returns[i - window : i]))
    return out


def bootstrap_min_n(returns: list[float], target_ratio: float, tol: float = 0.1, samples: int = 500) -> int:
    """
    Resample sub-windows of growing size; find the minimum window n where
    the Sortino/Sharpe ratio over a random window of size n falls within
    ±tol of the full-sample ratio in >= 80% of samples.

    Answers TM#2 Q1: at 62 trades, is the ratio measuring strategy or noise?
    """
    import random

    rng = random.Random(42)
    full = sortino(returns) / sharpe(returns) if sharpe(returns) != 0 else float("nan")
    if math.isnan(full):
        return -1

    for n in range(10, len(returns) + 1, 2):
        hits = 0
        for _ in range(samples):
            sub = rng.sample(returns, n)
            sh = sharpe(sub)
            so = sortino(sub)
            if sh == 0:
                continue
            ratio = so / sh
            if abs(ratio - full) <= tol:
                hits += 1
        if hits / samples >= 0.80:
            return n
    return len(returns)  # never stabilized


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=30, help="Rolling window size (default 30)")
    ap.add_argument("--bootstrap", type=int, default=500, help="Bootstrap samples (default 500)")
    ap.add_argument("--tol", type=float, default=0.1, help="Stability tolerance (default ±0.1)")
    ap.add_argument("--no-write", action="store_true", help="Print only; don't write JSON artifact")
    args = ap.parse_args()

    trades = fetch_trade_history()
    pnl_pct = [t["pnl_pct"] for t in trades if t.get("pnl_pct") is not None]

    overall_sh = sharpe(pnl_pct)
    overall_so = sortino(pnl_pct)
    ratio = (overall_so / overall_sh) if overall_sh != 0 else float("nan")

    rolling_so = rolling(pnl_pct, args.window, sortino)
    rolling_sh = rolling(pnl_pct, args.window, sharpe)
    rolling_ratio = [(s / h) if h != 0 else 0.0 for s, h in zip(rolling_so, rolling_sh)]

    losses = [r for r in pnl_pct if r < 0]
    wins = [r for r in pnl_pct if r > 0]
    avg_win = statistics.fmean(wins) if wins else 0.0
    avg_loss = statistics.fmean(losses) if losses else 0.0
    win_loss_skew = abs(avg_win / avg_loss) if avg_loss < 0 else float("inf")

    min_n = bootstrap_min_n(pnl_pct, ratio, tol=args.tol, samples=args.bootstrap)

    # Caveat: the "Sortino > 1.5x Sharpe" test is calibrated for positive-Sharpe
    # strategies. When Sharpe is negative (losing strategy), the ratio loses its
    # original meaning — a high ratio in negative territory means downside is
    # MORE concentrated than total deviation, the opposite of structural edge.
    sharpe_is_negative = overall_sh < 0

    out = {
        "computed_at_unix": int(__import__("time").time()),
        "n_trades": len(pnl_pct),
        "overall": {
            "sharpe_per_trade": round(overall_sh, 4),
            "sortino_per_trade": round(overall_so, 4),
            "sortino_sharpe_ratio": round(ratio, 4),
            "sharpe_is_negative": sharpe_is_negative,
            "ratio_test_applicable": not sharpe_is_negative,
            "passes_riskofficer_test": (ratio >= 1.5) and (not sharpe_is_negative),
        },
        "rolling": {
            "window": args.window,
            "n_windows": len(rolling_ratio),
            "sortino": [round(x, 4) for x in rolling_so],
            "sharpe": [round(x, 4) for x in rolling_sh],
            "ratio": [round(x, 4) for x in rolling_ratio],
            "ratio_min": round(min(rolling_ratio), 4) if rolling_ratio else None,
            "ratio_max": round(max(rolling_ratio), 4) if rolling_ratio else None,
            "ratio_mean": round(statistics.fmean(rolling_ratio), 4) if rolling_ratio else None,
        },
        "win_loss_profile": {
            "n_wins": len(wins),
            "n_losses": len(losses),
            "avg_win_pct": round(avg_win * 100, 4),
            "avg_loss_pct": round(avg_loss * 100, 4),
            "win_loss_magnitude_skew": round(win_loss_skew, 3),
        },
        "stability": {
            "min_trades_for_ratio_stable_within_tol": min_n,
            "tol": args.tol,
            "interpretation": (
                f"At n={min_n}, the Sortino/Sharpe ratio falls within ±{args.tol} of its "
                f"full-sample value in 80% of bootstrap resamples. "
                f"Below this n, the ratio is dominated by sample noise."
            ),
        },
        "riskofficer_test": {
            "threshold": 1.5,
            "current_ratio": round(ratio, 4),
            "verdict": (
                "TEST_NOT_APPLICABLE — Sharpe is negative; the >1.5 threshold "
                "is calibrated for positive-Sharpe strategies. In negative-Sharpe "
                "territory a higher ratio means downside is MORE concentrated than "
                "total deviation, the opposite of structural edge. The test needs "
                "Sharpe > 0 first."
            ) if sharpe_is_negative else (
                "PASS — ratio >= 1.5 (edge has structure)" if ratio >= 1.5
                else f"FAIL — ratio {round(ratio, 3)} below 1.5 (variance, not structure)"
            ),
            "comment_source": "https://moltbook.com/post/bb08641e-1f4c-4bfc-b43f-ad6036c70e82 (RiskOfficer_Bot reply 9194bc42)",
        },
    }

    print("\n=== iBitLabs Sortino / Sharpe analysis ===\n")
    print(f"  Trades analyzed:        {out['n_trades']}")
    print(f"  Sharpe (per trade):     {out['overall']['sharpe_per_trade']}")
    print(f"  Sortino (per trade):    {out['overall']['sortino_per_trade']}")
    print(f"  Sortino/Sharpe ratio:   {out['overall']['sortino_sharpe_ratio']}")
    print(f"  RiskOfficer_Bot test:   {out['riskofficer_test']['verdict']}")
    print()
    print(f"  Rolling window:         {args.window} trades")
    print(f"  Rolling ratio range:    {out['rolling']['ratio_min']} → {out['rolling']['ratio_max']}")
    print(f"  Rolling ratio mean:     {out['rolling']['ratio_mean']}")
    print()
    print(f"  Win/loss magnitude skew (|avg_win/avg_loss|): {out['win_loss_profile']['win_loss_magnitude_skew']}")
    print(f"  (avg win {out['win_loss_profile']['avg_win_pct']}% / avg loss {out['win_loss_profile']['avg_loss_pct']}%)")
    print()
    print(f"  Stability bootstrap:    n={min_n} trades for ±{args.tol} stability (80% of resamples)")
    print(f"  → Below n={min_n}, the Sortino/Sharpe ratio is sample noise, not signal.")
    print()

    if not args.no_write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(out, indent=2))
        print(f"  Written: {OUT_PATH.relative_to(OUT_PATH.parent.parent.parent)}")
    print()


if __name__ == "__main__":
    main()
