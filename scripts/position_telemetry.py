#!/usr/bin/env python3
"""
Position-state sidecar telemetry. Polls /api/live-status once per
invocation (intended to run every minute via launchd) and writes one
row to a NEW table `position_telemetry` in sol_sniper.db when a
position is open.

This is the executor-decoupled foundation for state-variable
instrumentation (per the variable-class hierarchy memo): captures
MFE / MAE trajectory, drawdown-from-peak, time-to-MFE, regime proxy,
and a SHADOW ExitScore that is computed but NEVER fed back to the
executor.

Why sidecar (not executor change):
- Executor source files are inviolable during structural-pause window.
- This script imports nothing from the executor, runs in its own process,
  and writes to a NEW table the executor never reads. Failure here cannot
  affect trading.

ExitScore = w₁·pnl + w₂·drawdown_from_peak + w₃·duration_hours + w₄·vol_ratio
(Per ChatGPT proposal 2026-04-25. Phase 1 = shadow only — recorded but not
acted upon. Phase 2/3 require explicit Bonny override of structural-pause.)

Read-only against trade_log + grid_orders. Writes only to position_telemetry.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

DB_PATH = Path("/Users/bonnyagent/ibitlabs/sol_sniper.db")
LIVE_STATUS_URL = "https://www.ibitlabs.com/api/live-status"

# ─── ExitScore hyperparameters (ChatGPT seed; uncalibrated) ──────────
# First-run observation 2026-04-25 on position #63 (72h, pnl -1.8%, mfe +0.4%):
# duration term (-0.5 × 72h = -36) dominates; pnl/drawdown/vol contribute <1.
# These weights need rescaling — likely duration should normalize against
# percentile of historical hold times rather than raw hours, OR the
# coefficient should drop to ~ -0.005. DO NOT promote shadow to live until
# weights produce a score whose terms are within the same order of magnitude.
W_PNL = 1.0
W_DRAWDOWN = -2.0       # negative — drawdown pulls score toward exit
W_DURATION_HRS = -0.5   # negative — RAW HOURS, NEEDS RECALIBRATION
W_VOL_RATIO = 0.3       # positive — high vol grants tolerance
EXIT_THRESHOLD = 0.0    # close-shadow if score < threshold


SCHEMA = """
CREATE TABLE IF NOT EXISTS position_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    position_key TEXT NOT NULL,
    symbol TEXT,
    direction TEXT,
    entry_price REAL,
    current_price REAL,
    pnl_pct REAL,
    highest_pnl REAL,
    elapsed_mins REAL,
    drawdown_from_peak REAL,
    vol_ratio REAL,
    bb_width_pct REAL,
    stoch_rsi REAL,
    regime TEXT,
    exit_score_shadow REAL,
    exit_score_threshold REAL,
    shadow_would_exit INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pt_position ON position_telemetry(position_key, ts);
CREATE INDEX IF NOT EXISTS idx_pt_ts ON position_telemetry(ts);
"""


def fetch_live_status() -> dict:
    req = urllib.request.Request(
        LIVE_STATUS_URL,
        headers={"User-Agent": "iBitLabs-position-telemetry/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def position_key_of(pos: dict, generated_at: int) -> str:
    # Stable per (symbol, direction, entry_price). Earlier version included
    # entry_unix derived from elapsed_mins, but elapsed_mins drifts across
    # ticks and that pushed the same position into adjacent 60s buckets,
    # producing duplicate keys (bug observed 2026-04-25). entry_price is
    # a float to 4 decimals; same exact entry on a re-open is improbable
    # in practice for SOL perp.
    sym = pos.get("symbol") or "UNKNOWN"
    direction = pos.get("direction") or "long"
    entry_price = float(pos.get("entry_price") or 0.0)
    return f"{sym}:{direction}:{entry_price:.4f}"


def compute_telemetry_row(d: dict, ts: int) -> dict | None:
    pos = d.get("position") or {}
    if not pos.get("active"):
        return None

    pnl_pct = float(pos.get("pnl_pct") or 0.0)
    highest_pnl = float(pos.get("highest_pnl") or 0.0)
    elapsed_mins = float(pos.get("elapsed_mins") or 0.0)
    duration_hours = elapsed_mins / 60.0
    drawdown_from_peak = max(0.0, highest_pnl - pnl_pct)

    indicators_pro = d.get("indicators_pro") or {}
    bb_upper = float(indicators_pro.get("bb_upper") or 0.0)
    bb_lower = float(indicators_pro.get("bb_lower") or 0.0)
    bb_mid = float(indicators_pro.get("bb_mid") or 0.0)
    bb_width_pct = ((bb_upper - bb_lower) / bb_mid) if bb_mid > 0 else 0.0
    vol_ratio = float(indicators_pro.get("vol_ratio") or 0.0)
    stoch_rsi = float(indicators_pro.get("stoch_rsi") or 0.0)
    regime = d.get("regime") or "unknown"

    # Shadow ExitScore — recorded but NEVER acted on
    exit_score = (
        W_PNL * pnl_pct
        + W_DRAWDOWN * drawdown_from_peak
        + W_DURATION_HRS * duration_hours
        + W_VOL_RATIO * vol_ratio
    )
    shadow_would_exit = 1 if exit_score < EXIT_THRESHOLD else 0

    return {
        "ts": ts,
        "position_key": position_key_of(pos, d.get("_ts_epoch", ts)),
        "symbol": pos.get("symbol"),
        "direction": pos.get("direction"),
        "entry_price": float(pos.get("entry_price") or 0.0),
        "current_price": float(pos.get("current_price") or 0.0),
        "pnl_pct": pnl_pct,
        "highest_pnl": highest_pnl,
        "elapsed_mins": elapsed_mins,
        "drawdown_from_peak": drawdown_from_peak,
        "vol_ratio": vol_ratio,
        "bb_width_pct": bb_width_pct,
        "stoch_rsi": stoch_rsi,
        "regime": regime,
        "exit_score_shadow": exit_score,
        "exit_score_threshold": EXIT_THRESHOLD,
        "shadow_would_exit": shadow_would_exit,
    }


def insert_row(conn: sqlite3.Connection, row: dict) -> None:
    keys = list(row.keys())
    placeholders = ", ".join("?" for _ in keys)
    cols = ", ".join(keys)
    conn.execute(
        f"INSERT INTO position_telemetry ({cols}) VALUES ({placeholders})",
        tuple(row[k] for k in keys),
    )
    conn.commit()


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        return 2

    try:
        d = fetch_live_status()
    except Exception as e:
        print(f"live-status fetch failed: {e}", file=sys.stderr)
        return 3

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.executescript(SCHEMA)

        ts = int(time.time())
        # live-status ts can be ISO string or epoch int — normalize to ts (epoch).
        d["_ts_epoch"] = ts
        row = compute_telemetry_row(d, ts)
        if row is None:
            # No active position — record nothing, exit clean
            print(f"no active position @ {ts}; skipping insert")
            return 0

        insert_row(conn, row)
        print(
            f"telemetry @ {ts}  key={row['position_key']}  "
            f"pnl={row['pnl_pct']*100:+.3f}%  "
            f"mfe={row['highest_pnl']*100:+.3f}%  "
            f"dd_peak={row['drawdown_from_peak']*100:.3f}%  "
            f"dur={row['elapsed_mins']/60:.2f}h  "
            f"shadow_score={row['exit_score_shadow']:+.4f}  "
            f"would_exit={row['shadow_would_exit']}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
