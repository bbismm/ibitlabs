#!/usr/bin/env python3
"""
iBitLabs — Twitter/X Auto-Poster
==================================
Posts trade reports and content to @BonnyOuyang automatically.

Twitter Free tier allows 1,500 tweets/month (posting only).
Uses tweepy if available, falls back to manual OAuth1 with stdlib.

Required env vars (already in your .env):
  TWITTER_API_KEY, TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET

Usage:
  # Post today's daily report
  python3 twitter_auto_poster.py --daily 2026-04-03

  # Post weekly report
  python3 twitter_auto_poster.py --weekly 2026-W15

  # Post custom text
  python3 twitter_auto_poster.py --text "Hello from iBitLabs!"

  # Post with image
  python3 twitter_auto_poster.py --text "Daily chart" --image reports/chart_2026-04-03.png

  # Dry run (don't actually post)
  python3 twitter_auto_poster.py --daily 2026-04-03 --dry-run
"""

import os
import sys
import json
import time
import hmac
import hashlib
import base64
import argparse
import logging
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path
from uuid import uuid4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------- CONFIG ----------
BASE_DIR = Path(__file__).parent.parent
REPORT_DIR = BASE_DIR / "reports"

# Load from .env file if env vars not set
def load_env():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip()
                    if val and not os.environ.get(key):
                        os.environ[key] = val

load_env()

API_KEY = os.environ.get("TWITTER_API_KEY", "")
API_SECRET = os.environ.get("TWITTER_API_SECRET", "")
ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN", "")
ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET", "")

TWEET_URL = "https://api.twitter.com/2/tweets"
UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"


# ---------- OAUTH 1.0a SIGNING (stdlib only) ----------

def _percent_encode(s: str) -> str:
    return quote(str(s), safe="")


def _oauth_signature(method: str, url: str, params: dict,
                     consumer_secret: str, token_secret: str) -> str:
    """Generate OAuth 1.0a HMAC-SHA1 signature."""
    sorted_params = urlencode(sorted(params.items()))
    base_string = f"{method.upper()}&{_percent_encode(url)}&{_percent_encode(sorted_params)}"
    signing_key = f"{_percent_encode(consumer_secret)}&{_percent_encode(token_secret)}"
    signature = hmac.new(
        signing_key.encode(), base_string.encode(), hashlib.sha1
    ).digest()
    return base64.b64encode(signature).decode()


def _oauth_header(method: str, url: str, extra_params: dict = None) -> str:
    """Build OAuth Authorization header."""
    oauth_params = {
        "oauth_consumer_key": API_KEY,
        "oauth_nonce": uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": ACCESS_TOKEN,
        "oauth_version": "1.0",
    }

    # Combine all params for signature
    all_params = {**oauth_params}
    if extra_params:
        all_params.update(extra_params)

    signature = _oauth_signature(method, url, all_params, API_SECRET, ACCESS_SECRET)
    oauth_params["oauth_signature"] = signature

    header_parts = [f'{_percent_encode(k)}="{_percent_encode(v)}"'
                    for k, v in sorted(oauth_params.items())]
    return "OAuth " + ", ".join(header_parts)


# ---------- TWITTER API ----------

def upload_image(image_path: Path):
    """Upload image to Twitter and return media_id string."""
    if not image_path.exists():
        logger.warning(f"Image not found: {image_path}")
        return None

    # Try tweepy first (handles multipart cleanly)
    try:
        import tweepy
        auth = tweepy.OAuth1UserHandler(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET)
        api = tweepy.API(auth)
        media = api.media_upload(str(image_path))
        logger.info(f"✅ Image uploaded via tweepy: {media.media_id_string}")
        return media.media_id_string
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"tweepy upload failed: {e}")

    # Fallback: manual multipart upload via urllib
    try:
        boundary = f"----WebKitFormBoundary{uuid4().hex[:16]}"
        with open(image_path, "rb") as f:
            image_data = f.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="media_data"\r\n\r\n'
            f"{base64.b64encode(image_data).decode()}\r\n"
            f"--{boundary}--\r\n"
        ).encode()

        auth_header = _oauth_header("POST", UPLOAD_URL)
        req = Request(UPLOAD_URL, data=body, method="POST")
        req.add_header("Authorization", auth_header)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            media_id = str(result["media_id"])
            logger.info(f"✅ Image uploaded via stdlib: {media_id}")
            return media_id
    except Exception as e:
        logger.error(f"❌ Image upload failed: {e}")
        return None


def post_tweet(text: str, media_id: str = None, dry_run: bool = False) -> bool:
    """Post a tweet. Returns True on success."""
    if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_SECRET]):
        logger.error("❌ Twitter API keys not configured. Check .env")
        return False

    if dry_run:
        logger.info(f"🏷️  [DRY RUN] Would tweet ({len(text)} chars):\n{text}")
        if media_id:
            logger.info(f"   With media: {media_id}")
        return True

    # Truncate to 280 chars
    if len(text) > 280:
        text = text[:277] + "..."
        logger.warning(f"⚠️  Tweet truncated to 280 chars")

    payload = {"text": text}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}

    # Try tweepy first
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=API_KEY, consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN, access_token_secret=ACCESS_SECRET
        )
        resp = client.create_tweet(text=text,
                                   media_ids=[media_id] if media_id else None)
        tweet_id = resp.data["id"]
        logger.info(f"✅ Posted via tweepy: https://x.com/BonnyOuyang/status/{tweet_id}")
        return True
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"tweepy post failed: {e}, trying stdlib...")

    # Fallback: manual v2 API call
    try:
        body = json.dumps(payload).encode()
        auth_header = _oauth_header("POST", TWEET_URL)

        req = Request(TWEET_URL, data=body, method="POST")
        req.add_header("Authorization", auth_header)
        req.add_header("Content-Type", "application/json")

        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            tweet_id = result["data"]["id"]
            logger.info(f"✅ Posted via stdlib: https://x.com/BonnyOuyang/status/{tweet_id}")
            return True
    except HTTPError as e:
        error_body = e.read().decode()
        logger.error(f"❌ Twitter API error {e.code}: {error_body}")

        if e.code == 403:
            logger.error(
                "   → 403 Forbidden. Possible causes:\n"
                "   1. App permissions: Go to developer.twitter.com → Your App → Settings\n"
                "      → App permissions → Set to 'Read and Write'\n"
                "   2. Regenerate Access Token AFTER changing permissions\n"
                "   3. Free tier: Verify your app is on the Free tier (allows posting)"
            )
        elif e.code == 429:
            logger.error("   → Rate limited. Free tier: 1,500 tweets/month")
        return False
    except Exception as e:
        logger.error(f"❌ Tweet failed: {e}")
        return False


def post_thread(tweets: list[str], dry_run: bool = False) -> bool:
    """Post a Twitter thread (reply chain)."""
    if not tweets:
        return False

    if dry_run:
        for i, t in enumerate(tweets):
            logger.info(f"🏷️  [DRY RUN] Thread [{i+1}/{len(tweets)}] ({len(t)} chars):\n{t}\n")
        return True

    # Post first tweet
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=API_KEY, consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN, access_token_secret=ACCESS_SECRET
        )
        resp = client.create_tweet(text=tweets[0])
        prev_id = resp.data["id"]
        logger.info(f"✅ Thread [1/{len(tweets)}]: https://x.com/BonnyOuyang/status/{prev_id}")

        for i, tweet_text in enumerate(tweets[1:], 2):
            time.sleep(2)  # Avoid rate limits
            resp = client.create_tweet(text=tweet_text, in_reply_to_tweet_id=prev_id)
            prev_id = resp.data["id"]
            logger.info(f"✅ Thread [{i}/{len(tweets)}]: https://x.com/BonnyOuyang/status/{prev_id}")
        return True
    except ImportError:
        logger.error("❌ Thread posting requires tweepy. pip3 install tweepy")
        # Fallback: just post the first tweet
        return post_tweet(tweets[0])
    except Exception as e:
        logger.error(f"❌ Thread failed: {e}")
        return False


# ---------- REPORT LOADING ----------

def load_daily_social(target_date: str):
    """Load Twitter copy from daily social file."""
    social_file = REPORT_DIR / f"social_{target_date}.txt"
    if not social_file.exists():
        logger.error(f"No social copy found: {social_file}")
        logger.info(f"Run daily_report_generator.py --date {target_date} first")
        return None

    with open(social_file) as f:
        content = f.read()

    # Extract Twitter section
    if "--- TWITTER ---" in content:
        start = content.index("--- TWITTER ---") + len("--- TWITTER ---\n")
        return content[start:].strip()

    return None


def load_weekly_social(week_label: str):
    """Load Twitter copy from weekly social file."""
    social_file = REPORT_DIR / f"weekly_social_{week_label}.txt"
    if not social_file.exists():
        logger.error(f"No weekly social copy: {social_file}")
        return None

    with open(social_file) as f:
        content = f.read()

    if "--- TWITTER ---" in content:
        start = content.index("--- TWITTER ---") + len("--- TWITTER ---\n")
        return content[start:].strip()

    return None


# ---------- MAIN ----------

def main():
    parser = argparse.ArgumentParser(description="iBitLabs Twitter Auto-Poster")
    parser.add_argument("--daily", metavar="DATE", help="Post daily report for YYYY-MM-DD")
    parser.add_argument("--weekly", metavar="WEEK", help="Post weekly report for YYYY-WNN")
    parser.add_argument("--text", help="Post custom text")
    parser.add_argument("--image", help="Attach image to tweet")
    parser.add_argument("--thread", nargs="+", help="Post a thread (multiple tweets)")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually post")
    args = parser.parse_args()

    media_id = None

    if args.daily:
        text = load_daily_social(args.daily)
        if not text:
            sys.exit(1)
        # Try to attach chart
        chart = REPORT_DIR / f"chart_{args.daily}.png"
        if chart.exists() and not args.dry_run:
            media_id = upload_image(chart)
        elif chart.exists():
            logger.info(f"🏷️  [DRY RUN] Would attach: {chart}")
        post_tweet(text, media_id=media_id, dry_run=args.dry_run)

    elif args.weekly:
        text = load_weekly_social(args.weekly)
        if not text:
            sys.exit(1)
        chart = REPORT_DIR / f"weekly_{args.weekly}.png"
        if chart.exists() and not args.dry_run:
            media_id = upload_image(chart)
        post_tweet(text, media_id=media_id, dry_run=args.dry_run)

    elif args.thread:
        post_thread(args.thread, dry_run=args.dry_run)

    elif args.text:
        if args.image and not args.dry_run:
            media_id = upload_image(Path(args.image))
        post_tweet(args.text, media_id=media_id, dry_run=args.dry_run)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
