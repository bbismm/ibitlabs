"""AntiPattern: archives a falsified rule into memory as feedback_*.md.

Writes:
  1. ~/.claude/projects/-Users-bonnyagent/memory/<memory_file>
  2. One-line entry appended to MEMORY.md (if memory_index_line set)

Safety: dry_run=True by default in the API. The archive_falsified.py CLI also defaults
to dry-run; use --write to commit. If the memory file already exists, refuses to
overwrite without --force.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
import jsonschema

HARNESS_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = HARNESS_ROOT / "schemas" / "anti_pattern.schema.json"
MEMORY_DIR = Path("/Users/bonnyagent/.claude/projects/-Users-bonnyagent/memory")
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"


@dataclass
class AntiPattern:
    data: dict[str, Any]
    source_path: Path

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AntiPattern":
        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f)
        return cls(data=data, source_path=path)

    def validate_schema(self) -> None:
        with SCHEMA_PATH.open() as f:
            schema = json.load(f)
        jsonschema.validate(instance=self.data, schema=schema)

    def memory_body(self) -> str:
        d = self.data
        first_why_line = d["why_falsified"].strip().splitlines()[0][:120]
        lines = [
            "---",
            f"name: {d['anti_pattern_id']}",
            f"description: Falsified — {first_why_line}",
            "type: feedback",
            "---",
            "",
            f"**{d['anti_pattern_id']}** — falsified {d['falsified_at']}.",
            "",
            f"**Original proposal:** `{d['original_proposal_id']}`",
            "",
            "**Evidence:**",
        ]
        for ev in d["evidence"]:
            lines.append(f"- {ev}")
        lines += [
            "",
            "**Why falsified:**",
            "",
            d["why_falsified"].strip(),
            "",
            "**Aliases blocked (these count as the same anti-pattern):**",
        ]
        for alias in d.get("aliases_blocked", []):
            lines.append(f"- `{alias}`")
        if d.get("next_proposal_check"):
            lines += [
                "",
                "**Before re-proposing:**",
                "",
                d["next_proposal_check"].strip(),
            ]
        lines += [
            "",
            f"**Falsified in:** {d.get('falsified_in', 'n/a')}",
            "",
            f"Source archive: `{self.source_path}`",
            "",
        ]
        return "\n".join(lines)

    def write_memory(self, *, write: bool = False, force: bool = False) -> tuple[Path, str]:
        """Returns (target_path, action) where action is 'wrote' / 'dry-run' / 'skipped'."""
        target = MEMORY_DIR / Path(self.data["memory_file"]).name
        body = self.memory_body()
        if not write:
            return target, "dry-run"
        if target.exists() and not force:
            return target, "skipped"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        return target, "wrote"

    def update_index(self, *, write: bool = False) -> str:
        """Returns 'appended' / 'skipped' / 'no_line' / 'no_index'."""
        line = self.data.get("memory_index_line")
        if not line:
            return "no_line"
        if not MEMORY_INDEX.exists():
            return "no_index"
        existing = MEMORY_INDEX.read_text()
        target_basename = Path(self.data["memory_file"]).name
        if target_basename in existing:
            return "skipped"
        if not write:
            return "dry-run"
        with MEMORY_INDEX.open("a") as f:
            if not existing.endswith("\n"):
                f.write("\n")
            f.write(line.rstrip() + "\n")
        return "appended"
