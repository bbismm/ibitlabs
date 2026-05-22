"""Anti-overfit gate evaluation. Defaults are not optional — built from $1k-bot lived lessons."""

from __future__ import annotations
from dataclasses import dataclass


DEFAULTS = {
    "min_trades": 30,
    "min_pf": 1.2,
    "min_wr_pct": 60.0,
    "min_distinct_regimes": 2,
}


@dataclass(frozen=True)
class GateResult:
    passed: bool
    n_trades: int
    pf: float
    wr_pct: float
    distinct_regimes: int
    reasons: list[str]


def check(trades: list[dict], regimes: list[str], thresholds: dict | None = None) -> GateResult:
    """Evaluate gates. v5.2 lesson: PF<1.0 live is noise, not architecture switch."""
    th = {**DEFAULTS, **(thresholds or {})}
    n = len(trades)
    wins_pnl = sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0)
    losses_pnl = abs(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0))
    if losses_pnl > 0:
        pf = wins_pnl / losses_pnl
    elif n > 0:
        pf = float("inf")
    else:
        pf = 0.0
    wins_count = sum(1 for t in trades if t.get("pnl", 0) > 0)
    wr = 100 * wins_count / n if n else 0.0
    distinct = len(set(regimes))

    reasons: list[str] = []
    if n < th["min_trades"]:
        reasons.append(f"n_trades={n} < min={th['min_trades']}")
    if pf < th["min_pf"]:
        reasons.append(f"PF={pf:.2f} < min={th['min_pf']:.2f}")
    if wr < th["min_wr_pct"]:
        reasons.append(f"WR={wr:.1f}% < min={th['min_wr_pct']:.1f}%")
    if distinct < th["min_distinct_regimes"]:
        reasons.append(f"distinct_regimes={distinct} < min={th['min_distinct_regimes']}")

    return GateResult(
        passed=len(reasons) == 0,
        n_trades=n,
        pf=pf,
        wr_pct=wr,
        distinct_regimes=distinct,
        reasons=reasons,
    )
