#!/usr/bin/env python3
"""
twitter_follow_batch.py — Follow a list of handles from @BonnyOuyang.

Usage:
    python3 twitter_follow_batch.py --dry-run   # validate handles resolve, don't follow
    python3 twitter_follow_batch.py             # actually follow
    python3 twitter_follow_batch.py --file my_list.txt

Handle file format: one handle per line, '@' prefix optional, '#' for comments.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/Users/bonnyagent/ibitlabs/.env")
except Exception:
    pass

# Suppress NotOpenSSLWarning
import warnings
warnings.filterwarnings("ignore")

import tweepy


# ── Default target list: AI builders + indie hackers + non-coder advocates ──
# Mix of reachable-size (1K-500K followers) and aspirational.
# She can add crypto-circle friends by passing --file.
DEFAULT_HANDLES = [
    # AI builders
    "amasad",        # Replit CEO
    "levelsio",      # Pieter Levels
    "simonw",        # Simon Willison
    "shl",           # Sahil Lavingia
    "swyx",          # Shawn Wang
    "nutlope",       # Hassan El Mghari
    "jasonzhou1993", # Jason Zhou (AI agents)
    "kettanaito",
    # Non-coder / solo-founder advocates
    "marc_louvion",
    "thisiskp_",
    "patio11",       # Patrick McKenzie
    "dhh",
    "nathanbarry",
    "gregisenberg",
    "iamharaldur",
    "rameerez",
    # Build-in-public
    "jakelevine",
    "davidcramer",
    "adamwathan",
    "tdinh_me",
    # AI / dev ecosystem
    "karpathy",
    "sama",
    "danielgross",
    "EladGil",
    "patrickc",
    "paulg",
    "jasonlk",
    "lizthedeveloper",
    "simonw",        # duplicate — ignored
    "shuding_",
]


def load_handles(path: Path | None) -> list[str]:
    if not path:
        return DEFAULT_HANDLES
    raw = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in raw:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line.lstrip("@"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Resolve handles to user IDs, don't follow")
    ap.add_argument("--file", type=Path, default=None,
                    help="Text file of handles (one per line, '#' for comments). "
                         "If omitted, uses baked-in AI-builder list.")
    ap.add_argument("--sleep", type=float, default=3.0,
                    help="Seconds between follow calls (default 3.0)")
    args = ap.parse_args()

    handles = load_handles(args.file)
    # dedupe while preserving order
    seen = set(); unique = []
    for h in handles:
        h = h.lower().lstrip("@")
        if h and h not in seen:
            seen.add(h); unique.append(h)
    handles = unique
    print(f"→ {len(handles)} unique handles")

    client = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )
    try:
        me = client.get_me()
    except Exception as e:
        print(f"[fatal] get_me failed: {e}", file=sys.stderr); sys.exit(1)
    my_id = me.data.id
    print(f"→ authed as @{me.data.username} (id={my_id})\n")

    ok, skipped, failed = [], [], []
    for i, h in enumerate(handles, 1):
        try:
            u = client.get_user(username=h)
            if not u.data:
                skipped.append((h, "not_found"))
                print(f"[{i:2}/{len(handles)}] @{h} NOT FOUND")
                continue
            uid = u.data.id
            if args.dry_run:
                ok.append((h, uid))
                print(f"[{i:2}/{len(handles)}] @{h} → id={uid}  [dry-run]")
            else:
                client.follow_user(target_user_id=uid)
                ok.append((h, uid))
                print(f"[{i:2}/{len(handles)}] @{h} → followed (id={uid})")
                time.sleep(args.sleep)
        except tweepy.errors.TooManyRequests as e:
            failed.append((h, "rate_limit"))
            print(f"[{i:2}/{len(handles)}] @{h} RATE LIMIT — sleeping 60s")
            time.sleep(60)
        except Exception as e:
            failed.append((h, str(e)[:80]))
            print(f"[{i:2}/{len(handles)}] @{h} FAIL: {e}")

    print(f"\n── summary ──")
    print(f"  ok:      {len(ok)}")
    print(f"  skipped: {len(skipped)}")
    print(f"  failed:  {len(failed)}")
    if failed:
        for h, why in failed:
            print(f"    - @{h}: {why}")


if __name__ == "__main__":
    main()
