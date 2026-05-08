#!/usr/bin/env python3
"""
moltbook_archive.py — pull all known @ibitlabs_agent posts + comments to disk.

Source 1: profile endpoint recentPosts (visible top 10).
Source 2: scrape known post IDs from local files (claude session jsonl,
  CLAUDE.md, saga chapters, contributors.json, memory files) — these
  are posts we've referenced anywhere on this Mac, even if they've fallen
  out of the API's recent listing.

For each known post id:
  GET /api/v1/posts/{id}        → full title + body
  GET /api/v1/posts/{id}/comments?limit=100  → all comments

Writes one JSON per post to ~/ibitlabs/data/moltbook_archive/<post_id>.json
plus an _index.json at top-level with summary rows.

Usage:
  python3 ~/ibitlabs/scripts/moltbook_archive.py
  python3 ~/ibitlabs/scripts/moltbook_archive.py --extra-id <uuid> [--extra-id <uuid> ...]

Auth: Moltbook Bearer key from macOS Keychain (service ibitlabs-moltbook-agent).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import urllib.request
import urllib.parse
import urllib.error

API_BASE = "https://moltbook.com/api/v1"
ARCHIVE_DIR = Path.home() / "ibitlabs" / "data" / "moltbook_archive"
# Both iBitLabs personas — brand-builder posts under ibitlabs_agent,
# reporter (Trading Minds) posts under ibitlabs_reporter. We archive both
# because reporter's threads carry interlocutor frames that show up in our
# contributor ledger (e.g. RiskOfficer_Bot's HMM × Monte Carlo content
# lives entirely on a Trading Minds #1 thread). Each archived JSON keeps
# its author name so downstream tools can filter as needed.
OUR_AGENTS = {"ibitlabs_agent", "ibitlabs_reporter"}
AGENT_NAME = "ibitlabs_agent"  # primary, used for profile recentPosts seeding

# UUID4 regex — 8-4-4-4-12 hex
# Only match UUIDs that appear in a Moltbook post URL pattern — avoids
# false-positive UUIDs from session jsonl tool-call IDs, message IDs, etc.
# v1 of this script naively scraped bare UUIDs and produced 24,511 candidates,
# 99.96% of which were 404 noise that ate the rate limit. v2 only takes
# UUIDs that someone wrote down as Moltbook post URLs.
MOLTBOOK_POST_URL_RE = re.compile(
    r"moltbook\.com/(?:post|p)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

# Locations to scan for known post IDs we may want to back-archive.
# Be tight here — we want files where Moltbook post URLs are deliberately
# recorded, not noise sources.
SCAN_PATHS = [
    Path.home() / "ibitlabs" / "CLAUDE.md",
    Path.home() / "ibitlabs" / "web" / "public" / "data",
    Path.home() / "Documents" / "Claude" / "Scheduled" / "moltbook-brand-builder",
    Path.home() / ".claude" / "projects" / "-Users-bonnyagent" / "memory",
    Path.home() / "trading_minds_log_2026-04-15.md",
    Path.home() / "trading_minds_log_2026-04-16.md",
    Path.home() / "trading_minds_log_2026-04-21.md",
    Path.home() / "ibitlabs" / "web" / "public" / "saga",
    # session jsonls included LAST + URL-pattern only (not bare UUID)
    Path.home() / ".claude" / "projects" / "-Users-bonnyagent",
]

# Rate-limit pacing
FETCH_INTERVAL_SECONDS = 0.7
RATE_LIMIT_BACKOFF_SECONDS = 60


def get_api_key() -> str:
    """Read the @ibitlabs_agent Moltbook key from macOS Keychain."""
    try:
        out = subprocess.check_output(
            ["security", "find-generic-password",
             "-s", "ibitlabs-moltbook-agent", "-a", "ibitlabs", "-w"],
            text=True,
        ).strip()
        if not out:
            sys.exit("FATAL: empty key returned from Keychain.")
        return out
    except subprocess.CalledProcessError:
        sys.exit("FATAL: could not read ibitlabs-moltbook-agent from Keychain.")


def get_json(url: str, key: str) -> dict | list | None:
    """Fetch JSON with rate-limit awareness.

    On 429: sleep RATE_LIMIT_BACKOFF_SECONDS, retry once. On second 429,
    return None (caller already paces). On 404, silent return None.
    """
    for attempt in (1, 2):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                if attempt == 1:
                    sys.stderr.write(
                        f"  HTTP 429 — backing off {RATE_LIMIT_BACKOFF_SECONDS}s, "
                        f"retrying once: {url}\n"
                    )
                    time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                    continue
                sys.stderr.write(f"  HTTP 429 (after backoff) — giving up: {url}\n")
                return None
            sys.stderr.write(f"  HTTP {e.code} on {url}\n")
            return None
        except Exception as e:
            sys.stderr.write(f"  fetch error on {url}: {e}\n")
            return None
    return None


def discover_recent_post_ids(key: str) -> list[str]:
    """Pull recent posts from the profile endpoint."""
    d = get_json(
        f"{API_BASE}/agents/profile?name={urllib.parse.quote(AGENT_NAME)}", key
    )
    if not d:
        return []
    return [p.get("id") for p in d.get("recentPosts", []) if p.get("id")]


def scrape_local_for_post_ids() -> set[str]:
    """Walk SCAN_PATHS and extract UUIDs that appear in Moltbook post URLs.

    v2: only matches the explicit `moltbook.com/post/<uuid>` or
    `moltbook.com/p/<uuid>` pattern — avoids the 24K-candidate noise from
    bare UUIDs in session jsonl tool-call IDs.
    """
    ids: set[str] = set()
    for root in SCAN_PATHS:
        if not root.exists():
            continue
        if root.is_file():
            files = [root]
        else:
            files = list(root.rglob("*"))
        for f in files:
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
            except Exception:
                continue
            if size > 50 * 1024 * 1024:  # >50MB skip
                continue
            try:
                text = f.read_text(errors="replace")
            except Exception:
                continue
            ids.update(m.lower() for m in MOLTBOOK_POST_URL_RE.findall(text))
    return ids


def fetch_post(post_id: str, key: str) -> dict | None:
    """Fetch full post + comments. Returns the merged record or None."""
    post = get_json(f"{API_BASE}/posts/{post_id}", key)
    if not post:
        return None
    # Endpoint sometimes wraps as {"post": {...}}
    if isinstance(post, dict) and "post" in post and isinstance(post["post"], dict):
        post = post["post"]
    # Filter to posts authored by either iBitLabs persona — agent or reporter.
    # We capture reporter posts because their threads contain frames from
    # named interlocutors that feed our contributor ledger (R8).
    author = (post.get("author") or post.get("agent") or {})
    author_name = author.get("name") if isinstance(author, dict) else None
    is_ours = (author_name in OUR_AGENTS) or (post.get("agent_name") in OUR_AGENTS)
    # Comments. NOTE: API rejects sort=oldest with HTTP 400.
    # `?sort=best&limit=100` is the working query (verified 2026-04-28).
    comments = get_json(
        f"{API_BASE}/posts/{post_id}/comments?sort=best&limit=100", key
    )
    comments_list = comments if isinstance(comments, list) else (
        comments.get("comments", []) if isinstance(comments, dict) else []
    )
    return {
        "post_id": post_id,
        "_archived_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "post": post,
        "comments": comments_list,
        "_known_to_be_ours": bool(is_ours),
    }


def build_index(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        p = r.get("post", {})
        rows.append({
            "post_id": r["post_id"],
            "title": p.get("title", ""),
            "created_at": p.get("created_at"),
            "submolt": (p.get("submolt") or {}).get("name") if isinstance(p.get("submolt"), dict) else p.get("submolt"),
            "upvotes": p.get("upvotes", 0),
            "downvotes": p.get("downvotes", 0),
            "comment_count": len(r.get("comments") or []),
            "url": f"https://moltbook.com/post/{r['post_id']}",
            "archived_at": r["_archived_at"],
        })
    rows.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra-id", action="append", default=[],
                    help="Additional post IDs to archive (repeatable).")
    ap.add_argument("--no-scan", action="store_true",
                    help="Skip local-file scrape; only archive profile recent + --extra-id.")
    args = ap.parse_args()

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    key = get_api_key()

    print(f"=== Moltbook archive pass starting @ {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ===")
    recent = discover_recent_post_ids(key)
    print(f"profile recentPosts: {len(recent)} ids")

    candidates: set[str] = set(recent) | set(i.lower() for i in args.extra_id)
    if not args.no_scan:
        scraped = scrape_local_for_post_ids()
        # Don't add UUIDs that look like things-other-than-posts; we'll let
        # the API filter (404 → skip).
        print(f"local scrape candidate UUIDs: {len(scraped)}")
        candidates |= scraped

    # Process recent first (the 10 most important), then everything else.
    # Skip already-archived posts so re-runs are cheap and idempotent.
    recent_set = set(recent)
    ordered = recent + sorted(c for c in candidates if c not in recent_set)
    seen: set[str] = set()
    deduped: list[str] = []
    for c in ordered:
        if c in seen:
            continue
        seen.add(c)
        deduped.append(c)

    already_archived = {p.stem for p in ARCHIVE_DIR.glob("*.json") if p.stem != "_index"}
    print(f"total candidate ids to try: {len(deduped)} "
          f"(already archived locally: {len(already_archived)})")

    records: list[dict] = []
    skipped_404 = 0
    skipped_not_ours = 0
    skipped_already = 0
    for i, pid in enumerate(deduped, 1):
        # Idempotent: if we already have it, load from disk and skip the fetch.
        if pid in already_archived:
            try:
                cached = json.loads((ARCHIVE_DIR / f"{pid}.json").read_text())
                records.append(cached)
                skipped_already += 1
                continue
            except Exception:
                pass  # fall through to refetch
        r = fetch_post(pid, key)
        if r is None:
            skipped_404 += 1
            time.sleep(FETCH_INTERVAL_SECONDS)
            continue
        is_recent = pid in recent_set
        if not (r.get("_known_to_be_ours") or is_recent):
            skipped_not_ours += 1
            time.sleep(FETCH_INTERVAL_SECONDS)
            continue
        out = ARCHIVE_DIR / f"{pid}.json"
        out.write_text(json.dumps(r, indent=2, ensure_ascii=False))
        records.append(r)
        if i % 10 == 0 or i == len(deduped):
            print(f"  ... archived {len(records)} so far (tried {i}/{len(deduped)})")
        time.sleep(FETCH_INTERVAL_SECONDS)

    print(f"DONE — archived {len(records)} posts; "
          f"({skipped_already} from cache, "
          f"{skipped_404} 404, {skipped_not_ours} non-ibitlabs_agent)")

    index_rows = build_index(records)
    index_path = ARCHIVE_DIR / "_index.json"
    index_path.write_text(json.dumps({
        "archive_version": 1,
        "agent": AGENT_NAME,
        "last_archived_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "post_count": len(index_rows),
        "total_comments": sum(r["comment_count"] for r in index_rows),
        "posts": index_rows,
    }, indent=2, ensure_ascii=False))
    print(f"index → {index_path}")

    if index_rows:
        oldest = index_rows[-1]
        newest = index_rows[0]
        print(f"oldest archived: {oldest['created_at']} | {oldest['title'][:70]}")
        print(f"newest archived: {newest['created_at']} | {newest['title'][:70]}")


if __name__ == "__main__":
    main()
