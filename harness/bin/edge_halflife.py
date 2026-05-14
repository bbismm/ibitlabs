#!/usr/bin/env python3
"""Edge half-life monitor.

Rolls up 30 / 60 / 90 day hit_rate + profit_factor for:
  1. The baseline bot (sol_sniper.db trade_log filtered by strategy_version + instance)
  2. Each proposal yaml under harness/examples/ (per-rule shadow signal)

Output is observation-only -- no archive, no control-flow change. Use
`rollback_status.py` for the unified rollup; this CLI is for drilling into a
specific target or surfacing the raw numbers.

Exit codes:
  0 -- all healthy or insufficient_data
  1 -- at least one decayed
  2 -- at least one degrading
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.lib.edge_halflife import EdgeHalflifeMonitor, EdgeStatus
from harness.lib.proposal import Proposal


EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

BADGE = {
    "healthy": "OK   ",
    "degrading": "WARN ",
    "decayed": "ALARM",
    "insufficient_data": "...  ",
}


def _fmt_pf(pf):
    if pf is None:
        return "n/a"
    if pf == float("inf"):
        return "inf"
    return f"{pf:.2f}"


def _fmt_hr(hr):
    return "n/a" if hr is None else f"{hr:.1%}"


def _print_status(es: EdgeStatus) -> None:
    print(f"[{BADGE[es.status]}] {es.target_id}  ({es.mode})")
    for w in es.windows:
        print(
            f"   {w.window_days:>3}d: n={w.n_paired:>3}  "
            f"HR={_fmt_hr(w.hit_rate):>6}  "
            f"PF={_fmt_pf(w.profit_factor):>5}  "
            f"PnL=${w.pnl_total:+.2f}"
        )
    if es.last_close_at:
        print(f"   last close: {es.last_close_at}")
    print(f"   -> {es.receipt}")
    print()


def collect(
    *,
    baseline_only: bool = False,
    rule_id: str | None = None,
    strategy_version: str = "hybrid_v5.1",
    instance_name: str = "live",
) -> list[EdgeStatus]:
    monitor = EdgeHalflifeMonitor()
    out: list[EdgeStatus] = []

    if rule_id is None:
        out.append(monitor.baseline(
            strategy_version=strategy_version,
            instance_name=instance_name,
        ))
        if baseline_only:
            return out

    for yaml_file in sorted(EXAMPLES_DIR.glob("*.yaml")):
        with yaml_file.open() as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict) or "proposal_id" not in raw:
            continue
        if rule_id and raw["proposal_id"] != rule_id:
            continue
        try:
            p = Proposal.from_yaml(yaml_file)
            out.append(monitor.for_proposal(p))
        except Exception as e:  # noqa: BLE001
            out.append(EdgeStatus(
                target_id=yaml_file.stem,
                mode="rule",
                status="insufficient_data",
                receipt=f"load error: {e}",
            ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline-only", action="store_true",
                    help="Skip per-rule yamls; just show baseline.")
    ap.add_argument("--rule", default=None,
                    help="Restrict to one proposal_id (skips baseline).")
    ap.add_argument("--strategy-version", default="hybrid_v5.1")
    ap.add_argument("--instance-name", default="live")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    statuses = collect(
        baseline_only=args.baseline_only,
        rule_id=args.rule,
        strategy_version=args.strategy_version,
        instance_name=args.instance_name,
    )

    if args.json:
        print(json.dumps([s.to_dict() for s in statuses], indent=2, default=str))
    else:
        for s in statuses:
            _print_status(s)

    if any(s.status == "decayed" for s in statuses):
        return 1
    if any(s.status == "degrading" for s in statuses):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
