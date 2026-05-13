#!/usr/bin/env python3
"""
Gate 3: Production-environment delta — slippage drag estimate.

Prep doc lines 87-88: shadow runs --paper (zero slippage / fee / rejection).
Tighter trailing (0.5%) is especially vulnerable to slippage erosion live.
This script projects shadow PnL with a slippage model applied per fill,
and compares the eroded edge to the trailing-stop budget.

Decision rule (operator-facing):
  slippage 2-side / trailing_stop_pct < 15% → swap is acceptable
  ratio 15-30%  → caution; consider relaxing trailing to 0.6%/0.7%
  ratio > 30%   → DEFER; slippage dominates the trailing edge
"""
import sqlite3
import statistics
import json
import os
import time

LIVE_DB = "/Users/bonnyagent/ibitlabs/sol_sniper.db"
SHADOW_DB = "/Users/bonnyagent/ibitlabs/sol_sniper_shadow.db"
OUT_DIR = "/Users/bonnyagent/ibitlabs/logs/4gate_2026-06-05"
os.makedirs(OUT_DIR, exist_ok=True)

TRAILING_STOP_PCT_SHADOW = 0.005  # 0.5% — current shadow value
ASSUMED_FEE_PCT = 0.0004           # Coinbase futures fee ~4bps per side


def measure_live_slippage():
    """Estimate live entry/exit slippage from sol_sniper.db.

    PROXY: trade_log carries entry_price (the actual fill) but not the
    intended/signal price. As a workable proxy for prep, take the absolute
    diff between consecutive 1-min ticks at order time as a slippage
    upper bound.

    For 06-05 review, REPLACE this proxy with a real audit:
      - join trade_log to entry_confidence_map.jsonl by order_id
      - compare market_state.last_price vs trade_log.entry_price
    """
    # PLACEHOLDER until 06-05 audit produces the real number.
    # 8bps is a reasonable starting estimate for SOL-USD-PERPETUAL on Coinbase.
    return 0.0008


def gate3():
    slip_pct = measure_live_slippage()

    conn = sqlite3.connect(f"file:{SHADOW_DB}?mode=ro", uri=True)
    rows = conn.execute("""
        SELECT pnl, entry_price, exit_price, direction, exit_reason,
               strategy_version
        FROM trade_log
        WHERE exit_reason IS NOT NULL AND pnl IS NOT NULL
          AND strategy_version IN ('hybrid_v5.1', 'v5.1', 'sniper_v5.1')
    """).fetchall()
    conn.close()

    valid = [r for r in rows if r[1] and r[2] and r[3]]
    eroded_pcts = []
    for pnl, entry, exit_, direction, exit_reason, _ in valid:
        slip = slip_pct * entry
        fee = ASSUMED_FEE_PCT * 2 * entry  # fee both sides
        if direction == "long":
            eff_entry = entry + slip
            eff_exit = exit_ - slip
            eroded = (eff_exit - eff_entry - fee) / eff_entry
        else:
            eff_entry = entry - slip
            eff_exit = exit_ + slip
            eroded = (eff_entry - eff_exit - fee) / eff_entry
        eroded_pcts.append(eroded)

    orig_pcts = [(t[2] - t[1]) / t[1] if t[3] == "long" else (t[1] - t[2]) / t[1]
                 for t in valid]

    n = len(eroded_pcts)
    if n == 0:
        print("Gate 3: no shadow trades available. Re-check schema and shadow DB freshness.")
        return None

    orig_med = statistics.median(orig_pcts)
    eroded_med = statistics.median(eroded_pcts)
    orig_sum = sum(orig_pcts)
    eroded_sum = sum(eroded_pcts)
    drag_per_trade = orig_med - eroded_med
    ratio = (slip_pct * 2) / TRAILING_STOP_PCT_SHADOW

    print(f"Gate 3: slippage drag estimate")
    print(f"  Trades analyzed:           {n}")
    print(f"  Slippage per side:         {slip_pct*100:.3f}%")
    print(f"  Fee per side:              {ASSUMED_FEE_PCT*100:.3f}%")
    print()
    print(f"  Original median PnL%:      {orig_med*100:+.3f}%")
    print(f"  Eroded median PnL%:        {eroded_med*100:+.3f}%")
    print(f"  Drag per trade (median):   {drag_per_trade*100:+.3f}%")
    print(f"  Original cumulative PnL%:  {orig_sum*100:+.2f}%")
    print(f"  Eroded cumulative PnL%:    {eroded_sum*100:+.2f}%")
    print()
    print(f"  Trailing stop budget:      {TRAILING_STOP_PCT_SHADOW*100:.1f}%")
    print(f"  2-side slippage:           {slip_pct*2*100:.2f}%")
    print(f"  ratio (slip / stop):       {ratio*100:.0f}%")
    print()
    if ratio < 0.15:
        verdict = "PASS — slippage is small vs trailing budget; swap acceptable"
    elif ratio < 0.30:
        verdict = "CAUTION — consider relaxing trailing to 0.6%/0.7% before swap"
    else:
        verdict = "FAIL — slippage dominates trailing edge; DEFER"
    print(f"GATE 3 VERDICT: {verdict}")

    return {
        "ts": time.time(),
        "n_trades": n,
        "slip_pct_per_side": slip_pct,
        "orig_median_pct": orig_med,
        "eroded_median_pct": eroded_med,
        "drag_per_trade_pct": drag_per_trade,
        "orig_cumulative_pct": orig_sum,
        "eroded_cumulative_pct": eroded_sum,
        "ratio_slip_to_stop": ratio,
        "verdict": verdict,
    }


if __name__ == "__main__":
    result = gate3()
    if result:
        out_path = os.path.join(OUT_DIR, "gate3.out")
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nRaw output: {out_path}")
