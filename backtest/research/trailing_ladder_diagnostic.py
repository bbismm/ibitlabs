"""Diagnostic — what does the winner-peak distribution actually look like?

If ladder tier 0.9 / 1.4 / 1.9 % rarely gets crossed, the ladder change is
mechanically incapable of helping. Run alongside trailing_ladder_2026_05_22.py.
"""

from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path

REPO = Path("~/ibitlabs").expanduser()
sys.path.insert(0, str(REPO))

from backtest.lib.data import load_ohlcv
from backtest.strategies import sol_v5_3 as strat


def main():
    print("[data] loading SOL 90d ...")
    bars_15m, bars_1h = load_ohlcv("SOL", "90d")

    # Baseline run (no ladder)
    trades = strat.run(bars_15m, bars_1h)
    print(f"[trades] n={len(trades)}")

    # exit_reason breakdown
    reasons = Counter(t.get("exit_reason") for t in trades)
    print(f"[exit_reason] {dict(reasons)}")

    # PnL by exit reason
    print()
    print(f"=== PnL by exit_reason ===")
    for reason in ("tp", "sl", "trailing", "timeout", "end"):
        rs = [t for t in trades if t.get("exit_reason") == reason]
        if not rs:
            continue
        pnl = sum(t.get("pnl", 0) for t in rs)
        pnl_pcts = []
        for t in rs:
            ep, xp = t.get("entry_price"), t.get("exit_price")
            if ep and xp:
                if t.get("direction") == "long":
                    pnl_pcts.append((xp - ep) / ep * 100)
                else:
                    pnl_pcts.append((ep - xp) / ep * 100)
        avg_pct = sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else 0
        print(
            f"  {reason:<10} n={len(rs):>3}  PnL=${pnl:+8.2f}  "
            f"avg_pct={avg_pct:+.2f}%  per_trade=${pnl/len(rs):+.2f}"
        )

    # Trailing-exit price distribution: what % did they exit at?
    print()
    print(f"=== Trailing-exit price % distribution (favorable side from entry) ===")
    trail_trades = [t for t in trades if t.get("exit_reason") == "trailing"]
    pct_bands = Counter()
    pcts_sorted = []
    for t in trail_trades:
        ep, xp = t.get("entry_price"), t.get("exit_price")
        if not ep or not xp:
            continue
        if t.get("direction") == "long":
            pct = (xp - ep) / ep * 100
        else:
            pct = (ep - xp) / ep * 100
        pcts_sorted.append(pct)
        # Bands by exit favorable %
        if pct < -0.5:
            pct_bands["a: exit < -0.5%"] += 1
        elif pct < 0:
            pct_bands["b: -0.5 to 0%"] += 1
        elif pct < 0.5:
            pct_bands["c: 0 to 0.5%"] += 1
        elif pct < 1.0:
            pct_bands["d: 0.5 to 1.0%"] += 1
        elif pct < 1.5:
            pct_bands["e: 1.0 to 1.5%"] += 1
        elif pct < 2.0:
            pct_bands["f: 1.5 to 2.0%"] += 1
        else:
            pct_bands["g: >= 2.0%"] += 1
    for band in sorted(pct_bands.keys()):
        print(f"  {band:<22} n={pct_bands[band]:>3}")

    # An exit at exit_pct = X means peak was X + cfg.trailing_stop = X + 0.5%
    # So peak distribution = exit_pct + 0.5
    print()
    print(f"=== Implied peak distribution (= exit_pct + 0.5%) ===")
    peaks = [p + 0.5 for p in pcts_sorted]
    peak_bands = Counter()
    for pk in peaks:
        if pk < 0.4:
            peak_bands["t0: peak < 0.4% (no trailing should fire)"] += 1
        elif pk < 0.9:
            peak_bands["t1: 0.4 to 0.9%"] += 1
        elif pk < 1.4:
            peak_bands["t2: 0.9 to 1.4%"] += 1
        elif pk < 1.9:
            peak_bands["t3: 1.4 to 1.9%"] += 1
        else:
            peak_bands["t4: >= 1.9%"] += 1
    for band in sorted(peak_bands.keys()):
        n = peak_bands[band]
        pct_of_total = 100 * n / len(peaks) if peaks else 0
        print(f"  {band:<48} n={n:>3} ({pct_of_total:.1f}%)")

    # The key question: how many trailing exits would have been affected by
    # tier2 (1.4%) and tier3 (1.9%)? i.e. how many peaks crossed those?
    n_tier2 = sum(1 for p in peaks if p >= 1.4)
    n_tier3 = sum(1 for p in peaks if p >= 1.9)
    print()
    print(f"[ladder reach] trailing-exit trades whose peak crossed:")
    print(f"  1.4% (tier 2-tier ladder hits): {n_tier2}/{len(peaks)} ({100*n_tier2/max(1,len(peaks)):.1f}%)")
    print(f"  1.9% (tier 4-tier ladder top):  {n_tier3}/{len(peaks)} ({100*n_tier3/max(1,len(peaks)):.1f}%)")


if __name__ == "__main__":
    main()
