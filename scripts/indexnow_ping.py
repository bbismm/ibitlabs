#!/usr/bin/env python3
"""
indexnow_ping.py — Notify Bing / Yandex / Seznam / Naver of new URLs via the
IndexNow protocol. Single POST covers all participating search engines.

Usage:
    # Ping a new Day (use after deploy)
    python3 indexnow_ping.py --day 18

    # Ping arbitrary URLs
    python3 indexnow_ping.py --urls https://www.ibitlabs.com/days https://www.ibitlabs.com/essays

    # Ping everything about /days (index + RSS + sitemap + all day anchors)
    python3 indexnow_ping.py --all-days
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

HOST = "www.ibitlabs.com"
KEY = "84219e6a1fda35fd22014b2d22a59aa2"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
DAYS_JSON = Path("/Users/bonnyagent/ibitlabs/web/public/data/days.json")


def ping(urls: list[str]) -> bool:
    if not urls:
        print("[indexnow] no urls", file=sys.stderr)
        return False
    # Dedupe preserving order
    seen = set()
    clean = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            clean.append(u)
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": clean,
    }
    body = json.dumps(payload).encode()
    req = Request(ENDPOINT, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Host", "api.indexnow.org")
    try:
        with urlopen(req, timeout=15) as resp:
            code = resp.getcode()
            text = resp.read().decode("utf-8", errors="replace")[:300]
    except HTTPError as e:
        code = e.code
        text = e.read().decode("utf-8", errors="replace")[:300]
    except Exception as e:
        print(f"[indexnow] transport error: {e}", file=sys.stderr)
        return False

    # Per spec: 200 = URLs received, 202 = accepted pending, 400 = bad request,
    # 403 = key not valid (file missing/wrong), 422 = URL issues, 429 = too many.
    print(f"[indexnow] HTTP {code} · {len(clean)} urls · body={text!r}")
    return code in (200, 202)


def urls_for_day(day_num: int) -> list[str]:
    payload = json.loads(DAYS_JSON.read_text(encoding="utf-8"))
    d = next((d for d in payload["days"] if d["dayNumber"] == day_num), None)
    if not d:
        print(f"[indexnow] Day {day_num} not found", file=sys.stderr)
        return []
    return [
        f"https://{HOST}/days",
        f"https://{HOST}/days#{d['slug']}",
        f"https://{HOST}/data/days.rss",
        f"https://{HOST}/sitemap.xml",
    ]


def urls_all_days() -> list[str]:
    payload = json.loads(DAYS_JSON.read_text(encoding="utf-8"))
    base = [
        f"https://{HOST}/days",
        f"https://{HOST}/data/days.rss",
        f"https://{HOST}/sitemap.xml",
        f"https://{HOST}/",
    ]
    anchors = [f"https://{HOST}/days#{d['slug']}"
               for d in sorted(payload["days"], key=lambda x: x["dayNumber"])]
    return base + anchors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--day", type=int, help="Ping URLs for a specific Day number")
    g.add_argument("--urls", nargs="+", help="Ping arbitrary URLs")
    g.add_argument("--all-days", action="store_true",
                   help="Ping /days index + RSS + sitemap + every Day anchor")
    args = ap.parse_args()

    if args.day:
        urls = urls_for_day(args.day)
    elif args.urls:
        urls = args.urls
    else:
        urls = urls_all_days()

    ok = ping(urls)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
