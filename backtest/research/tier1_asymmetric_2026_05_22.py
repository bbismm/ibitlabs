"""Tier-1 asymmetric trailing sweep — Bonny ask 2026-05-22 (follow-up).

Original ladder result said: tightening at higher peaks doesn't help because
winner-peak distribution is concentrated in 0.4-0.9%. The interesting question
is the FIRST tier itself: activate=0.4% / trail=X%, where X != 0.5%.

Current LIVE is activate=0.4 / trail=0.5 → 11 of 74 trailing exits land at
negative -0.5 to 0% (peak-just-touched-then-reversed cohort).

Sweep:
  activate=0.004, trail in {0.002, 0.003, 0.004, 0.005}  ← single-dim asymmetric
  Plus: activate=0.003 / trail=0.003  (lower-activation control)
        activate=0.005 / trail=0.003  (higher-activation + tight)

Run:
  python3 ~/ibitlabs/backtest/research/tier1_asymmetric_2026_05_22.py
"""

from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path

REPO = Path("~/ibitlabs").expanduser()
sys.path.insert(0, str(REPO))

from backtest.lib.data import load_ohlcv
from backtest.lib.gates import check as check_gates
from backtest.strategies import sol_v5_3 as strat

PERIOD = "90d"
OOS_DAYS = 30

# Each variant = (label, activate, trail)
VARIANTS = [
    ("LIVE         a=0.4 / t=0.5", 0.004, 0.005),
    ("symm-tight   a=0.4 / t=0.4", 0.004, 0.004),
    ("asymm-A      a=0.4 / t=0.3", 0.004, 0.003),
    ("asymm-B      a=0.4 / t=0.2", 0.004, 0.002),
    ("low-act      a=0.3 / t=0.3", 0.003, 0.003),
    ("high-act     a=0.5 / t=0.3", 0.005, 0.003),
]


def negative_trailing_count(trades):
    n_neg = 0
    for t in trades:
        if t.get("exit_reason") != "trailing":
            continue
        ep, xp = t.get("entry_price"), t.get("exit_price")
        if not ep or not xp:
            continue
        if t.get("direction") == "long":
            pnl_pct = (xp - ep) / ep
        else:
            pnl_pct = (ep - xp) / ep
        if pnl_pct < 0:
            n_neg += 1
    return n_neg


def gate_summary(trades):
    regimes = [t.get("regime", "?") for t in trades]
    r = check_gates(trades, regimes)
    pf_disp = f"{r.pf:.2f}" if r.pf != float("inf") else "inf"
    return {
        "n": r.n_trades,
        "pf_disp": pf_disp,
        "wr": r.wr_pct,
        "regimes": r.distinct_regimes,
        "pnl": sum(t.get("pnl", 0) for t in trades),
        "passed": r.passed,
        "trail_n": sum(1 for t in trades if t.get("exit_reason") == "trailing"),
        "trail_neg": negative_trailing_count(trades),
    }


def fmt_row(label, s):
    flag = "PASS" if s["passed"] else "FAIL"
    return (
        f"  {label:<32} n={s['n']:>3}  PF={s['pf_disp']:>5}  "
        f"WR={s['wr']:>5.1f}%  trail_n={s['trail_n']:>3}  "
        f"trail<0={s['trail_neg']:>2}  PnL=${s['pnl']:+8.2f}  {flag}"
    )


def main():
    print(f"[data] loading SOL {PERIOD} ...")
    bars_15m, bars_1h = load_ohlcv("SOL", PERIOD)
    print(f"[data] {len(bars_15m)} x 15m bars, {len(bars_1h)} x 1h bars")
    last_ts = bars_15m[-1]["ts"]
    is_cutoff_ts = last_ts - OOS_DAYS * 86400

    results = {}
    for label, act, trl in VARIANTS:
        ladder = [(act, trl)]  # single-tier ladder = override of activate+trail pair
        trades = strat.run(bars_15m, bars_1h, trailing_ladder=ladder)
        is_trades = [t for t in trades if t.get("entry_ts", 0) < is_cutoff_ts]
        oos_trades = [t for t in trades if t.get("entry_ts", 0) >= is_cutoff_ts]
        results[label] = {
            "full": gate_summary(trades),
            "is": gate_summary(is_trades),
            "oos": gate_summary(oos_trades),
            "trades": trades,
        }

    print()
    print(f"=== FULL 90d ===")
    for label, _, _ in VARIANTS:
        print(fmt_row(label, results[label]["full"]))
    print()
    print(f"=== IS (60d) ===")
    for label, _, _ in VARIANTS:
        print(fmt_row(label, results[label]["is"]))
    print()
    print(f"=== OOS (30d) ===")
    for label, _, _ in VARIANTS:
        print(fmt_row(label, results[label]["oos"]))

    # Deltas vs LIVE
    print()
    print(f"=== DELTAS vs LIVE (full 90d) ===")
    base = results["LIVE         a=0.4 / t=0.5"]["full"]
    for label, _, _ in VARIANTS:
        if label.startswith("LIVE"):
            continue
        f = results[label]["full"]
        d_pnl = f["pnl"] - base["pnl"]
        d_neg = f["trail_neg"] - base["trail_neg"]
        try:
            d_pf = float(f["pf_disp"]) - float(base["pf_disp"])
            pf_str = f"{d_pf:+.2f}"
        except ValueError:
            pf_str = "n/a"
        print(
            f"  {label:<32} dPnL=${d_pnl:+7.2f}  dPF={pf_str}  "
            f"d_trail<0={d_neg:+d}"
        )

    # IS/OOS coherence — does the winner win in both?
    print()
    print(f"=== IS+OOS coherence (PnL delta vs LIVE, $) ===")
    base_is = results["LIVE         a=0.4 / t=0.5"]["is"]["pnl"]
    base_oos = results["LIVE         a=0.4 / t=0.5"]["oos"]["pnl"]
    for label, _, _ in VARIANTS:
        if label.startswith("LIVE"):
            continue
        d_is = results[label]["is"]["pnl"] - base_is
        d_oos = results[label]["oos"]["pnl"] - base_oos
        coherent = "✓" if (d_is > 0) == (d_oos > 0) else "✗"
        print(
            f"  {label:<32} IS dPnL={d_is:+7.2f}  OOS dPnL={d_oos:+7.2f}  "
            f"both-positive: {coherent}"
        )


if __name__ == "__main__":
    main()
