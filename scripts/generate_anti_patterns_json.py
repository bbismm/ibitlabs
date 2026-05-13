#!/usr/bin/env python3
"""generate_anti_patterns_json.py — reads all harness/examples/*.yaml that are
anti-patterns (have `anti_pattern_id` field) and emits web/public/data/anti_patterns.json
for the /falsified web page to render.

This is the C-2 step from the harness strategic-depth plan: each anti-pattern
becomes a public "why we said no" web artifact. Failure as teaching material —
vision third pillar (传 / teach by record).

Usage:
    python3 scripts/generate_anti_patterns_json.py
    # outputs to web/public/data/anti_patterns.json

Run after adding/editing any harness/examples/*.yaml anti-pattern. Could be
wired into a daily cron parallel to run_harness_status.sh; for now manual.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "harness" / "examples"
TARGET = REPO_ROOT / "web" / "public" / "data" / "anti_patterns.json"
GITHUB_BASE = "https://github.com/bbismm/ibitlabs/blob/main/harness/examples"


def load_anti_patterns() -> list[dict]:
    out: list[dict] = []
    for yaml_file in sorted(EXAMPLES_DIR.glob("*.yaml")):
        with yaml_file.open() as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "anti_pattern_id" not in data:
            continue
        out.append({
            "anti_pattern_id": data["anti_pattern_id"],
            "domain": data.get("domain", "trading"),
            "original_proposal_id": data.get("original_proposal_id", ""),
            "falsified_at": data.get("falsified_at", ""),
            "falsified_in": data.get("falsified_in", ""),
            "evidence": data.get("evidence", []),
            "why_falsified": data.get("why_falsified", "").strip(),
            "aliases_blocked": data.get("aliases_blocked", []),
            "next_proposal_check": data.get("next_proposal_check", "").strip(),
            "memory_file": data.get("memory_file", ""),
            "source_yaml": f"{GITHUB_BASE}/{yaml_file.name}",
        })
    return out


def main() -> int:
    items = load_anti_patterns()
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(items),
        "by_domain": {},
        "anti_patterns": items,
    }
    for item in items:
        d = item["domain"]
        out["by_domain"][d] = out["by_domain"].get(d, 0) + 1

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {TARGET} ({TARGET.stat().st_size} bytes)")
    print(f"  count: {out['count']}")
    print(f"  by_domain: {out['by_domain']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
