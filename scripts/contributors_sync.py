#!/usr/bin/env python3
"""
contributors_sync.py — sync contributors.json from shadow JSONL schema v2 metadata.

Reads /Users/bonnyagent/ibitlabs/logs/shadow_*_rule.jsonl, extracts
schema_version >= 2 metadata (rule_id, rule_name, proposed_by, proposed_in,
proposed_source, proposed_in_url), and merges into
web/public/data/contributors.json.

Rules:
- proposed_by == "operator" → skip (no public attribution).
- Existing rule_id present → only auto-fill missing window dates; never
  overwrite operator-curated fields (frame, source_post, operator_note).
- New rule_id → append a stub entry with `_auto_generated: True` so the
  operator can spot it and fill frame/source_post manually.
- Output is byte-identical when nothing changed (idempotent; the wrapper
  only commits + deploys when the file actually changes).

Sources:
- proposed_source == "moltbook" (default for back-compat) → profile URL points
  to https://moltbook.com/u/{handle}, source_post starts as null.
- proposed_source == "github" → profile URL points to https://github.com/{handle},
  source_post is auto-populated from proposed_in_url so the operator doesn't
  have to fill it (GitHub URLs are stable; Moltbook URLs aren't).

Run manually:
  ~/ibitlabs/scripts/contributors_sync.py
Run from cron: invoked by run_moltbook_archive.sh at the end.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path("/Users/bonnyagent/ibitlabs")
LOGS_DIR = REPO / "logs"
CONTRIBUTORS_PATH = REPO / "web/public/data/contributors.json"
SHADOW_GLOB = "shadow_*_rule.jsonl"
SHADOW_WINDOW_DAYS = 30

POINTS_LEGEND = {
    "frame_stage_not_rule_yet": 5,
    "queued": 10,
    "shadow_window_open": 25,
    "shadow_window_passed": 100,
}


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def first_v2_metadata(path: Path) -> dict | None:
    """Return metadata from first line with schema_version >= 2, else None."""
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("schema_version", 1) >= 2:
                    return rec
        return None
    except FileNotFoundError:
        return None


def main() -> int:
    if not CONTRIBUTORS_PATH.exists():
        print(f"FATAL: {CONTRIBUTORS_PATH} not found", file=sys.stderr)
        return 1

    contributors = json.loads(CONTRIBUTORS_PATH.read_text())
    adopted = contributors.setdefault("adopted", [])
    by_rule_id = {e.get("rule_id"): e for e in adopted if e.get("rule_id")}

    changes: list[str] = []
    seen_files = 0

    for shadow_path in sorted(LOGS_DIR.glob(SHADOW_GLOB)):
        seen_files += 1
        rec = first_v2_metadata(shadow_path)
        if not rec:
            continue

        rule_id = rec.get("rule_id")
        rule_name = rec.get("rule_name")
        proposed_by = rec.get("proposed_by")
        proposed_in = rec.get("proposed_in")
        proposed_source = rec.get("proposed_source", "moltbook")
        proposed_in_url = rec.get("proposed_in_url")
        fire_ts = rec.get("fire_ts")

        if not rule_id or not rule_name or not proposed_by:
            continue
        if proposed_by == "operator":
            continue
        if not isinstance(fire_ts, (int, float)):
            continue

        existing = by_rule_id.get(rule_id)

        if existing is None:
            if proposed_source == "github":
                profile_url = f"https://github.com/{proposed_by}"
                source_post = proposed_in_url
            else:
                profile_url = f"https://moltbook.com/u/{proposed_by}"
                source_post = None
            stub = {
                "handle": proposed_by,
                "source": proposed_source,
                "profile_url": profile_url,
                "frame": None,
                "first_stated_in": proposed_in,
                "moltbook_url": profile_url if proposed_source == "moltbook" else None,
                "source_post": source_post,
                "rule_id": rule_id,
                "rule_name": rule_name,
                "adopted_on": iso_date(fire_ts),
                "code_location": f"sol_sniper_executor.py::_log_shadow_{rule_name}",
                "shadow_log": f"/logs/{shadow_path.name}",
                "shadow_window_opens": iso(fire_ts),
                "shadow_window_review": iso(fire_ts + SHADOW_WINDOW_DAYS * 86400),
                "review_status": "shadow_window_open",
                "points": POINTS_LEGEND["shadow_window_open"],
                "wallet_address": None,
                "operator_note": (
                    "(auto-generated stub — operator: fill frame description"
                    f"{'' if proposed_source == 'github' else ' + source_post URL'}"
                    ", then remove _auto_generated)"
                ),
                "_auto_generated": True,
            }
            adopted.append(stub)
            by_rule_id[rule_id] = stub
            changes.append(
                f"+ added stub for rule {rule_id} ({rule_name}) by {proposed_by} "
                f"[source={proposed_source}]"
            )
            continue

        if not existing.get("shadow_window_opens"):
            existing["shadow_window_opens"] = iso(fire_ts)
            existing["shadow_window_review"] = iso(fire_ts + SHADOW_WINDOW_DAYS * 86400)
            changes.append(f"~ filled shadow_window dates for rule {rule_id}")

    if changes:
        contributors["last_updated"] = iso(datetime.now(timezone.utc).timestamp())
        CONTRIBUTORS_PATH.write_text(
            json.dumps(contributors, indent=2, ensure_ascii=False) + "\n"
        )
        print(f"contributors_sync: {len(changes)} change(s) across {seen_files} shadow file(s)")
        for line in changes:
            print(f"  {line}")
        return 0

    print(f"contributors_sync: no changes ({seen_files} shadow file(s) scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
