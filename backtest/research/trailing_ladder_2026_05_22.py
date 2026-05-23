"""Tiered trailing-stop research — Bonny ask 2026-05-22.

Compares LIVE single-tier baseline vs 2-tier vs 4-tier ladders on 90d SOL,
with 60d IS / 30d OOS split. Reuses sol_v5_3 wrapper + harness gates.

Run:
  python3 ~/ibitlabs/backtest/research/trailing_ladder_2026_05_22.py
"""

from __future__ import annotations
import sys
from pathlib import Path

REPO = Path("~/ibitlabs").expanduser()
sys.path.insert(0, str(REPO))

from backtest.lib.data import load_ohlcv
from backtest.lib.gates import check as check_gates
from backtest.strategies import sol_v5_3 as strat

PERIOD = "90d"
OOS_DAYS = 30  # IS = 60d, OOS = 30d

VARIANTS = {
    "baseline (single 0.4/0.5)": None,  # leaves trailing_activate=0.004, trailing_stop=0.005
    "2-tier (0.4/0.5, 1.4/0.3)": [(0.004, 0.005), (0.014, 0.003)],
    "4-tier (0.4/0.5, 0.9/0.4, 1.4/0.3, 1.9/0.2)": [
        (0.004, 0.005), (0.009, 0.004), (0.014, 0.003), (0.019, 0.002),
    ],
}


def gate_summary(trades):
    regimes = [t.get("regime", "?") for t in trades]
    r = check_gates(trades, regimes)
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    pf_disp = f"{r.pf:.2f}" if r.pf != float("inf") else "inf"
    trail_n = sum(1 for t in trades if t.get("exit_reason") == "trailing")
    return {
        "n": r.n_trades,
        "pf_disp": pf_disp,
        "wr": r.wr_pct,
        "regimes": r.distinct_regimes,
        "pnl": total_pnl,
        "passed": r.passed,
        "reasons": r.reasons,
        "trail_n": trail_n,
    }


def fmt_row(label, s):
    flag = "PASS" if s["passed"] else "FAIL"
    return (
        f"  {label:<48} n={s['n']:>3}  PF={s['pf_disp']:>5}  "
        f"WR={s['wr']:>5.1f}%  reg={s['regimes']}  "
        f"trail_n={s['trail_n']:>3}  PnL=${s['pnl']:+8.2f}  {flag}"
    )


def main():
    print(f"[data] loading SOL {PERIOD} ...")
    bars_15m, bars_1h = load_ohlcv("SOL", PERIOD)
    print(f"[data] {len(bars_15m)} x 15m bars, {len(bars_1h)} x 1h bars")
    last_ts = bars_15m[-1]["ts"]
    is_cutoff_ts = last_ts - OOS_DAYS * 86400

    results = {}
    for label, ladder in VARIANTS.items():
        if ladder is None:
            trades = strat.run(bars_15m, bars_1h)
        else:
            trades = strat.run(bars_15m, bars_1h, trailing_ladder=ladder)
        is_trades = [t for t in trades if t.get("entry_ts", 0) < is_cutoff_ts]
        oos_trades = [t for t in trades if t.get("entry_ts", 0) >= is_cutoff_ts]
        results[label] = {
            "full": gate_summary(trades),
            "is": gate_summary(is_trades),
            "oos": gate_summary(oos_trades),
        }

    print()
    print(f"=== FULL 90d ===")
    for label, r in results.items():
        print(fmt_row(label, r["full"]))
    print()
    print(f"=== IS (60d) — anti-overfit IS+OOS must both pass at threshold ===")
    for label, r in results.items():
        print(fmt_row(label, r["is"]))
    print()
    print(f"=== OOS (30d) ===")
    for label, r in results.items():
        print(fmt_row(label, r["oos"]))
    print()
    print(f"=== DELTAS vs baseline (full 90d) ===")
    base = results["baseline (single 0.4/0.5)"]["full"]
    for label, r in results.items():
        if label.startswith("baseline"):
            continue
        f = r["full"]
        d_pnl = f["pnl"] - base["pnl"]
        d_n_trail = f["trail_n"] - base["trail_n"]
        try:
            d_pf = float(f["pf_disp"]) - float(base["pf_disp"])
            pf_str = f"{d_pf:+.2f}"
        except ValueError:
            pf_str = "n/a"
        d_wr = f["wr"] - base["wr"]
        print(
            f"  {label:<48} dPnL=${d_pnl:+7.2f}  dPF={pf_str}  "
            f"dWR={d_wr:+.1f}pp  d_trail_n={d_n_trail:+d}"
        )


if __name__ == "__main__":
    main()
