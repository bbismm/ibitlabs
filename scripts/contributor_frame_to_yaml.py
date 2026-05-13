#!/usr/bin/env python3
"""
contributor_frame_to_yaml.py — bridge a contributor's natural-language proposal
(from a Moltbook comment, GitHub issue, etc.) into a harness proposal yaml,
then optionally run validate_proposal.py on it.

This is the own-use wiring for the harness inside moltbook-reply-check (and any
future agent that handles inbound contributor frames). It does NOT decide
whether to open a shadow rule — it produces a structured yaml and tells you
which of the 5 funnel constraints the proposal currently fails.

Typical flow inside reply-check:
    1. Detect a proposal-shaped comment (hypothesis + direction + claim)
    2. Extract: proposed_by handle, comment URL, rule_name, hypothesis, direction
    3. Invoke this script with --validate
    4. Use the validator output in the reply draft (cite the memory rule
       behind whichever constraint failed — paste-back-ready rejection text)

Usage:
    python3 contributor_frame_to_yaml.py \\
        --proposed-by riverholybot \\
        --proposed-in https://moltbook.com/post/UUID#comment-uuid \\
        --rule-name constraint_decay_meta_governance \\
        --hypothesis "Each constraint should carry a half_life_days parameter; if 30d 0 useful intercepts + 15+ blocks of normal proposals, weight auto-decays." \\
        --direction neutral \\
        --evidence-seen 0 \\
        --evidence-source "1 conceptual proposal in Moltbook comment thread; no real-data instances yet" \\
        --validate

Exit codes (mirror validate_proposal.py when --validate is set):
    0  yaml produced AND (if --validate) all 5 constraints pass
    1  yaml produced AND --validate found violations (yaml still written)
    2  argument or IO error
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HARNESS = Path.home() / "ibitlabs" / "harness"
VALIDATE_CLI = HARNESS / "bin" / "validate_proposal.py"


def slugify(s: str) -> str:
    out = "".join(c if c.isalnum() else "_" for c in s.lower())
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:60] or "unnamed"


def yaml_escape_string(s: str) -> str:
    """Escape a string for a double-quoted YAML scalar."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_yaml(args) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    rule_id = args.proposal_id or f"proposed_{slugify(args.rule_name)}"
    shadow_log = args.shadow_log_jsonl or f"logs/shadow_{slugify(args.rule_name)}_rule.jsonl"

    ping_required = bool(args.proposed_by)
    proposed_by_field = (
        f'"{yaml_escape_string(args.proposed_by)}"' if args.proposed_by else "null"
    )
    proposed_in_field = (
        f'"{yaml_escape_string(args.proposed_in)}"' if args.proposed_in else "null"
    )

    # Indent hypothesis lines by 2 spaces under the `|` block scalar
    hypothesis_lines = args.hypothesis.strip().splitlines()
    indented = "\n".join(f"  {line}" for line in hypothesis_lines)

    return (
        f"proposal_id: {rule_id}\n"
        f"rule_name: {args.rule_name}\n"
        f"\n"
        f"proposed_by: {proposed_by_field}\n"
        f"proposed_in: {proposed_in_field}\n"
        f'proposed_at: "{now}"\n'
        f"\n"
        f"hypothesis: |\n"
        f"{indented}\n"
        f"direction: {args.direction}\n"
        f"\n"
        f"shadow_log_jsonl: {shadow_log}\n"
        f"control_flow_impact: log_only\n"
        f"\n"
        f"real_data_gate:\n"
        f"  evidence_threshold: 3\n"
        f"  evidence_seen: {args.evidence_seen}\n"
        f'  source: "{yaml_escape_string(args.evidence_source)}"\n'
        f"\n"
        f"shadow_budget:\n"
        f"  cap: 2\n"
        f"  current_active: {args.current_active}\n"
        f"\n"
        f"contributor_credit:\n"
        f"  ping_required: {str(ping_required).lower()}\n"
        f"  pinged_at: null\n"
        f"  ping_wait_hours: 48\n"
        f"  ack_received: false\n"
        f"\n"
        f"promotion_bar:\n"
        f"  min_entries: 30\n"
        f"  min_observation_days: 30\n"
        f"  min_hit_rate_spread_pp: 15\n"
        f"  direction_match_required: true\n"
        f"  no_confounding_shadow_required: true\n"
        f"  retire_after_days: 90\n"
        f"\n"
        f"rollback:\n"
        f"  on_bar_fail: retire_and_archive\n"
        f"  on_bug_discovered: reset_capital_and_window\n"
        f"  on_confounding_shadow: pause_and_review\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--proposed-by", required=True,
                    help="Contributor handle (Moltbook agent name or GitHub username)")
    ap.add_argument("--proposed-in", required=True,
                    help="URL of the source comment / issue / reply")
    ap.add_argument("--rule-name", required=True,
                    help="snake_case name, mirrors shadow jsonl rule_name")
    ap.add_argument("--hypothesis", required=True,
                    help="1-3 sentence falsifiable hypothesis; state direction + expected effect size")
    ap.add_argument("--direction", default="neutral",
                    choices=["long_bias", "short_bias", "both", "neutral"])
    ap.add_argument("--evidence-seen", type=int, default=0,
                    help="Real-data instances of this pattern we've seen — need >=3 to pass real_data_gate")
    ap.add_argument("--evidence-source", default="awaiting historical confirmation",
                    help="Where we saw the evidence_seen instances")
    ap.add_argument("--current-active", type=int, default=1,
                    help="Current active shadow count (default 1 = Rule F)")
    ap.add_argument("--shadow-log-jsonl",
                    help="Path relative to ~/ibitlabs/ (default: logs/shadow_<name>_rule.jsonl)")
    ap.add_argument("--proposal-id",
                    help="Override auto-generated proposal_id (default: proposed_<slug>)")
    ap.add_argument("--output",
                    help="Write yaml to this path (default: a /tmp file)")
    ap.add_argument("--validate", action="store_true",
                    help="Run validate_proposal.py on the produced yaml")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress the # wrote: line on stderr")
    args = ap.parse_args()

    yaml_text = build_yaml(args)

    if args.output:
        target_path = Path(args.output)
    else:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, prefix="contributor_frame_"
        )
        tmp.close()
        target_path = Path(tmp.name)
    target_path.write_text(yaml_text)

    if not args.quiet:
        print(f"# wrote yaml: {target_path}", file=sys.stderr)

    if not args.validate:
        print(yaml_text)
        return 0

    if not VALIDATE_CLI.exists():
        print(f"error: validate_proposal.py not found at {VALIDATE_CLI}", file=sys.stderr)
        return 2

    result = subprocess.run(
        [sys.executable, str(VALIDATE_CLI), str(target_path)],
        capture_output=True, text=True,
    )
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
