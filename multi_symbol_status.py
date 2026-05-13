"""multi_symbol_status.py — Phase 4 prerequisite 2d.

When ETH bot goes live, /api/live-status grows a `multi_symbol` block so the
/signals dashboard (and downstream consumers) can present SOL-only vs combined
vs ETH-contribution numbers honestly. SOL-only IS the phantom counterfactual
by construction — SOL bot keeps trading regardless of ETH's existence, so its
real equity curve from the launch moment forward is the answer to "what would
have happened with SOL-only?"

Two on-disk inputs:
  - state/multi_symbol_launch_anchor.json — written once at the moment the ETH
    plist flips from paper→live. Declares paths to ETH state + DB and freezes
    SOL's balance at launch instant. Read-only thereafter.
  - The ETH bot's own state file + DB (paths declared by the anchor).

This module never raises — a malformed anchor or unreachable ETH state must
not break the SOL-side /api/live-status endpoint. Worst case: returns
{"launched": false} or omits ETH-derived fields. The SOL view remains intact.
"""

import json
import os
import sqlite3
import time
from typing import Optional

ANCHOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "state", "multi_symbol_launch_anchor.json")

# ETH state file mtime within this window from now ⇒ bot considered alive.
# Matches SOL bot's scan_interval × ~4 to tolerate idle ticks without flapping.
ETH_ALIVE_THRESHOLD_SEC = 120


def _read_anchor() -> Optional[dict]:
    if not os.path.exists(ANCHOR_PATH):
        return None
    try:
        with open(ANCHOR_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def _read_eth_state(state_path: str) -> Optional[dict]:
    if not state_path or not os.path.exists(state_path):
        return None
    try:
        with open(state_path) as f:
            data = json.load(f)
        data["_mtime"] = os.path.getmtime(state_path)
        return data
    except Exception:
        return None


def _read_eth_trade_summary(db_path: str) -> dict:
    """Closed-trade count + PnL sum from ETH bot's trade_log."""
    summary = {"closed_trades": 0, "total_pnl": 0.0}
    if not db_path or not os.path.exists(db_path):
        return summary
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        try:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(pnl), 0) FROM trade_log "
                "WHERE exit_price IS NOT NULL"
            ).fetchone()
            summary["closed_trades"] = int(row[0])
            summary["total_pnl"] = round(float(row[1]), 2)
        finally:
            conn.close()
    except Exception:
        pass
    return summary


def build_multi_symbol_block(sol_balance: float, sol_total_pnl: float) -> dict:
    """Return the `multi_symbol` JSON block. Pre-launch: {"launched": false}.

    Caller passes SOL's current balance + total_pnl (already computed for the
    top-level fields). This module reads anchor + ETH side state independently.
    """
    anchor = _read_anchor()
    if not anchor:
        return {"launched": False}

    eth_state = _read_eth_state(anchor.get("eth_state_file", ""))
    eth_summary = _read_eth_trade_summary(anchor.get("eth_db_file", ""))
    eth_starting_capital = float(anchor.get("eth_starting_capital", 1000.0))
    sol_starting_capital = float(anchor.get("sol_starting_capital", 1000.0))

    eth_balance = None
    eth_alive = False
    eth_position_active = False
    if eth_state:
        cash = float(eth_state.get("cash", 0))
        pos = eth_state.get("position") or {}
        margin = float(pos.get("margin", 0)) if pos else 0.0
        eth_balance = round(cash + margin, 2)
        eth_alive = (time.time() - eth_state.get("_mtime", 0)) < ETH_ALIVE_THRESHOLD_SEC
        eth_position_active = bool(pos)

    combined_balance = (
        round(sol_balance + eth_balance, 2) if eth_balance is not None else None
    )
    combined_starting_capital = round(sol_starting_capital + eth_starting_capital, 2)

    return {
        "launched": True,
        "launched_at": anchor.get("launched_at"),
        "launched_at_ts": anchor.get("launched_at_ts"),
        "eth_mode": anchor.get("eth_mode", "live"),
        "sol_balance": round(sol_balance, 2),
        "sol_starting_capital": sol_starting_capital,
        "sol_total_pnl": round(sol_total_pnl, 2),
        "eth_balance": eth_balance,
        "eth_starting_capital": eth_starting_capital,
        "eth_total_pnl": eth_summary["total_pnl"],
        "eth_closed_trades": eth_summary["closed_trades"],
        "eth_position_active": eth_position_active,
        "eth_alive": eth_alive,
        "combined_balance": combined_balance,
        "combined_starting_capital": combined_starting_capital,
        "anchor": {
            "sol_balance_at_launch": anchor.get("sol_balance_at_launch"),
            "sol_total_pnl_at_launch": anchor.get("sol_total_pnl_at_launch"),
            "eth_balance_at_launch": anchor.get("eth_balance_at_launch"),
        },
    }
