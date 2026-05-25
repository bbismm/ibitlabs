"""vol_ratio (volume_mult) engine sweep — Bonny ask 2026-05-24.

Cross-validates the LIVE-replay finding (n=21, vol_ratio≥1.5 ships 5-24 21:35 EDT)
against a full 90d engine backtest with a bigger sample.

LIVE-replay (n=21) said both 1.20 and 1.55 are better than 1.50; differences
came from single-trade swings. This sweep runs the same SOL v5.3 engine end-to-end
under varied `volume_mult` to see whether the curve holds at scale.

Companion: vol_ratio_threshold_2026_05_24.py (LIVE replay).

Run:
  python3 ~/ibitlabs/backtest/research/vol_ratio_engine_sweep_2026_05_24.py
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
OOS_DAYS = 30

VARIANTS = [
    ("vm=1.00 (engine default)", 1.00),
    ("vm=1.10                 ", 1.10),
    ("vm=1.20                 ", 1.20),
    ("vm=1.30                 ", 1.30),
    ("vm=1.40                 ", 1.40),
    ("vm=1.50 (LIVE 5-24)     ", 1.50),
    ("vm=1.55 (SL-sig)        ", 1.55),
    ("vm=1.70                 ", 1.70),
    ("vm=2.00                 ", 2.00),
]


def gate_summary(trades):
    regimes = [t.get("regime", "?") for t in trades]
    r = check_gates(trades, regimes)
    pf_disp = f"{r.pf:.2f}" if r.pf != float("inf") else "inf"
    return {
        "n": r.n_trades,
        "pf": r.pf,
        "pf_disp": pf_disp,
        "wr": r.wr_pct,
        "regimes": r.distinct_regimes,
        "pnl": sum(t.get("pnl", 0) for t in trades),
        "passed": r.passed,
    }


def fmt_row(label, s):
    flag = "PASS" if s["passed"] else "FAIL"
    return (
        f"  {label:<28}  n={s['n']:>3}  PF={s['pf_disp']:>5}  "
        f"WR={s['wr']:>5.1f}%  regimes={s['regimes']}  "
        f"PnL=${s['pnl']:+8.2f}  {flag}"
    )


def main():
    print(f"[data] loading SOL {PERIOD} ...")
    bars_15m, bars_1h = load_ohlcv("SOL", PERIOD)
    print(f"[data] {len(bars_15m)} x 15m bars, {len(bars_1h)} x 1h bars")
    last_ts = bars_15m[-1]["ts"]
    is_cutoff_ts = last_ts - OOS_DAYS * 86400

    results = {}
    for label, vm in VARIANTS:
        trades = strat.run(bars_15m, bars_1h, volume_mult=vm)
        is_trades = [t for t in trades if t.get("entry_ts", 0) < is_cutoff_ts]
        oos_trades = [t for t in trades if t.get("entry_ts", 0) >= is_cutoff_ts]
        results[label] = {
            "full": gate_summary(trades),
            "is": gate_summary(is_trades),
            "oos": gate_summary(oos_trades),
        }
        print(f"  [{label.strip()}] full n={len(trades):>3} IS={len(is_trades):>3} OOS={len(oos_trades):>3}")

    print()
    print(f"=== FULL 90d ===")
    for label, _ in VARIANTS:
        print(fmt_row(label, results[label]["full"]))

    print()
    print(f"=== IS (60d) ===")
    for label, _ in VARIANTS:
        print(fmt_row(label, results[label]["is"]))

    print()
    print(f"=== OOS (30d) ===")
    for label, _ in VARIANTS:
        print(fmt_row(label, results[label]["oos"]))

    print()
    print(f"=== DELTAS vs vm=1.00 (full 90d) ===")
    base = results["vm=1.00 (engine default)"]["full"]
    for label, _ in VARIANTS:
        if label.startswith("vm=1.00"):
            continue
        f = results[label]["full"]
        d_pnl = f["pnl"] - base["pnl"]
        d_n = f["n"] - base["n"]
        d_pf = f["pf"] - base["pf"] if base["pf"] != float("inf") and f["pf"] != float("inf") else None
        pf_str = f"{d_pf:+.2f}" if d_pf is not None else "n/a"
        print(
            f"  {label:<28}  dPnL=${d_pnl:+8.2f}  dN={d_n:+4d}  dPF={pf_str}  "
            f"dWR={f['wr'] - base['wr']:+5.1f}pp"
        )

    print()
    print(f"=== IS+OOS coherence (PnL delta vs vm=1.00, $) ===")
    base_is = results["vm=1.00 (engine default)"]["is"]["pnl"]
    base_oos = results["vm=1.00 (engine default)"]["oos"]["pnl"]
    for label, _ in VARIANTS:
        if label.startswith("vm=1.00"):
            continue
        d_is = results[label]["is"]["pnl"] - base_is
        d_oos = results[label]["oos"]["pnl"] - base_oos
        coherent = "✓" if (d_is > 0) == (d_oos > 0) else "✗"
        print(
            f"  {label:<28}  IS dPnL=${d_is:+8.2f}  OOS dPnL=${d_oos:+8.2f}  "
            f"both-positive: {coherent}"
        )

    print()
    print(f"=== Verdict (full 90d, PnL ranked) ===")
    ranked = sorted(VARIANTS, key=lambda x: -results[x[0]]["full"]["pnl"])
    for i, (label, vm) in enumerate(ranked, 1):
        f = results[label]["full"]
        mark = ""
        if vm == 1.50:
            mark = "  ← LIVE 5-24"
        elif vm == 1.00:
            mark = "  ← engine default"
        print(f"  #{i}  {label:<28}  PnL=${f['pnl']:+8.2f}  n={f['n']:>3}  PF={f['pf_disp']:>5}  WR={f['wr']:>5.1f}%{mark}")


if __name__ == "__main__":
    main()
