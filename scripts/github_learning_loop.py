#!/usr/bin/env python3
"""
github_learning_loop.py — poll a fixed watchlist of public trading repos for
new merged PRs / closed issues / hot discussions, filter for relevance to
our hybrid_v5.1 sniper, and write a digest the operator can review.

Strict-mode design (mirrors moltbook-learning-loop):
- This script is INGESTION only. It NEVER writes contributor ledger entries.
- A GitHub user only enters web/public/data/contributors.json when their
  PR/issue/comment is adopted as a NAMED shadow rule in sol_sniper_executor.py
  and the resulting shadow_*_rule.jsonl carries:
    proposed_by:        <github_login>
    proposed_source:    "github"     <-- new (default "moltbook" for back-compat)
    proposed_in_url:    "<PR or issue URL>"
- contributors_sync.py reads those fields and creates the stub. That's the
  only path to public credit.

Watchlist (hard-coded; a starting set, kept small on purpose):
- hummingbot/hummingbot — perp + maker behaviour
- freqtrade/freqtrade   — strategy framework + risk
- ccxt/ccxt             — exchange/SDK behaviour changes (close_position-class
                          regressions are exactly the ones we got bitten by
                          on 2026-04-29 → α2 path)

State:
- ~/ibitlabs/state/github_learning_cursor.json  (per-repo last_seen markers)

Outputs per run:
- ~/ibitlabs/logs/github-learning-loop/raw/<repo>__<YYYYMMDD-HHMMSS>.jsonl
- ~/ibitlabs/logs/github-learning-loop/digests/<YYYYMMDD-HHMMSS>.md

Run manually:
  ~/ibitlabs/scripts/github_learning_loop.py            # incremental
  ~/ibitlabs/scripts/github_learning_loop.py --backfill # 30-day backfill
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path("/Users/bonnyagent/ibitlabs")
STATE_PATH = REPO_ROOT / "state/github_learning_cursor.json"
PUSHED_PATH = REPO_ROOT / "state/github_learning_critical_pushed.json"
LOG_DIR = REPO_ROOT / "logs/github-learning-loop"
RAW_DIR = LOG_DIR / "raw"
DIGEST_DIR = LOG_DIR / "digests"

WATCHLIST = [
    "hummingbot/hummingbot",
    "freqtrade/freqtrade",
    "ccxt/ccxt",
]

RELEVANCE_PATTERN = re.compile(
    r"(?i)\b(regime|stochrsi|stoch[ -]?rsi|sniper|reduce[_ -]?only|"
    r"close[_ -]?position|perp(etual)?|funding[_ -]?rate|sortino|"
    r"trailing[_ -]?stop|drawdown|maker[_ -]?fee|fee[_ -]?cushion|"
    r"position[_ -]?ghost|ghost[_ -]?position|reconcile|risk[_ -]?manager)\b"
)

# Tight subset that warrants an immediate ntfy push, not just a digest entry.
# Picked from incidents that actually bit us: 04-29 close_position SDK saga,
# 04-26/04-29 ghost-position SQL incidents, reduce_only proto field rejections.
# Keep this small — every match is a phone push.
CRITICAL_PATTERN = re.compile(
    r"(?i)\b(close[_ -]?position|reduce[_ -]?only|"
    r"position[_ -]?ghost|ghost[_ -]?position|funding[_ -]?(rate[_ -]?)?lag)\b"
)

BACKFILL_DAYS = 30
HOT_DISCUSSION_MIN_COMMENTS = 3
BODY_TRUNCATE = 8000

# ------- gh wrapper ----------------------------------------------------------


def gh_get(endpoint: str, params: dict) -> list[dict]:
    """Single-page `gh api` call. Per-page is tuned to cover one 12h tick.

    Pagination is intentionally OFF: large repos (ccxt, freqtrade) time out on
    --paginate, and a single page sorted by `updated desc` already covers any
    realistic 12h window — the incremental cursor catches missed items on the
    next run, and --backfill widens per_page for the one-shot 30d sweep.
    """
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{endpoint}?{qs}" if qs else endpoint
    try:
        out = subprocess.run(
            ["gh", "api", url], check=True, capture_output=True, text=True, timeout=90
        ).stdout
    except subprocess.CalledProcessError as e:
        print(f"  gh api failed for {url}: {e.stderr[:200]}", file=sys.stderr)
        return []
    except subprocess.TimeoutExpired:
        print(f"  gh api timeout for {url}", file=sys.stderr)
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else [data]


# ------- relevance + extraction ---------------------------------------------


def is_relevant(title: str, body: str | None) -> bool:
    if RELEVANCE_PATTERN.search(title or ""):
        return True
    if body and RELEVANCE_PATTERN.search(body[:BODY_TRUNCATE]):
        return True
    return False


def is_critical(title: str) -> bool:
    """Title-only critical match; body is too noisy for high-priority pushes."""
    return bool(CRITICAL_PATTERN.search(title or ""))


# ------- ntfy push (mirrors ghost_position_watchdog pattern) -----------------


def ntfy(title: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC", "")
    if not topic:
        return
    safe_title = title.encode("ascii", errors="replace").decode("ascii").replace("?", "")
    safe_title = safe_title.strip() or "github-learning-loop"
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={"Title": safe_title, "Priority": "high"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        print(f"  ntfy push failed: {e}", file=sys.stderr)


def load_pushed() -> set[str]:
    if not PUSHED_PATH.exists():
        return set()
    try:
        return set(json.loads(PUSHED_PATH.read_text()))
    except Exception:
        return set()


def save_pushed(pushed: set[str]) -> None:
    PUSHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUSHED_PATH.write_text(json.dumps(sorted(pushed), indent=2) + "\n")


def push_critical_if_new(items: list[dict], pushed: set[str]) -> int:
    """For each item whose title hits CRITICAL_PATTERN and we've never pushed,
    fire one ntfy and record it. Returns count of pushes sent."""
    sent = 0
    for item in items:
        if not is_critical(item["title"]):
            continue
        key = f"{item['repo']}#{item['kind']}#{item['number']}"
        if key in pushed:
            continue
        title = f"github-learning-loop CRITICAL: {item['repo']}"
        body = (
            f"#{item['number']} by @{item.get('author') or '?'}\n"
            f"{item['title']}\n"
            f"{item['html_url']}"
        )
        ntfy(title, body)
        pushed.add(key)
        sent += 1
    return sent


def slim_pr(repo: str, pr: dict) -> dict:
    return {
        "repo": repo,
        "kind": "pr",
        "number": pr["number"],
        "title": pr["title"],
        "author": (pr.get("user") or {}).get("login"),
        "html_url": pr["html_url"],
        "merged_at": pr.get("merged_at"),
        "labels": [l["name"] for l in pr.get("labels", [])],
        "body_excerpt": (pr.get("body") or "")[:BODY_TRUNCATE],
    }


def slim_issue(repo: str, issue: dict) -> dict:
    return {
        "repo": repo,
        "kind": "issue",
        "number": issue["number"],
        "title": issue["title"],
        "author": (issue.get("user") or {}).get("login"),
        "html_url": issue["html_url"],
        "closed_at": issue.get("closed_at"),
        "comments": issue.get("comments", 0),
        "labels": [l["name"] for l in issue.get("labels", [])],
        "body_excerpt": (issue.get("body") or "")[:BODY_TRUNCATE],
    }


# ------- per-repo poller ----------------------------------------------------


def poll_repo(repo: str, cursor: dict, since_iso: str) -> dict:
    """Returns {'merged_prs': [...], 'closed_issues': [...]} of relevant + slim items."""
    last_pr = cursor.get(repo, {}).get("last_seen_pr_number", 0)
    last_issue = cursor.get(repo, {}).get("last_seen_issue_number", 0)
    per_page = 100 if last_pr == 0 else 30

    # Closed PRs sorted by updated desc; we filter to merged + relevant + above cursor.
    prs_raw = gh_get(
        f"/repos/{repo}/pulls",
        {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": per_page,
        },
    )
    merged_prs = []
    max_pr_seen = last_pr
    for pr in prs_raw:
        n = pr.get("number", 0)
        if n <= last_pr:
            continue
        if not pr.get("merged_at"):
            continue
        if pr["merged_at"] < since_iso:
            continue
        max_pr_seen = max(max_pr_seen, n)
        if not is_relevant(pr.get("title", ""), pr.get("body")):
            continue
        merged_prs.append(slim_pr(repo, pr))

    # Closed issues — use the issues endpoint with filter to drop pull_request rows.
    issues_raw = gh_get(
        f"/repos/{repo}/issues",
        {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": per_page,
            "since": since_iso,
        },
    )
    closed_issues = []
    max_issue_seen = last_issue
    for issue in issues_raw:
        if "pull_request" in issue:
            continue  # pull request, already covered above
        n = issue.get("number", 0)
        if n <= last_issue:
            continue
        max_issue_seen = max(max_issue_seen, n)
        if not is_relevant(issue.get("title", ""), issue.get("body")):
            continue
        closed_issues.append(slim_issue(repo, issue))

    cursor[repo] = {
        "last_seen_pr_number": max_pr_seen,
        "last_seen_issue_number": max_issue_seen,
        "last_run_iso": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    return {"merged_prs": merged_prs, "closed_issues": closed_issues}


# ------- digest writer ------------------------------------------------------


def write_raw(ts: str, repo: str, items: list[dict]) -> Path | None:
    if not items:
        return None
    safe_repo = repo.replace("/", "__")
    path = RAW_DIR / f"{safe_repo}__{ts}.jsonl"
    with path.open("w") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def write_digest(ts: str, all_results: dict[str, dict], summary_lines: list[str]) -> Path:
    path = DIGEST_DIR / f"{ts}.md"
    lines: list[str] = []
    lines.append(f"# github-learning-loop digest — {ts}")
    lines.append("")
    lines.append("## Run summary")
    lines.extend(f"- {s}" for s in summary_lines)
    lines.append("")
    lines.append("## How to credit a contributor")
    lines.append(
        "An author below earns a contributors.json entry **only** if you adopt "
        "the idea as a named shadow rule in `sol_sniper_executor.py`. Set "
        "`proposed_by=<github_login>`, `proposed_source=\"github\"`, and "
        "`proposed_in_url=<PR/issue URL>` on the shadow JSONL's first line. "
        "`contributors_sync.py` does the rest."
    )
    lines.append("")

    for repo, results in all_results.items():
        lines.append(f"## {repo}")
        for kind_label, items in (
            ("Merged PRs", results["merged_prs"]),
            ("Closed issues", results["closed_issues"]),
        ):
            if not items:
                continue
            lines.append(f"### {kind_label}")
            for item in items:
                author = item.get("author") or "?"
                url = item["html_url"]
                lines.append(f"- [{item['title']}]({url}) — @{author}")
                excerpt = (item.get("body_excerpt") or "").strip().replace("\n", " ")
                if excerpt:
                    lines.append(f"  > {excerpt[:300]}{'…' if len(excerpt) > 300 else ''}")
            lines.append("")
        if not results["merged_prs"] and not results["closed_issues"]:
            lines.append("_(no relevant items this run)_")
            lines.append("")

    path.write_text("\n".join(lines))
    return path


# ------- main ---------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--backfill",
        action="store_true",
        help=f"Ignore cursor; scan last {BACKFILL_DAYS} days. First-run mode.",
    )
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    cursor: dict = {}
    if STATE_PATH.exists() and not args.backfill:
        try:
            cursor = json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            cursor = {}

    if args.backfill:
        cursor = {}

    since = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    pushed = load_pushed()
    pushed_before = len(pushed)

    all_results: dict[str, dict] = {}
    summary: list[str] = []
    for repo in WATCHLIST:
        print(f"[{repo}] polling…")
        results = poll_repo(repo, cursor, since_iso)
        all_results[repo] = results
        items = results["merged_prs"] + results["closed_issues"]
        write_raw(ts, repo, items)
        sent = push_critical_if_new(items, pushed)
        suffix = f" — {sent} CRITICAL push(es)" if sent else ""
        summary.append(
            f"{repo}: {len(results['merged_prs'])} relevant merged PR(s), "
            f"{len(results['closed_issues'])} relevant closed issue(s)"
            f"{suffix}"
        )

    digest_path = write_digest(ts, all_results, summary)
    STATE_PATH.write_text(json.dumps(cursor, indent=2) + "\n")
    if len(pushed) != pushed_before:
        save_pushed(pushed)

    total = sum(
        len(r["merged_prs"]) + len(r["closed_issues"]) for r in all_results.values()
    )
    pushed_this_run = len(pushed) - pushed_before
    print(f"\ngithub-learning-loop: {total} relevant item(s) across {len(WATCHLIST)} repo(s)")
    if pushed_this_run:
        print(f"  CRITICAL pushes sent: {pushed_this_run}")
    print(f"digest: {digest_path}")
    if total == 0:
        print("(silence is a valid run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
