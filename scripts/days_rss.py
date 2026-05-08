#!/usr/bin/env python3
"""Generate web/public/data/days.rss from web/public/data/days.json.

Runs as part of the daily days-generator pipeline (and once for backfill).
"""
import html as _html
import json
import re
from pathlib import Path
from datetime import datetime, timezone

DAYS_JSON = Path("/Users/bonnyagent/ibitlabs/web/public/data/days.json")
RSS_OUT = Path("/Users/bonnyagent/ibitlabs/web/public/data/days.rss")
SITE = "https://www.ibitlabs.com"


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return _html.unescape(s).strip()


def main():
    payload = json.loads(DAYS_JSON.read_text(encoding="utf-8"))
    days = sorted(payload["days"], key=lambda d: d["dayNumber"], reverse=True)
    now_rfc822 = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    items = []
    for d in days:
        en = d.get("i18n", {}).get("en", {})
        title = en.get("title", f"Day {d['dayNumber']}")
        tagline = en.get("tagline", "")
        body_html = en.get("body", "")
        slug = d.get("slug", "")
        date = d.get("date", "")
        # RFC 822 pub date at noon UTC of that day
        try:
            dt = datetime.strptime(date, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
            pub = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            pub = now_rfc822
        url = f"{SITE}/days#{slug}"
        item = f"""    <item>
      <title>{_html.escape(title)}</title>
      <link>{url}</link>
      <guid isPermaLink="true">{url}</guid>
      <pubDate>{pub}</pubDate>
      <description>{_html.escape(tagline)}</description>
      <content:encoded><![CDATA[{body_html}]]></content:encoded>
      <dc:creator>Bonnybb</dc:creator>
    </item>"""
        items.append(item)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>iBitLabs — Days</title>
    <link>{SITE}/days</link>
    <atom:link href="{SITE}/data/days.rss" rel="self" type="application/rss+xml"/>
    <description>A daily serialized dual-POV chronicle of the iBitLabs live-trading experiment. Two alternating first-person protagonists — SHE (Bonnybb) and IT (SNIPER) — with real trades, real timestamps, real PnL.</description>
    <language>en</language>
    <copyright>© 2026 iBitLabs</copyright>
    <lastBuildDate>{now_rfc822}</lastBuildDate>
    <image>
      <url>{SITE}/favicon.png</url>
      <title>iBitLabs — Days</title>
      <link>{SITE}/days</link>
    </image>
{chr(10).join(items)}
  </channel>
</rss>
"""
    RSS_OUT.write_text(rss, encoding="utf-8")
    print(f"✓ wrote {RSS_OUT} ({len(days)} items)")


if __name__ == "__main__":
    main()
