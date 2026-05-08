#!/usr/bin/env python3
"""
Aggregator for position_telemetry sidecar data. Reads the table written
every 60s by position_telemetry.py, computes per-position trajectory
metrics, and writes web/public/data/position_telemetry_summary.json.

What this captures (the right state-variable class — not indicators):
  · per-position MFE evolution (path-max profit)
  · per-position MAE-from-observation (path-min profit since sidecar started watching)
  · drawdown-from-peak distribution per position
  · time-to-MFE in seconds (how fast did the win reveal itself?)
  · current shadow ExitScore + threshold + would-exit count

This is the receipts moat for the variable-class hierarchy memo: PnL,
drawdown-from-peak, duration, vol_ratio. NOT indicators (StochRSI etc.).

Limitations / data quality:
  · MAE here is "lowest pnl_pct observed BY THE SIDECAR" — if sidecar
    started after the position was already underwater, the true MAE is
    deeper. Position #63 has been open since before sidecar began
    (2026-04-25), so its MAE shown here is a lower bound, not the truth.
  · time-to-MFE is the time the sidecar OBSERVED the peak — same caveat:
    if the peak happened before sidecar started, value is misleading.
  · Becomes accurate from the first position opened AFTER sidecar boot.

Read-only against position_telemetry; writes JSON only. No mutation.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

DB_PATH = Path("/Users/bonnyagent/ibitlabs/sol_sniper.db")
OUT_PATH = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "position_telemetry_summary.json"


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Existence check
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='position_telemetry'"
    ).fetchone()
    if not has_table:
        out = {
            "computed_at_unix": int(time.time()),
            "status": "table_not_initialized",
            "interpretation": "position_telemetry table does not yet exist; sidecar has not run.",
        }
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(out, indent=2))
        print("table not yet created — wrote no_data placeholder")
        return

    rows = conn.execute("""
        SELECT ts, position_key, pnl_pct, highest_pnl, elapsed_mins,
               drawdown_from_peak, vol_ratio, bb_width_pct, regime,
               exit_score_shadow, exit_score_threshold, shadow_would_exit
        FROM position_telemetry
        ORDER BY ts ASC
    """).fetchall()
    conn.close()

    n_ticks = len(rows)
    if n_ticks == 0:
        out = {
            "computed_at_unix": int(time.time()),
            "status": "no_ticks_yet",
            "interpretation": "Table exists but has no rows. No position has been observed yet.",
        }
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(out, indent=2))
        print("no rows in position_telemetry yet")
        return

    # Group by position_key
    positions: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        positions.setdefault(r["position_key"], []).append(r)

    position_summaries = []
    for key, ticks in positions.items():
        first = ticks[0]
        last = ticks[-1]
        pnls = [t["pnl_pct"] for t in ticks]
        highest_observed = max(t["highest_pnl"] for t in ticks)
        # Find first tick where highest_pnl reached its observed peak
        time_to_mfe_sec: int | None = None
        for t in ticks:
            if t["highest_pnl"] >= highest_observed:
                time_to_mfe_sec = t["ts"] - first["ts"]
                break
        peak_dd = max(t["drawdown_from_peak"] for t in ticks)
        score_min = min(t["exit_score_shadow"] for t in ticks)
        score_max = max(t["exit_score_shadow"] for t in ticks)
        would_exit_count = sum(1 for t in ticks if t["shadow_would_exit"] == 1)

        position_summaries.append({
            "position_key": key,
            "first_seen_ts": first["ts"],
            "last_seen_ts": last["ts"],
            "tick_count": len(ticks),
            "duration_observed_min": round((last["ts"] - first["ts"]) / 60.0, 2),
            "pnl_first_pct": round(first["pnl_pct"] * 100, 4),
            "pnl_last_pct": round(last["pnl_pct"] * 100, 4),
            "pnl_min_observed_pct": round(min(pnls) * 100, 4),
            "pnl_max_observed_pct": round(max(pnls) * 100, 4),
            "mfe_observed_pct": round(highest_observed * 100, 4),
            "mae_observed_pct": round(min(pnls) * 100, 4),
            "peak_drawdown_pct": round(peak_dd * 100, 4),
            "time_to_observed_mfe_sec": time_to_mfe_sec,
            "shadow_score_min": round(score_min, 4),
            "shadow_score_max": round(score_max, 4),
            "shadow_score_last": round(last["exit_score_shadow"], 4),
            "shadow_threshold": last["exit_score_threshold"],
            "would_exit_tick_count": would_exit_count,
            "regime_last": last["regime"],
            "vol_ratio_last": last["vol_ratio"],
            "bb_width_pct_last": round(last["bb_width_pct"] * 100, 4),
            "still_open": (time.time() - last["ts"]) < 300,
        })

    # Cross-position aggregates (when n_positions > 1)
    closed = [p for p in position_summaries if not p["still_open"]]
    aggregates = None
    if closed:
        aggregates = {
            "n_closed_in_telemetry": len(closed),
            "avg_mfe_pct": round(statistics.fmean(p["mfe_observed_pct"] for p in closed), 4),
            "avg_mae_pct": round(statistics.fmean(p["mae_observed_pct"] for p in closed), 4),
            "avg_peak_drawdown_pct": round(statistics.fmean(p["peak_drawdown_pct"] for p in closed), 4),
            "avg_time_to_mfe_sec": round(
                statistics.fmean(p["time_to_observed_mfe_sec"] or 0 for p in closed), 2
            ),
        }

    out = {
        "computed_at_unix": int(time.time()),
        "n_ticks_total": n_ticks,
        "n_positions_observed": len(positions),
        "n_positions_open_now": sum(1 for p in position_summaries if p["still_open"]),
        "first_tick_ts": rows[0]["ts"],
        "last_tick_ts": rows[-1]["ts"],
        "positions": position_summaries,
        "aggregates_over_closed": aggregates,
        "shadow_exitscore_calibration_note": (
            "Shadow ExitScore weights are uncalibrated seeds (W_PNL=1.0, W_DRAWDOWN=-2.0, "
            "W_DURATION_HRS=-0.5, W_VOL_RATIO=0.3). At raw-hour scale, duration term "
            "dominates. DO NOT promote shadow to live until weights produce same-magnitude "
            "terms. See feedback_zhi_yong.md and position_telemetry.py module docstring."
        ),
        "boundary_caveat": (
            "MFE/MAE/time-to-MFE values for any position open BEFORE sidecar boot "
            "(e.g. trade #63) are observation-bounded, not true. From the first "
            "position opened after sidecar boot, values reflect the full trajectory."
        ),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))

    print(f"\n=== position_telemetry summary ===\n")
    print(f"  ticks: {n_ticks}  positions observed: {len(positions)}  open now: {out['n_positions_open_now']}")
    for p in position_summaries:
        marker = "🟢" if p["still_open"] else "✓"
        print(f"  {marker} {p['position_key']}")
        print(f"     ticks={p['tick_count']}  dur_min={p['duration_observed_min']}  "
              f"pnl_last={p['pnl_last_pct']:+.3f}%  mfe={p['mfe_observed_pct']:+.3f}%  "
              f"mae={p['mae_observed_pct']:+.3f}%  peak_dd={p['peak_drawdown_pct']:.3f}%  "
              f"score_last={p['shadow_score_last']:+.2f}  would_exit_ticks={p['would_exit_tick_count']}/{p['tick_count']}")
    print(f"\n  Written: {OUT_PATH.relative_to(OUT_PATH.parent.parent.parent)}\n")


if __name__ == "__main__":
    main()
