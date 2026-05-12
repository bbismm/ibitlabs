#!/usr/bin/env python3
"""Archive a falsified rule into memory as feedback_*.md.

Default is dry-run (prints what would be written). Use --write to commit. If the
target memory file already exists, refuses to overwrite without --force.

Exit codes:
  0 — success (or dry-run preview)
  1 — schema validation failed
  2 — file/IO error
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from harness.lib.anti_pattern import AntiPattern


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("anti_pattern_yaml")
    ap.add_argument("--write", action="store_true", help="actually write memory file")
    ap.add_argument("--force", action="store_true", help="overwrite existing memory file")
    ap.add_argument("--show", action="store_true", help="print the rendered memory body")
    args = ap.parse_args()

    try:
        archive = AntiPattern.from_yaml(args.anti_pattern_yaml)
    except FileNotFoundError:
        print(f"error: file not found: {args.anti_pattern_yaml}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: failed to parse {args.anti_pattern_yaml}: {e}", file=sys.stderr)
        return 2

    try:
        archive.validate_schema()
    except Exception as e:
        print(f"[reject] schema error: {e}", file=sys.stderr)
        return 1

    target, action = archive.write_memory(write=args.write, force=args.force)
    index_action = archive.update_index(write=args.write)

    prefix = "[write]" if args.write else "[dry-run]"
    print(f"{prefix} anti_pattern_id: {archive.data['anti_pattern_id']}")
    print(f"        memory file: {target}")
    print(f"        memory file action: {action}")
    print(f"        index action: {index_action}")

    if args.show or not args.write:
        print("---")
        print(archive.memory_body())

    if action == "skipped":
        print(
            "note: memory file already exists. Pass --force to overwrite.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
