#!/usr/bin/env python3
"""
Shadow ExitScore calibration — closes the loop on position_telemetry's
shadow_would_exit signal. For each closed position observed by the sidecar,
join to the actual trade_log close and answer: when shadow first said
"exit", was that better or worse than the live exit logic's eventual call?

Read-only. Joins:
  - position_telemetry (shadow signal ticks, per 60s)
  - trade_log         (paired BUY open / SELL close rows)

Output: web/public/data/shadow_exitscore_calibration.json
Schedule: nightly via com.ibitlabs.shadow-calibration-nightly (after
mfe-mae-nightly so any column updates have settled).

Honest-zero mode: until at least one position observed by the sidecar
has a matching SELL in trade_log, output reports n_closed=0 and the
gap reason. Same pattern as compute_mfe_mae.py.

Pairing logic:
  - position_key in telemetry = "{symbol}:{direction}:{entry_price:.4f}"
  - find trade_log BUY row(s) matching symbol+direction+entry_price
  - the BUY's "close" is the next SELL row in id order with same direction
  - SELL.exit_reason / SELL.pnl / SELL.exit_price give actual outcome
  - if no SELL found yet, position still open → skip

Calibration metric (per closed position):
  - shadow_first_signal_ts: ts of first tick with shadow_would_exit=1
  - shadow_lead_minutes: minutes between shadow's first signal and actual close
  - pnl_pct_at_shadow_signal: pnl_pct in the tick where shadow first fired
  - pnl_pct_at_actual_close: derived from trade_log entry/exit price (long:
    (exit-entry)/entry; short: (entry-exit)/entry — fee-naive, comparable)
  - delta_pp: pnl_pct_at_actual_close - pnl_pct_at_shadow_signal
    (positive = waiting was better; negative = shadow would have been better)
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

DB_PATH = Path("/Users/bonnyagent/ibitlabs/sol_sniper.db")
OUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "web" / "public" / "data" / "shadow_exitscore_calibration.json"
)

ENTRY_PRICE_TOLERANCE = 0.0005  # match telemetry's :.4f rounding


def find_matching_close(
    conn: sqlite3.Connection,
    symbol: str,
    direction: str,
    entry_price: float,
    first_telemetry_ts: int,
) -> dict | None:
    """Find the SELL row that closes a BUY at this symbol/direction/entry_price.

    Strategy: locate BUY rows in trade_log matching the entry, then the next
    SELL in id order with same direction is the close. Use the BUY whose
    timestamp is closest to (and ≤) first_telemetry_ts to disambiguate
    repeated entries at the same price.
    """
    buys = conn.execute(
        """
        SELECT id, timestamp FROM trade_log
        WHERE symbol = ? AND direction = ? AND side = 'BUY'
          AND ABS(entry_price - ?) < ?
        ORDER BY id ASC
        """,
        (symbol, direction, entry_price, ENTRY_PRICE_TOLERANCE),
    ).fetchall()
    if not buys:
        return None

    # Pick the BUY whose timestamp is closest to (and ≤) the sidecar's
    # first observation of this key. If sidecar started mid-trade, first
    # observation lags entry — we want the most recent BUY ≤ first_seen.
    buy_id, buy_ts = None, None
    for b_id, b_ts in buys:
        if b_ts <= first_telemetry_ts + 60:  # 60s grace
            buy_id, buy_ts = b_id, b_ts
    if buy_id is None:
        # All matching BUYs are AFTER first sidecar observation — pick earliest
        buy_id, buy_ts = buys[0]

    sell = conn.execute(
        """
        SELECT id, timestamp, exit_reason, pnl, exit_price, entry_price, fees
        FROM trade_log
        WHERE id > ? AND symbol = ? AND direction = ? AND side = 'SELL'
        ORDER BY id ASC LIMIT 1
        """,
        (buy_id, symbol, direction),
    ).fetchone()
    if not sell:
        return None

    sell_id, sell_ts, exit_reason, pnl, exit_price, sell_entry, fees = sell
    return {
        "buy_id": buy_id,
        "buy_ts": buy_ts,
        "sell_id": sell_id,
        "sell_ts": sell_ts,
        "exit_reason": exit_reason,
        "pnl_usd": pnl,
        "exit_price": exit_price,
        "entry_price": sell_entry,
        "fees": fees,
    }


def pnl_pct_from_prices(direction: str, entry: float, exit_: float) -> float:
    if entry <= 0:
        return 0.0
    if direction == "long":
        return (exit_ - entry) / entry
    return (entry - exit_) / entry


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    has_pt = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='position_telemetry'"
    ).fetchone()
    if not has_pt:
        out = {
            "computed_at_unix": int(time.time()),
            "n_closed_in_telemetry": 0,
            "status": "table_not_initialized",
            "interpretation": "position_telemetry table does not yet exist; sidecar has not run.",
        }
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(out, indent=2))
        print("position_telemetry table missing — wrote placeholder")
        return

    keys = conn.execute(
        """
        SELECT position_key, symbol, direction, entry_price,
               MIN(ts) AS first_seen, MAX(ts) AS last_seen, COUNT(*) AS ticks
        FROM position_telemetry
        GROUP BY position_key
        ORDER BY first_seen ASC
        """
    ).fetchall()

    if not keys:
        out = {
            "computed_at_unix": int(time.time()),
            "n_closed_in_telemetry": 0,
            "status": "no_observations_yet",
            "interpretation": "Sidecar has not recorded any position ticks yet.",
        }
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(out, indent=2))
        print("no telemetry ticks — wrote placeholder")
        return

    closed_calibrations = []
    open_observations = []
    unmatched_keys = []

    for k in keys:
        pos_key = k["position_key"]
        symbol = k["symbol"]
        direction = k["direction"]
        entry_price = float(k["entry_price"] or 0.0)
        first_seen = int(k["first_seen"])
        last_seen = int(k["last_seen"])

        match = find_matching_close(conn, symbol, direction, entry_price, first_seen)
        if not match or match["sell_ts"] < first_seen:
            # Either no close yet, or the matched SELL is older than our
            # first observation (means sidecar is observing the next trade
            # at same entry — rare but defensible to skip).
            now = int(time.time())
            still_active = (now - last_seen) < 300
            (open_observations if still_active else unmatched_keys).append({
                "position_key": pos_key,
                "first_seen_ts": first_seen,
                "last_seen_ts": last_seen,
                "ticks_observed": int(k["ticks"]),
                "still_active_recent_tick": still_active,
            })
            continue

        # Find shadow's first would_exit=1 tick for this position
        first_signal = conn.execute(
            """
            SELECT ts, pnl_pct, highest_pnl, drawdown_from_peak,
                   elapsed_mins, exit_score_shadow, regime
            FROM position_telemetry
            WHERE position_key = ? AND shadow_would_exit = 1
            ORDER BY ts ASC LIMIT 1
            """,
            (pos_key,),
        ).fetchone()

        # Tick counts
        ticks_total = int(k["ticks"])
        would_exit_ticks = conn.execute(
            "SELECT COUNT(*) FROM position_telemetry WHERE position_key = ? AND shadow_would_exit = 1",
            (pos_key,),
        ).fetchone()[0]

        actual_close_ts = int(match["sell_ts"])
        actual_pnl_pct = pnl_pct_from_prices(
            direction, float(match["entry_price"] or entry_price), float(match["exit_price"] or 0.0)
        )

        if first_signal:
            shadow_ts = int(first_signal["ts"])
            shadow_pnl_pct = float(first_signal["pnl_pct"] or 0.0)
            shadow_lead_mins = round((actual_close_ts - shadow_ts) / 60.0, 2)
            delta_pp = round((actual_pnl_pct - shadow_pnl_pct) * 100, 4)
            verdict = (
                "shadow_better" if delta_pp < -0.10
                else "shadow_worse" if delta_pp > 0.10
                else "neutral"
            )
        else:
            shadow_ts = None
            shadow_pnl_pct = None
            shadow_lead_mins = None
            delta_pp = None
            verdict = "shadow_never_fired"

        closed_calibrations.append({
            "position_key": pos_key,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": match["exit_price"],
            "exit_reason": match["exit_reason"],
            "actual_pnl_usd": match["pnl_usd"],
            "actual_pnl_pct": round(actual_pnl_pct * 100, 4),
            "actual_close_ts": actual_close_ts,
            "actual_hold_mins": round((actual_close_ts - match["buy_ts"]) / 60.0, 2),
            "ticks_observed": ticks_total,
            "would_exit_ticks": would_exit_ticks,
            "shadow_first_signal_ts": shadow_ts,
            "shadow_pnl_pct_at_signal": (
                round(shadow_pnl_pct * 100, 4) if shadow_pnl_pct is not None else None
            ),
            "shadow_lead_mins_before_close": shadow_lead_mins,
            "delta_pp_actual_minus_shadow": delta_pp,
            "verdict": verdict,
        })

    n_closed = len(closed_calibrations)
    aggregates = None
    if n_closed > 0:
        deltas = [c["delta_pp_actual_minus_shadow"] for c in closed_calibrations
                  if c["delta_pp_actual_minus_shadow"] is not None]
        leads = [c["shadow_lead_mins_before_close"] for c in closed_calibrations
                 if c["shadow_lead_mins_before_close"] is not None]
        aggregates = {
            "n_with_shadow_signal": len(deltas),
            "shadow_better_count": sum(1 for c in closed_calibrations if c["verdict"] == "shadow_better"),
            "shadow_worse_count": sum(1 for c in closed_calibrations if c["verdict"] == "shadow_worse"),
            "neutral_count": sum(1 for c in closed_calibrations if c["verdict"] == "neutral"),
            "shadow_never_fired_count": sum(1 for c in closed_calibrations if c["verdict"] == "shadow_never_fired"),
            "median_delta_pp": round(statistics.median(deltas), 4) if deltas else None,
            "mean_delta_pp": round(statistics.fmean(deltas), 4) if deltas else None,
            "median_shadow_lead_mins": round(statistics.median(leads), 2) if leads else None,
        }

    out = {
        "computed_at_unix": int(time.time()),
        "n_closed_in_telemetry": n_closed,
        "n_open_observed": len(open_observations),
        "n_unmatched_keys": len(unmatched_keys),
        "status": "ok" if n_closed > 0 else "no_closed_observations_yet",
        "interpretation": (
            f"{n_closed} position(s) observed by sidecar have closed in trade_log. "
            "delta_pp_actual_minus_shadow > 0 means waiting beat shadow's exit; "
            "< 0 means shadow's exit would have been better. neutral band = ±0.10pp. "
            "Shadow weights are uncalibrated seeds; verdict is data, not authority."
        ) if n_closed > 0 else (
            "Sidecar has observed at least one position but no matching SELL in "
            "trade_log yet. The artifact will populate as soon as the next live "
            "close arrives. This is the receipts gap, exposed honestly."
        ),
        "shadow_weights": {
            "W_PNL": 1.0, "W_DRAWDOWN": -2.0, "W_DURATION_HRS": -0.5, "W_VOL_RATIO": 0.3,
            "EXIT_THRESHOLD": 0.0,
            "calibration_note": "Raw-hour duration term currently dominates; weights need rescaling before promotion. See position_telemetry.py docstring.",
        },
        "closed_calibrations": closed_calibrations,
        "open_observations": open_observations,
        "unmatched_keys": unmatched_keys,
        "aggregates": aggregates,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))

    print("\n=== shadow ExitScore calibration ===\n")
    print(f"  closed_in_telemetry: {n_closed}  open_observed: {len(open_observations)}  unmatched: {len(unmatched_keys)}")
    if aggregates:
        print(f"  shadow_better: {aggregates['shadow_better_count']}  "
              f"shadow_worse: {aggregates['shadow_worse_count']}  "
              f"neutral: {aggregates['neutral_count']}  "
              f"never_fired: {aggregates['shadow_never_fired_count']}")
        print(f"  median Δpp (actual − shadow): {aggregates['median_delta_pp']}  "
              f"median shadow lead: {aggregates['median_shadow_lead_mins']} min")
    for c in closed_calibrations[-5:]:
        print(f"  {c['position_key']}  "
              f"actual={c['actual_pnl_pct']:+.3f}%  "
              f"shadow_signal={c['shadow_pnl_pct_at_signal']}  "
              f"Δpp={c['delta_pp_actual_minus_shadow']}  "
              f"lead={c['shadow_lead_mins_before_close']}min  "
              f"verdict={c['verdict']}")
    for o in open_observations:
        print(f"  [open] {o['position_key']}  ticks={o['ticks_observed']}")
    print(f"\n  Written: {OUT_PATH.relative_to(OUT_PATH.parent.parent.parent)}\n")

    conn.close()


if __name__ == "__main__":
    main()
