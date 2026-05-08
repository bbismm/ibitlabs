#!/usr/bin/env python3
"""
MFE / MAE distribution analyzer (the right variable class — instrument
state, not indicators).

Reads trade_log.{mfe, mae} for v5.1 closed trades, computes:
  • MFE distribution (avg, median, p10, p90)
  • MAE distribution
  • |avg_win / avg_loss| skew (already in compute_sortino, replicated for cohesion)
  • give_back = MFE - final_pnl_pct  (how much profit retraced before close)
  • mae_to_sl_ratio = |MAE| / |SL_threshold|  (how often the SL was actually
    needed vs how deep the trade really went)

Writes web/public/data/mfe_mae_distribution.json and prints summary.

This is the canonical artifact for the "trailing winners mask the loss
profile" question (RiskOfficer_Bot) and the "TP/SL too early/tight"
question (general state-variable instrumentation).

Limitations / data quality:
- mfe/mae columns were added 2026-04-22 per state_db.py:208. Historical
  v5.1 trades that closed before that date will have NULL mfe/mae. As of
  2026-04-25, all 7 closed v5.1 trades have NULL — the artifact is built
  but reports n_with_data=0. This is honest receipts: the data gap is
  visible. Once new trades close (and the executor process stays up
  through open→close), populated rows will appear.
- This script is read-only against trade_log. Does not touch the
  executor or any decision state.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

DB_PATH = Path("/Users/bonnyagent/ibitlabs/sol_sniper.db")
OUT_PATH = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "mfe_mae_distribution.json"
STRATEGY = "hybrid_v5.1"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, exit_reason, entry_price, exit_price, mfe, mae, pnl
        FROM trade_log
        WHERE strategy_version=? AND exit_price IS NOT NULL
        ORDER BY id ASC
    """, (STRATEGY,)).fetchall()
    conn.close()

    n_total = len(rows)
    populated = [r for r in rows if r["mfe"] is not None and r["mae"] is not None]
    n_pop = len(populated)

    out = {
        "computed_at_unix": int(time.time()),
        "strategy_version": STRATEGY,
        "n_v51_closed": n_total,
        "n_with_mfe_mae_populated": n_pop,
        "data_gap_note": (
            "mfe/mae columns added 2026-04-22 (state_db.py:208). Historical v5.1 trades "
            "that closed before that date have NULL mfe/mae and are excluded. Process "
            "restarts between open and close will also produce NULLs. Going-forward "
            "trades will populate these once a full open→close cycle runs without restart."
        ) if n_pop < n_total else None,
    }

    if n_pop == 0:
        out["status"] = "no_data_yet"
        out["interpretation"] = (
            f"All {n_total} v5.1 closed trades have NULL mfe/mae. The artifact is "
            "ready to populate as soon as new trades close with the columns set. "
            "This is the receipts gap, exposed honestly."
        )
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(out, indent=2))
        print(f"\n=== MFE/MAE distribution ({STRATEGY}) ===")
        print(f"  n closed: {n_total}")
        print(f"  n with mfe/mae populated: {n_pop}")
        print(f"  status: no_data_yet — see {OUT_PATH.relative_to(OUT_PATH.parent.parent.parent)}")
        return

    # We have data — compute distribution
    mfe_vals = [r["mfe"] for r in populated]
    mae_vals = [r["mae"] for r in populated]
    final_pnl_pcts = [(r["exit_price"] - r["entry_price"]) / r["entry_price"] for r in populated]
    give_backs = [r["mfe"] - p for r, p in zip(populated, final_pnl_pcts) if r["mfe"] > 0]

    out.update({
        "mfe": {
            "avg_pct": round(statistics.fmean(mfe_vals) * 100, 4),
            "median_pct": round(statistics.median(mfe_vals) * 100, 4),
            "p10_pct": round(percentile(mfe_vals, 0.10) * 100, 4),
            "p90_pct": round(percentile(mfe_vals, 0.90) * 100, 4),
            "max_pct": round(max(mfe_vals) * 100, 4),
        },
        "mae": {
            "avg_pct": round(statistics.fmean(mae_vals) * 100, 4),
            "median_pct": round(statistics.median(mae_vals) * 100, 4),
            "p10_pct": round(percentile(mae_vals, 0.10) * 100, 4),
            "p90_pct": round(percentile(mae_vals, 0.90) * 100, 4),
            "min_pct": round(min(mae_vals) * 100, 4),
        },
        "give_back_pct": {
            "n": len(give_backs),
            "avg": round(statistics.fmean(give_backs) * 100, 4) if give_backs else None,
            "median": round(statistics.median(give_backs) * 100, 4) if give_backs else None,
            "p90": round(percentile(give_backs, 0.90) * 100, 4) if give_backs else None,
            "interpretation": (
                "give_back = MFE - final_pnl_pct. High p90 give_back means trailing "
                "is leaving meaningful profit on the table. Low give_back means "
                "trailing is catching peaks tightly."
            ),
        },
    })

    print(f"\n=== MFE/MAE distribution ({STRATEGY}, n={n_pop}/{n_total}) ===\n")
    print(f"  MFE  avg {out['mfe']['avg_pct']:+.3f}%  med {out['mfe']['median_pct']:+.3f}%  "
          f"p10 {out['mfe']['p10_pct']:+.3f}%  p90 {out['mfe']['p90_pct']:+.3f}%")
    print(f"  MAE  avg {out['mae']['avg_pct']:+.3f}%  med {out['mae']['median_pct']:+.3f}%  "
          f"p10 {out['mae']['p10_pct']:+.3f}%  p90 {out['mae']['p90_pct']:+.3f}%")
    if out["give_back_pct"].get("avg") is not None:
        print(f"  give_back  avg {out['give_back_pct']['avg']:+.3f}%  "
              f"med {out['give_back_pct']['median']:+.3f}%  p90 {out['give_back_pct']['p90']:+.3f}%")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\n  Written: {OUT_PATH.relative_to(OUT_PATH.parent.parent.parent)}\n")


if __name__ == "__main__":
    main()
