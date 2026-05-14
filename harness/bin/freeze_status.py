#!/usr/bin/env python3
"""Report harness schema-freeze status from governance/reviews.yaml.

Operator-level governance (see docs/why.md §Operator Rule O1):
  When >=2 scheduled reviews close within 7 days of each other (cluster),
  the harness schema/CLI/lib freeze for [first_close-7d, last_close+14d].
  Mutations to schemas/, bin/, lib/ during the freeze should be parked as
  hypotheses-with-trigger and re-submitted post-freeze.

Exit codes:
  0 - currently UNFROZEN
  1 - currently FROZEN
  2 - file/IO/parse error
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.lib.freeze import (
    DEFAULT_REVIEWS_PATH,
    current_status,
    load_reviews,
    window_to_dict,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument(
        "--reviews",
        default=str(DEFAULT_REVIEWS_PATH),
        help="path to reviews YAML (default: harness/governance/reviews.yaml)",
    )
    ap.add_argument(
        "--now",
        default=None,
        help="ISO date override (e.g. 2026-05-31) for what-if checks",
    )
    ap.add_argument("--json", action="store_true", help="emit JSON instead of human-readable")
    args = ap.parse_args()

    try:
        reviews = load_reviews(args.reviews)
    except FileNotFoundError:
        print(f"error: reviews file not found: {args.reviews}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: failed to parse {args.reviews}: {e}", file=sys.stderr)
        return 2

    now = date.fromisoformat(args.now) if args.now else date.today()
    status = current_status(now, reviews)

    if args.json:
        out: dict = {
            "as_of": now.isoformat(),
            "frozen": status.frozen,
        }
        if status.active_window is not None:
            out["active_window"] = window_to_dict(status.active_window)
            out["days_until_unfreeze"] = status.days_until_unfreeze
        if status.next_window is not None:
            out["next_window"] = window_to_dict(status.next_window)
            out["days_until_freeze"] = status.days_until_freeze
        print(json.dumps(out, indent=2))
    else:
        if status.frozen:
            w = status.active_window
            assert w is not None
            cluster_str = ", ".join(f"{r.name} {r.closes_at.isoformat()}" for r in w.reviews)
            print(f"[FROZEN] as of {now.isoformat()}")
            print(
                f"  window: {w.start.isoformat()} -> {w.end.isoformat()} "
                f"({status.days_until_unfreeze}d remaining)"
            )
            print(f"  cluster ({len(w.reviews)} reviews): {cluster_str}")
            print("  rule: schema/CLI/lib changes must be parked and re-submitted post-freeze")
            print("  see: docs/why.md Operator Rule O1")
        else:
            print(f"[UNFROZEN] as of {now.isoformat()}")
            if status.next_window is not None:
                w = status.next_window
                cluster_str = ", ".join(f"{r.name} {r.closes_at.isoformat()}" for r in w.reviews)
                print(f"  next freeze: {w.start.isoformat()} ({status.days_until_freeze}d away)")
                print(f"  upcoming cluster ({len(w.reviews)} reviews): {cluster_str}")
            else:
                print("  no upcoming review clusters scheduled")

    return 1 if status.frozen else 0


if __name__ == "__main__":
    sys.exit(main())
