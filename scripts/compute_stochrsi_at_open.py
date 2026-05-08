#!/usr/bin/env python3
"""
StochRSI-at-open vs PnL cross-tab (Item 7 partial — pure observation).

Answers @newworldhoarder's open question on Moltbook: at what StochRSI value
does the entry rule actually outperform? The threshold is 0.25 by config —
but does opening at 0.05 (deep oversold) outperform opening at 0.20 (just
inside the threshold)?

Reads trade_log from sol_sniper.db (host-only, no API), regexes StochRSI@open
out of trigger_rule, bins by StochRSI value, computes win rate + avg PnL%
per bin. Writes web/public/data/stochrsi_at_open.json so it is publicly
verifiable as receipts (same pattern as compute_sortino.py).

Limitations:
- StochRSI@close is NOT logged in trade_log. So this answers "open value
  vs outcome" but NOT "open-and-still-falling" — the full pairing
  newworldhoarder asked about.
- Trades without a regex-matching trigger_rule (orphan reconciles, manual
  closes) are dropped. Drop-count is reported.

This script is read-only. It does not touch the executor, schema, or
any live trading state.

Usage:
  python3 scripts/compute_stochrsi_at_open.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

DB_PATH = Path("/Users/bonnyagent/ibitlabs/sol_sniper.db")
OUT_PATH = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "stochrsi_at_open.json"

STOCHRSI_RE = re.compile(r"StochRSI=([0-9]+\.?[0-9]*)")
# Only consider v5.1 mean-reversion oversold entries — earlier strategy versions
# used StochRSI=0.98+ overbought-breakout triggers, which is a different
# population. Mixing them is a strategy-version error.
TRIGGER_FILTER_LIKE = "%StochRSI=%oversold (thresh=%"
STRATEGY_FILTER = "hybrid_v5.1"

# Bins are open-left, closed-right except the last which is closed-both:
# [0.00-0.05], (0.05-0.10], (0.10-0.15], (0.15-0.20], (0.20-0.25]
BIN_EDGES = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25]


def bin_for(value: float) -> str:
    if value <= BIN_EDGES[0]:
        return f"[{BIN_EDGES[0]:.2f}–{BIN_EDGES[1]:.2f}]"
    for lo, hi in zip(BIN_EDGES[:-1], BIN_EDGES[1:]):
        if lo < value <= hi:
            return f"({lo:.2f}–{hi:.2f}]"
    return f">{BIN_EDGES[-1]:.2f}"


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.execute("""
        SELECT id, direction, entry_price, exit_price, pnl, mfe, mae, trigger_rule
        FROM trade_log
        WHERE exit_price IS NOT NULL
          AND entry_price IS NOT NULL
          AND trigger_rule LIKE ?
          AND strategy_version = ?
        ORDER BY id ASC
    """, (TRIGGER_FILTER_LIKE, STRATEGY_FILTER))
    rows = cur.fetchall()
    conn.close()

    parsed: list[dict] = []
    skipped_no_match = 0
    for r in rows:
        m = STOCHRSI_RE.search(r["trigger_rule"] or "")
        if not m:
            skipped_no_match += 1
            continue
        try:
            stoch = float(m.group(1))
        except ValueError:
            skipped_no_match += 1
            continue
        ep = float(r["entry_price"])
        xp = float(r["exit_price"])
        sign = 1.0 if (r["direction"] or "long").lower() == "long" else -1.0
        pnl_pct = (xp - ep) / ep * sign
        parsed.append({
            "id": r["id"],
            "stochrsi_at_open": stoch,
            "pnl_pct": pnl_pct,
            "pnl_usd": float(r["pnl"] or 0.0),
            "direction": r["direction"],
        })

    # Bin
    buckets: dict[str, list[dict]] = {}
    for t in parsed:
        b = bin_for(t["stochrsi_at_open"])
        buckets.setdefault(b, []).append(t)

    bin_stats = []
    for label in [
        f"[{BIN_EDGES[0]:.2f}–{BIN_EDGES[1]:.2f}]",
        f"({BIN_EDGES[0]:.2f}–{BIN_EDGES[1]:.2f}]",  # only used if bin_for returned this; defensive
    ] + [f"({lo:.2f}–{hi:.2f}]" for lo, hi in zip(BIN_EDGES[1:-1], BIN_EDGES[2:])] + [f">{BIN_EDGES[-1]:.2f}"]:
        if label not in buckets:
            continue
        ts = buckets[label]
        wins = [t for t in ts if t["pnl_pct"] > 0]
        losses = [t for t in ts if t["pnl_pct"] <= 0]
        bin_stats.append({
            "bin": label,
            "n": len(ts),
            "n_wins": len(wins),
            "n_losses": len(losses),
            "win_rate_pct": round(len(wins) / len(ts) * 100, 2) if ts else 0.0,
            "avg_pnl_pct": round(statistics.fmean(t["pnl_pct"] for t in ts) * 100, 4),
            "median_pnl_pct": round(statistics.median(t["pnl_pct"] for t in ts) * 100, 4),
            "total_pnl_usd": round(sum(t["pnl_usd"] for t in ts), 2),
            "stochrsi_min": round(min(t["stochrsi_at_open"] for t in ts), 4),
            "stochrsi_max": round(max(t["stochrsi_at_open"] for t in ts), 4),
        })

    # Overall correlation between stochrsi_at_open and pnl_pct (Spearman-style via ranks)
    if len(parsed) >= 5:
        xs = [t["stochrsi_at_open"] for t in parsed]
        ys = [t["pnl_pct"] for t in parsed]
        n = len(xs)
        mean_x = statistics.fmean(xs)
        mean_y = statistics.fmean(ys)
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den_x = (sum((x - mean_x) ** 2 for x in xs)) ** 0.5
        den_y = (sum((y - mean_y) ** 2 for y in ys)) ** 0.5
        pearson = (num / (den_x * den_y)) if (den_x * den_y) > 0 else 0.0
    else:
        pearson = None

    out = {
        "computed_at_unix": int(time.time()),
        "strategy_version": STRATEGY_FILTER,
        "trigger_filter": TRIGGER_FILTER_LIKE,
        "n_v51_oversold_closed": len(rows),
        "n_with_stochrsi": len(parsed),
        "n_skipped_no_match": skipped_no_match,
        "stochrsi_threshold_at_open": 0.25,
        "bins": bin_stats,
        "pearson_stochrsi_vs_pnl_pct": round(pearson, 4) if pearson is not None else None,
        "interpretation": (
            "Negative Pearson means lower StochRSI@open associates with higher PnL — "
            "deeper oversold entries outperform shallower ones, supporting the threshold. "
            "Near-zero Pearson means the threshold gates entry but doesn't grade it: "
            "depth of oversold inside the threshold is not a signal. Positive Pearson "
            "would mean shallower entries outperform — the threshold is mis-calibrated."
        ),
        "limitation_notes": [
            "StochRSI at close is NOT logged in trade_log; this answers 'open value vs outcome', "
            "not '@newworldhoarder full pairing' (open vs still-falling-at-close).",
            "Trades without regex-matching trigger_rule (orphan reconciles, manual closes) dropped.",
            "Bins are open-left, closed-right; the deepest bucket [0.00–0.05] is closed-both.",
        ],
        "comment_source": "Polanyi-adjacent question from @newworldhoarder on Moltbook (paired-StochRSI under-thought-property)",
    }

    print(f"\n=== StochRSI@open vs PnL cross-tab ({STRATEGY_FILTER} oversold only) ===\n")
    print(f"  v5.1 oversold closed:         {len(rows)}")
    print(f"  With regex StochRSI@open:     {len(parsed)}")
    print(f"  Skipped (no regex match):     {skipped_no_match}")
    print(f"  *Sample is small (n={len(parsed)}); cross-tab is exploratory, not conclusive.")
    print()
    print(f"  {'Bin':<14}  {'n':>3}  {'WR%':>6}  {'avg PnL%':>9}  {'med PnL%':>9}  {'Σ USD':>9}")
    print(f"  {'─'*14}  {'─'*3}  {'─'*6}  {'─'*9}  {'─'*9}  {'─'*9}")
    for b in bin_stats:
        print(f"  {b['bin']:<14}  {b['n']:>3}  {b['win_rate_pct']:>5.1f}%  "
              f"{b['avg_pnl_pct']:>8.3f}%  {b['median_pnl_pct']:>8.3f}%  {b['total_pnl_usd']:>9.2f}")
    print()
    print(f"  Pearson(StochRSI@open, PnL%): {pearson:.4f}" if pearson is not None else
          "  Pearson: insufficient data")
    print()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"  Written: {OUT_PATH.relative_to(OUT_PATH.parent.parent.parent)}")
    print()


if __name__ == "__main__":
    main()
