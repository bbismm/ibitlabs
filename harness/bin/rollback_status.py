#!/usr/bin/env python3
"""List all rollback monitors across the 3 layers (realtime / observation / proposal).

Exit codes:
  0 — all healthy
  1 — at least one alarm
  2 — at least one degraded or unknown (no alarm)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.lib.rollback import RollbackLadder


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--layer",
        choices=["realtime", "observation", "proposal", "all"],
        default="all",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ladder = RollbackLadder()
    if args.layer == "all":
        monitors = ladder.list_all()
    elif args.layer == "realtime":
        monitors = ladder.realtime.list_monitors()
    elif args.layer == "observation":
        monitors = ladder.observation.list_monitors()
    else:
        monitors = ladder.proposal.list_monitors()

    if args.json:
        print(json.dumps([m.to_dict() for m in monitors], indent=2))
    else:
        by_layer: dict[str, list] = {"realtime": [], "observation": [], "proposal": []}
        for m in monitors:
            by_layer[m.layer].append(m)
        badge_map = {"healthy": "OK   ", "degraded": "WARN ", "alarm": "ALARM", "unknown": "?    "}
        for layer in ("realtime", "observation", "proposal"):
            ms = by_layer[layer]
            if not ms:
                continue
            print(f"== {layer.upper()} ==")
            for m in ms:
                print(f"  [{badge_map[m.status]}] {m.id}")
                print(f"          {m.description}")
                if m.detail:
                    print(f"          {m.detail}")
            print()

    if any(m.status == "alarm" for m in monitors):
        return 1
    if any(m.status in ("degraded", "unknown") for m in monitors):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
