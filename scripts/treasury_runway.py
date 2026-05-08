#!/usr/bin/env python3
"""
treasury_runway.py — Compute how many days the AI can survive on its savings.

Phase A of the AI Treasury experiment (see docs/AI_TREASURY_V0.md §2).

Formula:
    profit_pool  = realized_profit_since_inception           (principal is untouchable)
    daily_burn   = state/treasury_cost.json.total_usd_per_day
    runway_days  = profit_pool / daily_burn

Rules:
  - Principal floor is $1,000 USDC. The AI is not allowed to spend it.
  - Only REALIZED trading profit counts. Unrealized PnL does not pay the rent.
  - If realized profit is zero, runway = 0 days ("paycheck-to-paycheck").
  - If realized profit is negative, runway < 0 ("in debt to creator"),
    which is published honestly.

Data sources:
  - state/treasury_cost.json  (written by scripts/treasury_cost.py)
  - sol_sniper.db trade_log   (read-only, shared by Sniper V3 + Micro Grid V3)

This script makes NO network calls and NO writes to the trading DB. It is
a pure observation layer — safe to run while the live bot is trading.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
PRINCIPAL_FLOOR_USD = 1_000.00   # seed capital, never counted as profit
RUNWAY_MILESTONE_DAYS = 90       # progress-bar max shown on dashboard

# ─── Paths ───────────────────────────────────────────────────────────────────
REPO_ROOT        = Path(__file__).resolve().parent.parent
STATE_DIR        = REPO_ROOT / "state"
COST_FILE        = STATE_DIR / "treasury_cost.json"
OUTPUT_FILE      = STATE_DIR / "treasury_runway.json"
TRADE_DB         = REPO_ROOT / "sol_sniper.db"


def load_cost() -> dict:
    if not COST_FILE.exists():
        raise FileNotFoundError(
            f"{COST_FILE} missing. Run scripts/treasury_cost.py first."
        )
    with COST_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_realized_profit() -> tuple[float, int, float | None, float | None]:
    """
    Return (realized_profit_usd, trade_count, first_ts, last_ts).

    Realized profit = SUM(pnl) - SUM(fees) - SUM(funding) across all rows
    in trade_log. NULL fees/funding are treated as 0 — for older rows the
    fee was either baked into pnl or not recorded.
    """
    if not TRADE_DB.exists():
        return 0.0, 0, None, None

    # Open read-only to avoid any chance of locking the live trader.
    uri = f"file:{TRADE_DB}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT "
            "  COUNT(*), "
            "  COALESCE(SUM(pnl), 0.0), "
            "  COALESCE(SUM(fees), 0.0), "
            "  COALESCE(SUM(funding), 0.0), "
            "  MIN(timestamp), "
            "  MAX(timestamp) "
            "FROM trade_log"
        )
        count, pnl_sum, fees_sum, funding_sum, first_ts, last_ts = cur.fetchone()
    finally:
        con.close()

    realized = float(pnl_sum) - float(fees_sum) - float(funding_sum)
    return round(realized, 4), int(count), first_ts, last_ts


def classify_status(runway_days: float) -> str:
    if runway_days < 0:
        return "in_debt"
    if runway_days < 7:
        return "red"
    if runway_days < 30:
        return "orange"
    if runway_days < 60:
        return "yellow"
    return "green"


def compute_runway() -> dict:
    cost = load_cost()
    agent_name = cost.get("agent_name", "the bot")
    daily_burn = float(cost["total_usd_per_day"])

    realized, trade_count, first_ts, last_ts = fetch_realized_profit()

    profit_pool = realized  # principal is NOT counted; only gains above it
    if daily_burn > 0:
        runway_days = profit_pool / daily_burn
    else:
        runway_days = float("inf")  # should never happen, but be explicit

    runway_days_rounded = round(runway_days, 2) if runway_days != float("inf") else None
    status = classify_status(runway_days if runway_days != float("inf") else 999999)

    progress_pct = 0.0
    if runway_days > 0:
        progress_pct = min(100.0, round((runway_days / RUNWAY_MILESTONE_DAYS) * 100, 2))

    def _iso(ts: float | None) -> str | None:
        if ts is None:
            return None
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()

    return {
        "agent_name": agent_name,
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "currency": "USD",
        "principal_floor_usd": PRINCIPAL_FLOOR_USD,
        "profit_pool_usd": round(profit_pool, 2),
        "daily_burn_usd": round(daily_burn, 4),
        "runway_days": runway_days_rounded,
        "status": status,
        "milestone_days": RUNWAY_MILESTONE_DAYS,
        "progress_pct": progress_pct,
        "realized_profit": {
            "value_usd": round(realized, 2),
            "trade_count": trade_count,
            "first_trade_at": _iso(first_ts),
            "last_trade_at": _iso(last_ts),
            "source": "sol_sniper.db/trade_log",
        },
        "note": (
            "Only realized trading profit counts as the AI's savings. "
            "The $1,000 principal is seed capital and not part of the profit pool. "
            "Unrealized PnL is ignored — open positions cannot pay the rent."
        ),
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".treasury_runway_", suffix=".json", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def format_runway_label(days: float | None) -> str:
    if days is None:
        return "∞"
    if days < 0:
        return f"{days:+.1f} days (in debt)"
    return f"{days:.1f} days"


def main() -> int:
    payload = compute_runway()
    atomic_write_json(OUTPUT_FILE, payload)

    name = payload["agent_name"]
    days_label = format_runway_label(payload["runway_days"])
    print(
        f"[treasury_runway] {name}: "
        f"profit_pool ${payload['profit_pool_usd']:.2f} · "
        f"burn ${payload['daily_burn_usd']:.4f}/day · "
        f"runway {days_label} · "
        f"status {payload['status']}"
    )
    rp = payload["realized_profit"]
    print(
        f"[treasury_runway] basis: "
        f"{rp['trade_count']} trades, "
        f"realized PnL ${rp['value_usd']:.2f}"
    )
    print(f"[treasury_runway] wrote {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
