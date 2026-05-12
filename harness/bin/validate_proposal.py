#!/usr/bin/env python3
"""Validate a proposal yaml against the 5 contributor-funnel constraints.

Exit codes:
  0 — all 5 constraints pass
  1 — one or more violations
  2 — file/IO error
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.lib.proposal import Proposal


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("proposal_yaml")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of human-readable")
    args = ap.parse_args()

    try:
        p = Proposal.from_yaml(args.proposal_yaml)
    except FileNotFoundError:
        print(f"error: file not found: {args.proposal_yaml}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: failed to parse {args.proposal_yaml}: {e}", file=sys.stderr)
        return 2

    violations = p.validate_all()

    if args.json:
        print(json.dumps({
            "proposal_id": p.data.get("proposal_id"),
            "pass": len(violations) == 0,
            "violations": [
                {"constraint": v.constraint, "memory_rule": v.memory_rule, "detail": v.detail}
                for v in violations
            ],
        }, indent=2))
    else:
        pid = p.data.get("proposal_id", "?")
        if not violations:
            print(f"[pass] {pid}: all 5 constraints satisfied")
        else:
            print(f"[reject] {pid}: {len(violations)} constraint(s) violated")
            for v in violations:
                print(f"  - [{v.constraint}] {v.detail}")
                print(f"    rule: {v.memory_rule}")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
