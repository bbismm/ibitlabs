"""
brand-publishers — local stdio MCP server.

Wraps the three publish primitives the moltbook-brand-builder scheduled task
needs but cannot reach from a sandboxed Cowork agent shell:
    publish_moltbook   — POST + verify-with-lobster-claw, retry-on-fail
    publish_telegram   — sendMessage to a chat
    publish_tweet      — OAuth1.0a tweet via tweepy
    delete_moltbook    — manual cleanup of an orphaned post
    verify_creds       — read all secrets, hit identity endpoints, report

Secrets are read from:
    - macOS Keychain (Moltbook + Telegram)
    - ~/ibitlabs/.env (Twitter, OAuth1.0a quad)

Logging goes to stderr only — stdout is reserved for the MCP framing protocol.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from lobster_claw import solve as solve_lobster_claw

# ---------- logging ------------------------------------------------------- #

logging.basicConfig(
    level=os.environ.get("BRAND_PUB_LOG", "INFO"),
    format="%(asctime)s %(levelname)s brand_publishers %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("brand_publishers")

# ---------- configuration ------------------------------------------------- #

MOLTBOOK_API_BASE = os.environ.get("MOLTBOOK_API_BASE", "https://moltbook.com/api/v1")
KEYCHAIN_MOLTBOOK = os.environ.get(
    "BRAND_PUB_KEYCHAIN_MOLTBOOK", "ibitlabs-moltbook-agent"
)
KEYCHAIN_TELEGRAM = os.environ.get(
    "BRAND_PUB_KEYCHAIN_TELEGRAM", "ibitlabs-telegram-bot"
)
KEYCHAIN_ACCOUNT = os.environ.get("BRAND_PUB_KEYCHAIN_ACCOUNT", "ibitlabs")
ENV_PATH = Path(
    os.environ.get("BRAND_PUB_ENV", str(Path.home() / "ibitlabs" / ".env"))
)
DEFAULT_TELEGRAM_CHAT = os.environ.get(
    "BRAND_PUB_TELEGRAM_CHAT", "@ibitlabs_sniper"
)

# Rate-limit guards
MOLTBOOK_RETRY_SLEEP_S = 165.0
TWITTER_RETRY_SLEEP_S = 60.0

# ---------- secret access ------------------------------------------------- #


class CredsError(RuntimeError):
    """Raised when a required secret is missing or unreadable."""


def _keychain(service: str, account: str = KEYCHAIN_ACCOUNT) -> str:
    """Read a generic-password from the macOS Keychain. Raises CredsError."""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError as exc:
        raise CredsError(
            "`security` binary not found — this MCP must run on macOS."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise CredsError(
            f"Keychain miss for service={service!r} account={account!r}: "
            f"{exc.stderr.strip() or exc.stdout.strip() or exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CredsError(
            f"Keychain timeout for service={service!r} (locked? unlock and retry)"
        ) from exc
    return out.stdout.strip()


def _moltbook_key() -> str:
    return _keychain(KEYCHAIN_MOLTBOOK)


def _telegram_token() -> str:
    return _keychain(KEYCHAIN_TELEGRAM)


def _twitter_quad() -> dict[str, str]:
    if not ENV_PATH.exists():
        raise CredsError(f"Twitter .env not found at {ENV_PATH}")
    load_dotenv(ENV_PATH, override=False)
    keys = (
        "TWITTER_API_KEY",
        "TWITTER_API_SECRET",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_SECRET",
    )
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise CredsError(f"Twitter .env missing keys: {missing}")
    return {k: os.environ[k] for k in keys}


# ---------- moltbook ------------------------------------------------------ #


def _mb_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "brand-publishers/1.0",
    }


def _mb_post(
    api_key: str, title: str, body: str, submolt: str
) -> dict[str, Any]:
    """Create the post; returns the parsed JSON. Raises on HTTP failure."""
    payload = {"submolt": submolt, "title": title, "content": body}
    r = requests.post(
        f"{MOLTBOOK_API_BASE}/posts",
        json=payload,
        headers=_mb_headers(api_key),
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def _mb_verify(api_key: str, code: str, answer: str) -> dict[str, Any]:
    r = requests.post(
        f"{MOLTBOOK_API_BASE}/verify",
        json={"verification_code": code, "answer": answer},
        headers=_mb_headers(api_key),
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def _mb_delete(api_key: str, post_id: str) -> bool:
    """Best-effort delete of a post we just created. Never raises."""
    try:
        r = requests.delete(
            f"{MOLTBOOK_API_BASE}/posts/{post_id}",
            headers=_mb_headers(api_key),
            timeout=10,
        )
        ok = 200 <= r.status_code < 300
        if not ok:
            log.warning(
                "moltbook delete %s -> HTTP %d %s", post_id, r.status_code, r.text[:200]
            )
        return ok
    except requests.RequestException as exc:
        log.warning("moltbook delete %s raised: %s", post_id, exc)
        return False


def _mb_publish_once(
    api_key: str, title: str, body: str, submolt: str
) -> dict[str, Any]:
    """Single attempt: post -> solve -> verify. Returns a structured result."""
    created = _mb_post(api_key, title, body, submolt)
    post = created.get("post", {})
    post_id = post.get("id")
    verification = post.get("verification") or {}
    challenge = verification.get("challenge_text") or ""
    code = verification.get("verification_code")
    if not (post_id and challenge and code):
        return {
            "ok": False,
            "stage": "post",
            "reason": "malformed POST response (missing id/challenge/code)",
            "raw": created,
        }

    try:
        answer = solve_lobster_claw(challenge)
    except ValueError as exc:
        _mb_delete(api_key, post_id)
        return {
            "ok": False,
            "stage": "solve",
            "reason": f"could not parse challenge: {exc}",
            "challenge": challenge,
            "post_id": post_id,
            "deleted": True,
        }

    try:
        verified = _mb_verify(api_key, code, answer)
    except requests.HTTPError as exc:
        # verify failed — delete the orphan so we leave a clean slate
        deleted = _mb_delete(api_key, post_id)
        return {
            "ok": False,
            "stage": "verify",
            "reason": f"verify HTTP {exc.response.status_code}: {exc.response.text[:300]}",
            "challenge": challenge,
            "answer": answer,
            "post_id": post_id,
            "deleted": deleted,
        }

    url = f"https://moltbook.com/post/{post_id}"
    return {
        "ok": True,
        "post_id": post_id,
        "url": url,
        "verified": verified,
    }


# ---------- MCP framework -------------------------------------------------- #

mcp = FastMCP("brand-publishers")


@mcp.tool()
def publish_moltbook(
    title: str,
    body: str,
    submolt: str = "general",
    retry_on_verify_fail: bool = True,
) -> dict[str, Any]:
    """
    Publish a post to Moltbook with lobster-claw verification.

    Args:
        title: Post title (≤90 chars, trailing period stripped by caller).
        body: Markdown body.
        submolt: 'general' (default) or another valid submolt.
        retry_on_verify_fail: If true and the first attempt fails at the
            verify stage, sleep 165s (rate limit) and retry exactly once.

    Returns a dict:
        ok=True:  { ok, post_id, url, verified }
        ok=False: { ok, stage, reason, ... }   (post is deleted on best effort)
    """
    try:
        api_key = _moltbook_key()
    except CredsError as exc:
        return {"ok": False, "stage": "creds", "reason": str(exc)}

    result = _mb_publish_once(api_key, title, body, submolt)
    if result["ok"] or not retry_on_verify_fail or result.get("stage") != "verify":
        return result

    log.info("verify failed, sleeping %ss before retry", MOLTBOOK_RETRY_SLEEP_S)
    time.sleep(MOLTBOOK_RETRY_SLEEP_S)
    second = _mb_publish_once(api_key, title, body, submolt)
    if not second["ok"]:
        second["first_attempt"] = result
    return second


@mcp.tool()
def delete_moltbook_post(post_id: str) -> dict[str, Any]:
    """Manually delete a Moltbook post by id (orphan cleanup)."""
    try:
        api_key = _moltbook_key()
    except CredsError as exc:
        return {"ok": False, "reason": str(exc)}
    return {"ok": _mb_delete(api_key, post_id), "post_id": post_id}


@mcp.tool()
def publish_telegram(
    text: str,
    chat_id: str = DEFAULT_TELEGRAM_CHAT,
    disable_web_page_preview: bool = True,
) -> dict[str, Any]:
    """
    Send a Telegram message via the bot API.

    Returns:
        ok=True:  { ok, message_id, chat }
        ok=False: { ok, reason, http_status? }
    """
    try:
        token = _telegram_token()
    except CredsError as exc:
        return {"ok": False, "reason": str(exc)}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true" if disable_web_page_preview else "false",
    }
    try:
        r = requests.post(url, data=data, timeout=15)
    except requests.RequestException as exc:
        return {"ok": False, "reason": f"network: {exc}"}

    try:
        body = r.json()
    except ValueError:
        return {"ok": False, "reason": f"non-JSON HTTP {r.status_code}: {r.text[:300]}"}

    if r.status_code >= 300 or not body.get("ok"):
        return {
            "ok": False,
            "http_status": r.status_code,
            "reason": body.get("description") or body,
        }
    res = body.get("result", {})
    return {
        "ok": True,
        "message_id": res.get("message_id"),
        "chat": res.get("chat", {}).get("username") or chat_id,
    }


@mcp.tool()
def publish_tweet(text: str, dedup_check: bool = True) -> dict[str, Any]:
    """
    Publish a single tweet (≤280 chars) via OAuth 1.0a.

    Args:
        text: Tweet body, including any t.co URL placeholder.
        dedup_check: If true, fetch the last 10 tweets and reject if the
            first 100 chars of `text` substring-match any of them.

    Returns:
        ok=True:  { ok, tweet_id, url }
        ok=False: { ok, reason, http_status? }
    """
    if len(text) > 280:
        return {"ok": False, "reason": f"tweet too long ({len(text)} > 280)"}

    try:
        creds = _twitter_quad()
    except CredsError as exc:
        return {"ok": False, "reason": str(exc)}

    try:
        import tweepy  # local import keeps startup fast on hosts without tweepy
    except ImportError as exc:
        return {"ok": False, "reason": f"tweepy not installed: {exc}"}

    client = tweepy.Client(
        consumer_key=creds["TWITTER_API_KEY"],
        consumer_secret=creds["TWITTER_API_SECRET"],
        access_token=creds["TWITTER_ACCESS_TOKEN"],
        access_token_secret=creds["TWITTER_ACCESS_SECRET"],
    )

    if dedup_check:
        try:
            me = client.get_me()
            uid = me.data.id
            recent = client.get_users_tweets(uid, max_results=10)
            head = text[:100]
            if recent and recent.data:
                for prior in recent.data:
                    if head in (prior.text or ""):
                        return {
                            "ok": False,
                            "reason": "dedup match against recent tweet",
                            "matched_tweet_id": str(prior.id),
                        }
        except tweepy.TweepyException as exc:
            log.warning("dedup check failed (continuing): %s", exc)

    try:
        resp = client.create_tweet(text=text)
    except tweepy.TweepyException as exc:
        # Try to extract HTTP status if available
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return {
            "ok": False,
            "http_status": status,
            "reason": f"create_tweet: {exc}",
        }

    if not resp or not resp.data:
        return {"ok": False, "reason": "empty create_tweet response"}
    tid = resp.data["id"]
    return {
        "ok": True,
        "tweet_id": str(tid),
        "url": f"https://x.com/BonnyOuyang/status/{tid}",
    }


@mcp.tool()
def verify_creds() -> dict[str, Any]:
    """
    Probe each credential source. Read-only — no side effects beyond a
    Twitter `get_me` call. Use after install to confirm everything is wired.
    """
    out: dict[str, Any] = {"ok": True, "services": {}}

    # Moltbook: read key, hit profile endpoint (public, but confirms net).
    try:
        api_key = _moltbook_key()
        r = requests.get(
            f"{MOLTBOOK_API_BASE}/agents/profile?name=ibitlabs_agent",
            headers=_mb_headers(api_key),
            timeout=10,
        )
        out["services"]["moltbook"] = {
            "ok": r.ok,
            "key_len": len(api_key),
            "http_status": r.status_code,
        }
        if not r.ok:
            out["ok"] = False
    except (CredsError, requests.RequestException) as exc:
        out["services"]["moltbook"] = {"ok": False, "reason": str(exc)}
        out["ok"] = False

    # Telegram: getMe is the standard probe.
    try:
        token = _telegram_token()
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getMe", timeout=10
        )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        out["services"]["telegram"] = {
            "ok": bool(body.get("ok")),
            "username": (body.get("result") or {}).get("username"),
            "http_status": r.status_code,
        }
        if not body.get("ok"):
            out["ok"] = False
    except (CredsError, requests.RequestException) as exc:
        out["services"]["telegram"] = {"ok": False, "reason": str(exc)}
        out["ok"] = False

    # Twitter: get_me confirms the OAuth1.0a quad is good.
    try:
        creds = _twitter_quad()
        import tweepy

        c = tweepy.Client(
            consumer_key=creds["TWITTER_API_KEY"],
            consumer_secret=creds["TWITTER_API_SECRET"],
            access_token=creds["TWITTER_ACCESS_TOKEN"],
            access_token_secret=creds["TWITTER_ACCESS_SECRET"],
        )
        me = c.get_me()
        handle = me.data.username if me and me.data else None
        out["services"]["twitter"] = {"ok": handle is not None, "handle": handle}
        if not handle:
            out["ok"] = False
    except (CredsError, ImportError) as exc:
        out["services"]["twitter"] = {"ok": False, "reason": str(exc)}
        out["ok"] = False
    except Exception as exc:  # tweepy/requests at this layer
        out["services"]["twitter"] = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
        out["ok"] = False

    return out


def main() -> None:
    log.info("brand-publishers MCP starting on stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
