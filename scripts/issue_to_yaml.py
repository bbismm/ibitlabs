#!/usr/bin/env python3
"""issue_to_yaml.py — parse a GitHub issue (filled out via the propose-shadow-rule
form template) and emit a harness proposal yaml. Optionally validates against
the 5 funnel constraints.

This is the GitHub side of the contributor funnel, parallel to
contributor_frame_to_yaml.py (which handles Moltbook comments). Both produce the
same harness yaml shape; this one knows how to extract from GitHub form sections.

Usage:
    # From a GitHub issue number (uses `gh` CLI):
    python3 issue_to_yaml.py 42 [--validate] [--output PATH]

    # From stdin (e.g., piped from `gh issue view N --json body,url,author`):
    gh issue view 42 --json body,url,author | python3 issue_to_yaml.py --from-stdin --validate

    # From a local body file (testing only — no GitHub metadata):
    python3 issue_to_yaml.py --body-file body.md --validate

Exit codes:
    0  yaml produced (and --validate passed if requested)
    1  yaml produced; --validate found violations
    2  parse error / IO error / gh CLI failure
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Reuse build_yaml + the args-namespace shape from the Moltbook bridge.
sys.path.insert(0, str(Path(__file__).parent))
from contributor_frame_to_yaml import build_yaml as build_proposal_yaml  # noqa: E402

# Form-template label → internal extraction key. Update if the template changes.
LABEL_MAP = {
    "Rule handle": "rule_name",
    "The condition (precise)": "condition",
    "Direction bias": "direction",
    "Hypothesis (what would the data show if this works?)": "hypothesis",
    "Real-data evidence count": "evidence_count",
    "Real-data evidence source": "evidence_source",
    "Why this isn't a paraphrase of existing rules": "not_duplicate",
    "Promotion criteria (sample × effect × direction)": "acceptance",
    "Handle for credit on /contributors (optional)": "handle",
    "Source post / discussion (optional)": "source_post",
}

VALID_DIRECTIONS = {"long_bias", "short_bias", "both", "neutral"}


def parse_issue_body(body: str) -> dict[str, str]:
    """Split a GitHub form-template body by `### <Label>` sections."""
    out: dict[str, str] = {}
    sections = re.split(r"^### ", body, flags=re.MULTILINE)
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        first_nl = sec.find("\n")
        if first_nl == -1:
            continue
        label = sec[:first_nl].strip()
        value = sec[first_nl:].strip()
        # GitHub renders empty optional fields as `_No response_`
        if value in ("_No response_", "_None_"):
            value = ""
        if label in LABEL_MAP:
            out[LABEL_MAP[label]] = value
    return out


def fetch_issue_via_gh(issue_ref: str) -> dict:
    """Run `gh issue view <ref> --json body,number,url,author` and return dict."""
    cmd = ["gh", "issue", "view", issue_ref, "--json", "body,number,url,author"]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE)
    except FileNotFoundError as e:
        raise RuntimeError("gh CLI not found; install with `brew install gh`") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"gh view failed: {e.stderr.strip()}") from e
    return json.loads(out)


def to_namespace(parsed: dict[str, str], *, issue_url: str | None = None,
                 author_login: str | None = None):
    """Map parsed form fields → an argparse-like namespace usable by build_yaml."""
    rule_name = parsed.get("rule_name", "").strip() or "unnamed_rule"
    direction = parsed.get("direction", "neutral").strip()
    if direction not in VALID_DIRECTIONS:
        direction = "neutral"
    hypothesis = parsed.get("hypothesis", "").strip() or "Hypothesis missing from issue body."

    raw_count = parsed.get("evidence_count", "0").strip()
    try:
        evidence_seen = int(raw_count.split()[0])  # tolerate "3" or "3 instances"
    except (ValueError, IndexError):
        evidence_seen = 0
    evidence_source = parsed.get("evidence_source", "").strip() or "no source provided in issue body"

    # proposed_by: form field "Handle for credit" wins; fall back to GitHub issue author.
    handle = parsed.get("handle", "").strip().lstrip("@")
    if not handle and author_login:
        handle = author_login.lstrip("@")

    # proposed_in: form field "Source post" wins; fall back to GitHub issue URL.
    source = parsed.get("source_post", "").strip()
    proposed_in = source or issue_url or ""

    class Args:
        pass
    a = Args()
    a.proposal_id = None
    a.rule_name = rule_name
    a.proposed_by = handle if handle else None
    a.proposed_in = proposed_in
    a.hypothesis = hypothesis
    a.direction = direction
    a.evidence_seen = evidence_seen
    a.evidence_source = evidence_source
    a.current_active = 1   # Rule F is in shadow; matches harness state at write time
    a.shadow_log_jsonl = None  # let build_yaml auto-name from rule_name
    return a


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("issue_ref", nargs="?", help="GitHub issue number or URL (uses gh CLI)")
    src.add_argument("--from-stdin", action="store_true",
                     help="Read JSON {body, url, author:{login}} from stdin")
    src.add_argument("--body-file", help="Read body markdown from this file (testing)")
    ap.add_argument("--validate", action="store_true",
                    help="Run validate_proposal.py on the produced yaml")
    ap.add_argument("--output", help="Write yaml to this path (else /tmp + print to stdout)")
    args = ap.parse_args()

    body = ""
    issue_url: str | None = None
    author_login: str | None = None

    if args.from_stdin:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"error: stdin not valid JSON: {e}", file=sys.stderr)
            return 2
        body = data.get("body", "") or ""
        issue_url = data.get("url")
        author_login = (data.get("author") or {}).get("login")
    elif args.body_file:
        body = Path(args.body_file).read_text()
    else:
        try:
            data = fetch_issue_via_gh(args.issue_ref)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        body = data.get("body", "") or ""
        issue_url = data.get("url")
        author_login = (data.get("author") or {}).get("login")

    if not body.strip():
        print("error: empty issue body", file=sys.stderr)
        return 2

    parsed = parse_issue_body(body)
    if not parsed.get("rule_name"):
        print(
            "error: could not extract 'Rule handle' from issue body — "
            "is this a propose-shadow-rule template issue?",
            file=sys.stderr,
        )
        return 2

    namespace = to_namespace(parsed, issue_url=issue_url, author_login=author_login)
    yaml_text = build_proposal_yaml(namespace)

    if args.output:
        target = Path(args.output)
    else:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, prefix="issue_to_yaml_"
        )
        tmp.close()
        target = Path(tmp.name)
    target.write_text(yaml_text)
    print(f"# wrote yaml: {target}", file=sys.stderr)

    if not args.validate:
        print(yaml_text)
        return 0

    validate_cli = Path.home() / "ibitlabs" / "harness" / "bin" / "validate_proposal.py"
    if not validate_cli.exists():
        print(f"error: validate_proposal.py not found at {validate_cli}", file=sys.stderr)
        return 2
    result = subprocess.run(
        [sys.executable, str(validate_cli), str(target)],
        capture_output=True, text=True,
    )
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
