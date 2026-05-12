#!/usr/bin/env python3
"""Evaluate a proposal against its promotion bar using real shadow jsonl + sol_sniper.db.

Exit codes:
  0 — PROMOTE
  1 — RETIRE or RETIRE_BY_DEADLINE
  2 — KEEP_OBSERVING
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.lib.proposal import Proposal
from harness.lib.promotion_bar import PromotionBar


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("proposal_yaml")
    ap.add_argument("--db", default=None, help="override sol_sniper.db path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        p = Proposal.from_yaml(args.proposal_yaml)
    except FileNotFoundError:
        print(f"error: file not found: {args.proposal_yaml}", file=sys.stderr)
        return 2

    bar = PromotionBar(p, db_path=Path(args.db)) if args.db else PromotionBar(p)
    decision = bar.evaluate()

    if args.json:
        print(json.dumps(decision.to_dict(), indent=2, default=str))
    else:
        print(f"[{decision.decision}] {p.data['proposal_id']}")
        print(f"  receipt: {decision.receipt}")
        print("  metrics:")
        for k, v in decision.metrics.items():
            if isinstance(v, float):
                v = f"{v:.4f}"
            print(f"    {k}: {v}")

    if decision.decision == "PROMOTE":
        return 0
    if decision.decision in ("RETIRE", "RETIRE_BY_DEADLINE"):
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
