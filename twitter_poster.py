"""
iBitLabs — Auto-Poster (Telegram Channel + Twitter/X)
Posts trade updates to @ibitlabs_sniper (Telegram) and @BonnyOuyang (Twitter).
Called by kv_publisher broadcast functions when trades open/close.

Required env vars:
  TELEGRAM_BOT_TOKEN — Bot token for @ibitlabs_signal_bot
  TWITTER_OAUTH2_TOKEN — OAuth 2.0 access token (from twitter_auth.py)
  TWITTER_REFRESH_TOKEN — OAuth 2.0 refresh token
  TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET — OAuth 2.0 app credentials
"""

import os
import json
import time
import base64
import logging
from urllib.request import Request, urlopen
from urllib.parse import urlencode

logger = logging.getLogger("channel_poster")

CHANNEL = "@ibitlabs_sniper"
TWEET_URL = "https://api.twitter.com/2/tweets"


# ── Twitter OAuth 2.0 token refresh ──

def _refresh_twitter_token():
    """Refresh the OAuth 2.0 access token using refresh_token."""
    client_id = os.environ.get("TWITTER_CLIENT_ID", "")
    client_secret = os.environ.get("TWITTER_CLIENT_SECRET", "")
    refresh_token = os.environ.get("TWITTER_REFRESH_TOKEN", "")
    if not all([client_id, client_secret, refresh_token]):
        return None

    try:
        data = urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }).encode()
        creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        req = Request("https://api.twitter.com/2/oauth2/token", data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Authorization", f"Basic {creds}")

        with urlopen(req, timeout=15) as resp:
            tokens = json.loads(resp.read())

        new_access = tokens.get("access_token", "")
        new_refresh = tokens.get("refresh_token", "")

        if new_access:
            os.environ["TWITTER_OAUTH2_TOKEN"] = new_access
            if new_refresh:
                os.environ["TWITTER_REFRESH_TOKEN"] = new_refresh
            # Also save to .env file
            _update_env_token(new_access, new_refresh)
            logger.info("[TWITTER] Token refreshed successfully")
            return new_access
    except Exception as e:
        logger.warning(f"[TWITTER] Token refresh failed: {e}")
    return None


def _update_env_token(access_token, refresh_token=""):
    """Update tokens in .env file."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "r") as f:
            content = f.read()
        for key, val in [("TWITTER_OAUTH2_TOKEN", access_token), ("TWITTER_REFRESH_TOKEN", refresh_token)]:
            if not val:
                continue
            if f"{key}=" in content:
                lines = content.split("\n")
                content = "\n".join(
                    f"{key}={val}" if line.startswith(f"{key}=") else line
                    for line in lines
                )
            else:
                content = content.rstrip("\n") + f"\n{key}={val}\n"
        with open(env_path, "w") as f:
            f.write(content)
    except Exception:
        pass


# ── Send functions ──

def _send_channel(text: str):
    """Send a message to the Telegram channel."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": CHANNEL,
            "text": text,
            "parse_mode": "Markdown",
        }).encode()
        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=10) as resp:
            logger.info(f"[CHANNEL] Posted to {CHANNEL}")
    except Exception as e:
        logger.warning(f"[CHANNEL] Post failed: {e}")


def _send_tweet(text: str):
    """Post a tweet to @BonnyOuyang using OAuth 2.0."""
    token = os.environ.get("TWITTER_OAUTH2_TOKEN", "")
    if not token:
        logger.warning("[TWITTER] No TWITTER_OAUTH2_TOKEN — run twitter_auth.py first")
        return

    # Strip markdown for Twitter
    clean = text.replace("*", "").replace("_", "").replace("\n\n- iBitLabs Sniper", "")
    if len(clean) > 275:
        clean = clean[:272] + "..."
    clean += "\n\nibitlabs.com"

    for attempt in range(2):  # Try once, refresh token if 401, try again
        try:
            body = json.dumps({"text": clean}).encode()
            req = Request(TWEET_URL, data=body, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                tid = result.get("data", {}).get("id", "?")
                logger.info(f"[TWITTER] Posted: https://x.com/BonnyOuyang/status/{tid}")
                return
        except Exception as e:
            err_str = str(e)
            if "401" in err_str and attempt == 0:
                logger.info("[TWITTER] Token expired, refreshing...")
                new_token = _refresh_twitter_token()
                if new_token:
                    token = new_token
                    continue
            logger.warning(f"[TWITTER] Post failed: {e}")
            return


def _post(text: str):
    """Post to Telegram channel only. Twitter disabled to avoid spam."""
    _send_channel(text)
    # _send_tweet(text)  # Disabled — auto-tweets may annoy followers


# ── Trade event handlers (called by kv_publisher) ──

def tweet_signal_open(direction: str, price: float, stoch_rsi: float):
    """Post when Sniper opens a position."""
    is_long = direction.upper() in ("BUY", "LONG")
    emoji = "\U0001f7e2" if is_long else "\U0001f534"
    label = "LONG" if is_long else "SHORT"

    text = (
        f"{emoji} *Sniper {label} — SOL PERP ${price:.2f}*\n\n"
        f"StochRSI: {stoch_rsi:.3f}\n"
        f"All conditions met. Position opened.\n\n"
        f"— _iBitLabs Sniper_"
    )
    _post(text)


def tweet_signal_close(direction: str, entry_price: float, exit_price: float,
                       pnl_usd: float, pnl_pct: float, reason: str):
    """Post when Sniper closes a position."""
    is_win = pnl_usd >= 0
    emoji = "\u2705" if is_win else "\u26a0\ufe0f"
    label = direction.upper()
    pnl_sign = "+" if pnl_usd >= 0 else ""
    reason_map = {"tp": "Take Profit", "sl": "Stop Loss", "trailing": "Trailing Stop",
                  "timeout": "Timeout", "system": "System Exit"}
    reason_label = reason_map.get(reason, reason)

    text = (
        f"{emoji} *Closed {label} — SOL PERP*\n\n"
        f"${entry_price:.2f} → ${exit_price:.2f}\n"
        f"P/L: {pnl_sign}${pnl_usd:.2f} ({pnl_sign}{pnl_pct:.2f}%)\n"
        f"Reason: {reason_label}\n\n"
        f"— _iBitLabs Sniper_"
    )
    _post(text)


def tweet_grid_trade(side: str, entry: float, exit_price: float,
                     pnl: float, total_pnl: float):
    """Post when grid completes a trade (TP hit)."""
    emoji = "\u2705" if pnl >= 0 else "\u26a0\ufe0f"
    pnl_sign = "+" if pnl >= 0 else ""
    total_sign = "+" if total_pnl >= 0 else ""

    text = (
        f"{emoji} *Grid TP — SOL PERP*\n\n"
        f"${entry:.2f} → ${exit_price:.2f}\n"
        f"P/L: {pnl_sign}${pnl:.2f} | Total: {total_sign}${total_pnl:.2f}\n\n"
        f"— _iBitLabs Sniper_"
    )
    _post(text)
