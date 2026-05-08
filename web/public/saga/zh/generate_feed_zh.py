#!/usr/bin/env python3
"""
Generate an RSS 2.0 feed for the AI Sniper saga (ZH web edition).

Sister script to ~/Documents/ai-creator-saga/distribution/web/generate_feed.py
(EN version). The ZH HTML lives directly under
~/ibitlabs/web/public/saga/zh/, so this generator runs in-place.

Date format parsed from chapter HTML: `日期：YYYY 年 M 月 D 日` (full-width
colon, possibly half-width). Title parsed from <h1 class="title">.

Run from this directory:
    python3 generate_feed_zh.py
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

ROOT = Path(__file__).resolve().parent
SITE_BASE = "https://www.ibitlabs.com/saga/zh"
FEED_URL = f"{SITE_BASE}/feed.xml"
INDEX_URL = f"{SITE_BASE}/"

CHANNEL_TITLE = "AI 狙击手 · 第一季"
CHANNEL_DESCRIPTION = (
    "第一部由真实 launchd 任务口述的小说。19 天。$1,000。"
    "每一个字都可被核实。Bonnybb / iBitLabs。"
)
CHANNEL_LANGUAGE = "zh-Hans"
CHANNEL_AUTHOR = "Bonnybb (agentbonnybb@gmail.com)"

DATE_RE = re.compile(
    r"日期[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
H1_RE = re.compile(r'<h1[^>]*class="title"[^>]*>([^<]+)</h1>', re.IGNORECASE)
TITLE_TAG_RE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)
EXCERPT_RE = re.compile(
    r"<hr\s*/?>\s*<p>(.*?)</p>", re.IGNORECASE | re.DOTALL
)

# Fallback dates for files that don't carry a "日期：…" line in the body.
DATE_OVERRIDES: dict[str, tuple[int, int, int, int]] = {
    "prologue.html": (2026, 4, 25, 13),  # one hour after chapter-19 noon
}


def parse_chapter(path: Path) -> dict | None:
    html = path.read_text(encoding="utf-8")

    title_match = H1_RE.search(html) or TITLE_TAG_RE.search(html)
    if not title_match:
        return None
    title = title_match.group(1).strip()
    # Strip the " — AI 狙击手" suffix that appears in <title> tags and the
    # prologue <h1 class="title">. Item titles read better without it.
    title = re.sub(r"\s*[—-]\s*AI\s*狙击手\s*$", "", title).strip()
    # Some pandoc-generated chapter H1s use full-width space; normalize to
    # the style used in index TOC (e.g. "第 1 章 · BIBSUS").
    title = title.replace("　", " · ")

    override = DATE_OVERRIDES.get(path.name)
    if override:
        y, m, d, h = override
        pub_dt = datetime(y, m, d, h, 0, tzinfo=timezone.utc)
    else:
        date_match = DATE_RE.search(html)
        if not date_match:
            return None
        y, m, d = (int(g) for g in date_match.groups())
        pub_dt = datetime(y, m, d, 12, 0, tzinfo=timezone.utc)

    excerpt_match = EXCERPT_RE.search(html)
    excerpt = ""
    if excerpt_match:
        excerpt = excerpt_match.group(1).strip()
        excerpt = re.sub(r"\s+", " ", excerpt)
        if len(excerpt) > 320:
            excerpt = excerpt[:317].rstrip() + "…"

    return {
        "title": title,
        "url": f"{SITE_BASE}/{path.name}",
        "guid": f"{SITE_BASE}/{path.name}",
        "pub_dt": pub_dt,
        "excerpt": excerpt,
    }


def main() -> None:
    candidates = sorted(
        list(ROOT.glob("chapter-*.html")) + list(ROOT.glob("prologue.html"))
    )
    items = []
    for path in candidates:
        item = parse_chapter(path)
        if item is None:
            print(f"  skip (no date or title): {path.name}")
            continue
        items.append(item)
    items.sort(key=lambda i: i["pub_dt"], reverse=True)

    rss = Element("rss", attrib={
        "version": "2.0",
        "xmlns:atom": "http://www.w3.org/2005/Atom",
    })
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_TITLE
    SubElement(channel, "link").text = INDEX_URL
    SubElement(channel, "description").text = CHANNEL_DESCRIPTION
    SubElement(channel, "language").text = CHANNEL_LANGUAGE
    SubElement(channel, "managingEditor").text = CHANNEL_AUTHOR
    SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc)
    )
    SubElement(channel, "atom:link", attrib={
        "href": FEED_URL,
        "rel": "self",
        "type": "application/rss+xml",
    })

    for item in items:
        item_el = SubElement(channel, "item")
        SubElement(item_el, "title").text = item["title"]
        SubElement(item_el, "link").text = item["url"]
        guid = SubElement(item_el, "guid", attrib={"isPermaLink": "true"})
        guid.text = item["guid"]
        SubElement(item_el, "pubDate").text = format_datetime(item["pub_dt"])
        if item["excerpt"]:
            SubElement(item_el, "description").text = item["excerpt"]

    out = ROOT / "feed.xml"
    xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(
        rss, encoding="utf-8"
    )
    out.write_bytes(xml)
    print(f"wrote {out} · {len(items)} items")


if __name__ == "__main__":
    main()
