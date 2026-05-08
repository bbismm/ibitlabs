#!/usr/bin/env python3
"""
days_broadcast.py — Broadcast a Day entry to Telegram (@ibitlabs_sniper)
and Twitter (@BonnyOuyang) in the format: tagline + pull quote + URL.

Reads web/public/data/days.json.
Reuses OAuth/token logic from /Users/bonnyagent/ibitlabs/twitter_poster.py.

Usage:
    python3 days_broadcast.py                    # today's Day N, EN, both channels
    python3 days_broadcast.py --day 17           # specific day
    python3 days_broadcast.py --day 17 --dry-run # preview only
    python3 days_broadcast.py --day 17 --lang zh # post ZH version
    python3 days_broadcast.py --day 17 --no-twitter
    python3 days_broadcast.py --day 17 --no-telegram
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

# Load .env so Twitter/Telegram creds are available
try:
    from dotenv import load_dotenv
    load_dotenv("/Users/bonnyagent/ibitlabs/.env")
except Exception:
    # Minimal .env loader fallback
    env_path = Path("/Users/bonnyagent/ibitlabs/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, "/Users/bonnyagent/ibitlabs")
try:
    from twitter_poster import _send_channel, _refresh_twitter_token
except Exception as e:
    print(f"[fatal] cannot import twitter_poster: {e}", file=sys.stderr)
    sys.exit(1)

import json as _json
from urllib.request import Request, urlopen

DAYS_JSON = Path("/Users/bonnyagent/ibitlabs/web/public/data/days.json")
DAY_1_DATE = dt.date(2026, 4, 7)
SITE = "https://www.ibitlabs.com"
TWEET_URL = "https://api.twitter.com/2/tweets"
TWITTER_MAX = 280

# Twitter counts CJK chars with weight 2. Treat non-ASCII as weight 2 for safety.
def tweet_weight(s: str) -> int:
    return sum(2 if ord(c) > 127 else 1 for c in s)


def day_number_for(date: dt.date) -> int:
    return (date - DAY_1_DATE).days + 1


def date_for_day(day_num: int) -> dt.date:
    return DAY_1_DATE + dt.timedelta(days=day_num - 1)


def load_day(target_day: int) -> dict | None:
    payload = json.loads(DAYS_JSON.read_text(encoding="utf-8"))
    for d in payload["days"]:
        if d["dayNumber"] == target_day:
            return d
    return None


def format_message(day: dict, lang: str, for_twitter: bool) -> str:
    i = day.get("i18n", {}).get(lang) or day.get("i18n", {}).get("en") or {}
    title = i.get("title", f"Day {day['dayNumber']}")
    tagline = i.get("tagline", "")
    quote = i.get("pullQuote", "")
    url = f"{SITE}/days#{day['slug']}"

    # Base message (uniform for TG and Twitter)
    parts = [title]
    if tagline:
        parts.append("")
        parts.append(tagline)
    if quote:
        parts.append("")
        parts.append(f"「{quote}」")
    parts.append("")
    parts.append(url)
    msg = "\n".join(parts)

    if not for_twitter:
        return msg

    # Twitter: shrink if over weight limit. URL shortened by Twitter to 23.
    # Compute weight replacing URL with 23 ASCII chars.
    def weight_for_tweet(m: str) -> int:
        return tweet_weight(m.replace(url, "x" * 23))

    if weight_for_tweet(msg) <= TWITTER_MAX:
        return msg

    # Progressive shrink: truncate quote first
    if quote:
        # Keep tagline intact, shrink quote
        max_q_weight = TWITTER_MAX - weight_for_tweet(msg.replace(f"「{quote}」", "「」"))
        # max_q_weight is headroom — trim until fits
        trimmed = quote
        while trimmed and tweet_weight(trimmed) > max_q_weight - 1:
            trimmed = trimmed[:-1]
        if trimmed and len(trimmed) < len(quote):
            trimmed = trimmed.rstrip(".,!?;:—- ") + "…"
        parts = [title, "", tagline, "", f"「{trimmed}」", "", url] if tagline else [title, "", f"「{trimmed}」", "", url]
        msg = "\n".join(parts)
        if weight_for_tweet(msg) <= TWITTER_MAX:
            return msg

    # Still over — drop the quote entirely
    parts = [title, "", tagline, "", url] if tagline else [title, "", url]
    msg = "\n".join(parts)
    if weight_for_tweet(msg) <= TWITTER_MAX:
        return msg

    # Last resort — truncate tagline
    trimmed_tag = tagline
    while trimmed_tag and weight_for_tweet("\n".join([title, "", trimmed_tag, "", url])) > TWITTER_MAX - 1:
        trimmed_tag = trimmed_tag[:-1]
    return "\n".join([title, "", trimmed_tag.rstrip() + "…", "", url])


def send_telegram(msg: str, dry: bool) -> bool:
    if dry:
        print("── [DRY-RUN: TELEGRAM] ──")
        print(msg)
        print("────────────────────────")
        return True
    # Send plain (no Markdown) so brackets and punctuation aren't parsed
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("[tg] no TELEGRAM_BOT_TOKEN", file=sys.stderr)
        return False
    try:
        payload = _json.dumps({
            "chat_id": "@ibitlabs_sniper",
            "text": msg,
            "disable_web_page_preview": False,
        }).encode()
        req = Request(f"https://api.telegram.org/bot{token}/sendMessage",
                      data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
            if data.get("ok"):
                print(f"[tg] sent: msg_id={data['result']['message_id']}")
                return True
            print(f"[tg] error: {data}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[tg] failed: {e}", file=sys.stderr)
        return False


import html as _html_lib
import re


def _strip_html(s: str) -> str:
    """Convert HTML fragment to plain text, preserving paragraph breaks."""
    s = re.sub(r"<hr\s*/?>", "\n", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>\s*", "\n\n", s)
    s = re.sub(r"<p[^>]*>", "", s)
    s = re.sub(r"</?(strong|em|b|i|u|code|blockquote)[^>]*>", "", s)
    s = _html_lib.unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def parse_body_sections(html: str) -> list[tuple[str, str]]:
    """Return list of (role, text). role in {her, it, button}. Tagline NOT included
    (it's already in the root tweet)."""
    sections: list[tuple[str, str]] = []
    # Cut everything before first h3 (skips tagline + metadata line + first <hr>)
    pat = r'<h3\s+class="pov-header\s+pov-(her|it|button)"[^>]*>[^<]*</h3>(.*?)(?=<h3\s+class="pov-header|<hr\s*/?>|$)'
    for m in re.finditer(pat, html, flags=re.S):
        role = m.group(1)
        text = _strip_html(m.group(2))
        if text:
            sections.append((role, text))
    return sections


def chunk_section(text: str, max_weight: int = 270) -> list[str]:
    """Chunk text into tweet-sized pieces, respecting paragraph boundaries
    first, then sentence boundaries."""
    out: list[str] = []
    current = ""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    for para in paras:
        cand = f"{current}\n\n{para}" if current else para
        if tweet_weight(cand) <= max_weight:
            current = cand
            continue
        # flush current
        if current:
            out.append(current)
            current = ""
        # paragraph alone fits?
        if tweet_weight(para) <= max_weight:
            current = para
            continue
        # split by sentence
        sents = re.split(r"(?<=[.!?。！？])\s+", para)
        for s in sents:
            s = s.strip()
            if not s:
                continue
            cand2 = f"{current} {s}".strip() if current else s
            if tweet_weight(cand2) <= max_weight:
                current = cand2
            else:
                if current:
                    out.append(current)
                # sentence itself too big — hard split at char weight
                while tweet_weight(s) > max_weight:
                    cut = max_weight
                    while cut > 0 and tweet_weight(s[:cut]) > max_weight:
                        cut -= 1
                    out.append(s[:cut].rstrip() + "…")
                    s = s[cut:].lstrip()
                current = s
    if current:
        out.append(current)
    return out


def build_thread_tweets(day: dict, lang: str) -> tuple[str, list[str]]:
    """Return (root_msg, [reply_1, reply_2, ...])."""
    i = day.get("i18n", {}).get(lang) or day.get("i18n", {}).get("en") or {}
    body_html = i.get("body", "")
    sections = parse_body_sections(body_html)

    reply_tweets: list[str] = []
    section_count = sum(1 for r, _ in sections if r != "button")
    # Count will be used as "N of total" suffix — total = section_count + 1 button
    total = len(sections)

    idx = 0
    for role, text in sections:
        idx += 1
        label = {"her": "SHE", "it": "IT", "button": "TOMORROW"}[role]
        if lang == "zh":
            label = {"her": "她", "it": "它", "button": "预告"}[role]
        # Header for this section
        header = f"—— {label} ——"
        chunks = chunk_section(text, max_weight=270 - tweet_weight(header) - 2)
        for j, chunk in enumerate(chunks):
            if j == 0:
                msg = f"{header}\n\n{chunk}"
            else:
                msg = chunk
            reply_tweets.append(msg)

    # Root tweet is the same format as the single-tweet version
    root = format_message(day, lang, for_twitter=True)
    return root, reply_tweets


def _tweepy_client():
    import tweepy
    return tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )


def post_thread(root_msg: str, reply_tweets: list[str],
                dry: bool = False,
                existing_root_id: str | None = None) -> dict:
    """Post a Twitter thread. If existing_root_id is provided, reply-chain to
    that tweet (don't post a new root)."""
    if dry:
        print("── [DRY-RUN: TWITTER THREAD @BonnyOuyang] ──")
        if existing_root_id:
            print(f"(extending existing root {existing_root_id})")
        else:
            print("── ROOT ──")
            print(root_msg)
        for i, t in enumerate(reply_tweets, 1):
            print(f"── REPLY {i}/{len(reply_tweets)} (weight {tweet_weight(t)}) ──")
            print(t)
        print("─────────────────────────────────────────────")
        return {"ok": True, "tweets": len(reply_tweets) + (0 if existing_root_id else 1)}

    try:
        client = _tweepy_client()
    except Exception as e:
        print(f"[tw] client init failed: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}

    ids: list[str] = []
    if existing_root_id:
        prev_id = existing_root_id
    else:
        try:
            r = client.create_tweet(text=root_msg)
            prev_id = getattr(r, "data", {}).get("id")
            if not prev_id:
                print(f"[tw] root post no id: {r}", file=sys.stderr)
                return {"ok": False, "error": "no_id_from_root"}
            ids.append(prev_id)
            print(f"[tw] root: https://x.com/BonnyOuyang/status/{prev_id}")
        except Exception as e:
            print(f"[tw] root post failed: {e}", file=sys.stderr)
            return {"ok": False, "error": str(e)}

    for i, text in enumerate(reply_tweets, 1):
        try:
            r = client.create_tweet(text=text, in_reply_to_tweet_id=prev_id)
            new_id = getattr(r, "data", {}).get("id")
            if not new_id:
                print(f"[tw] reply {i} no id", file=sys.stderr)
                break
            ids.append(new_id)
            prev_id = new_id
            print(f"[tw] reply {i}/{len(reply_tweets)}: https://x.com/BonnyOuyang/status/{new_id}")
        except Exception as e:
            print(f"[tw] reply {i} failed: {e}", file=sys.stderr)
            return {"ok": False, "error": str(e), "ids_posted": ids}
    return {"ok": True, "ids": ids}


def send_twitter(msg: str, dry: bool) -> bool:
    if dry:
        import re
        url_weight_replaced = re.sub(r"https?://\S+", "x" * 23, msg)
        print("── [DRY-RUN: TWITTER @BonnyOuyang] ──")
        print(msg)
        print(f"weight: {tweet_weight(url_weight_replaced)} / {TWITTER_MAX}")
        print("─────────────────────────────────────")
        return True

    # Primary: OAuth 1.0a via tweepy (non-expiring tokens).
    # Fallback: OAuth 2.0 Bearer (auto-refresh) if 1.0a fails.
    try:
        import tweepy
        api_key = os.environ.get("TWITTER_API_KEY", "")
        api_secret = os.environ.get("TWITTER_API_SECRET", "")
        access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
        access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")
        if all([api_key, api_secret, access_token, access_secret]):
            client = tweepy.Client(
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_secret,
            )
            resp = client.create_tweet(text=msg)
            tid = getattr(resp, "data", {}).get("id") if resp else None
            if tid:
                print(f"[tw] sent (OAuth1): https://x.com/BonnyOuyang/status/{tid}")
                return True
            print(f"[tw] OAuth1 unexpected response: {resp}", file=sys.stderr)
    except Exception as e:
        print(f"[tw] OAuth1 failed: {e} — falling back to OAuth2", file=sys.stderr)

    # Fallback: OAuth 2.0
    token = os.environ.get("TWITTER_OAUTH2_TOKEN", "")
    if not token:
        print("[tw] no OAuth2 token either", file=sys.stderr)
        return False

    for attempt in range(2):
        try:
            body = _json.dumps({"text": msg}).encode()
            req = Request(TWEET_URL, data=body, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=20) as resp:
                result = _json.loads(resp.read())
                tid = result.get("data", {}).get("id")
                if tid:
                    print(f"[tw] sent (OAuth2 fallback): https://x.com/BonnyOuyang/status/{tid}")
                    return True
                print(f"[tw] OAuth2 unexpected response: {result}", file=sys.stderr)
                return False
        except Exception as e:
            err = str(e)
            if "401" in err and attempt == 0:
                print("[tw] OAuth2 401 — refreshing…")
                new = _refresh_twitter_token()
                if new:
                    token = new
                    continue
            print(f"[tw] OAuth2 failed: {e}", file=sys.stderr)
            return False
    return False


QUEUE_FILE = Path("/Users/bonnyagent/ibitlabs/web/public/data/days_broadcast_queue.json")


def replay_next() -> dict:
    """Post the next un-broadcast Day from the queue file. Updates state in-place.
    Channels and language come from the queue file."""
    if not QUEUE_FILE.exists():
        return {"status": "no_queue_file", "path": str(QUEUE_FILE)}
    q = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    remaining = q.get("remaining", [])
    if not remaining:
        return {"status": "queue_empty"}

    target = remaining[0]
    channels = q.get("channels", ["twitter"])
    lang = q.get("lang", "en")

    day = load_day(target)
    if not day:
        # Day doesn't exist yet — skip it (stays at head of queue for retry)
        return {"status": "day_not_found", "day": target}

    results = {}
    if "telegram" in channels:
        tg_msg = format_message(day, lang, for_twitter=False)
        results["telegram"] = send_telegram(tg_msg, dry=False)
    if "twitter" in channels:
        # Thread post: root = tagline+quote+URL teaser, replies = full body sections
        root, replies = build_thread_tweets(day, lang)
        r = post_thread(root, replies, dry=False)
        results["twitter"] = bool(r.get("ok"))

    ok = all(results.values()) if results else False
    # Rotate queue only if any configured channel succeeded
    if ok:
        q["remaining"] = remaining[1:]
        q["completed"] = q.get("completed", []) + [target]
    q["last_run"] = dt.datetime.now().astimezone().isoformat()
    q["last_result"] = {"day": target, "channels": results, "ok": ok}
    QUEUE_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return {"status": "ok" if ok else "partial_or_fail",
            "day": target, "channels": results,
            "remaining_after": q["remaining"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--day", type=int, help="Day number")
    group.add_argument("--date", type=str, help="YYYY-MM-DD")
    group.add_argument("--replay-next", action="store_true",
                       help="Post the next Day from the backfill queue (state in days_broadcast_queue.json)")
    ap.add_argument("--lang", choices=["en", "zh"], default="en")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-twitter", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--thread", action="store_true",
                    help="Post as Twitter thread (root teaser + body reply chain). Default for --replay-next.")
    ap.add_argument("--extend-tweet-id", type=str, default=None,
                    help="Extend an existing tweet with body reply-chain only (no new root).")
    args = ap.parse_args()

    if args.replay_next:
        result = replay_next()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") in ("no_queue_file", "partial_or_fail", "day_not_found"):
            sys.exit(1)
        return

    if args.date:
        target = day_number_for(dt.date.fromisoformat(args.date))
    elif args.day:
        target = args.day
    else:
        target = day_number_for(dt.date.today())

    day = load_day(target)
    if not day:
        print(f"[fatal] Day {target} not found in {DAYS_JSON}", file=sys.stderr)
        sys.exit(2)

    i = day.get("i18n", {}).get(args.lang, {})
    title = i.get("title", f"Day {target}")
    slug = day.get("slug", "")
    print(f"── Broadcasting Day {target} ── lang={args.lang} ── {title} ── {slug}")

    tg_msg = format_message(day, args.lang, for_twitter=False)
    tw_msg = format_message(day, args.lang, for_twitter=True)

    results = {}
    if not args.no_telegram:
        results["telegram"] = send_telegram(tg_msg, args.dry_run)
    if not args.no_twitter:
        if args.thread or args.extend_tweet_id:
            root, replies = build_thread_tweets(day, args.lang)
            r = post_thread(root, replies, dry=args.dry_run,
                            existing_root_id=args.extend_tweet_id)
            results["twitter"] = bool(r.get("ok"))
        else:
            results["twitter"] = send_twitter(tw_msg, args.dry_run)

    print(f"[result] {results}")
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
