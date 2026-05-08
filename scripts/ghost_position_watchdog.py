#!/usr/bin/env python3
"""Ghost-position watchdog — runs every 60s via launchd.

Triple-checks that the bot's view of position state agrees with Coinbase's.
Three independent ground-truth sources:

  1. Bot state file (`sol_sniper_state.json`).position
  2. Coinbase API `get_futures_position`
  3. Buying-power delta: `total_usd_balance - futures_buying_power`
     - 0 → no margin locked → no position
     - $200-$700 (per contract @ 2x leverage) → position exists

If any two disagree on "is there a position now?":
  - 1st mismatch: log + ntfy
  - 3rd consecutive: log + ntfy + iMessage
  - 5th consecutive: bootout `com.ibitlabs.sniper` to stop bot from acting on
    a fictional state

The 2026-04-29 incidents (close_position 404 retry loop, +$10 captured
manually) showed we lacked autonomous detection. This watchdog closes that
gap. See `reference_close_position_sdk_404.md` and the "幽灵仓位" thread.

Streak state at `state/ghost_watchdog_state.json`. Reset to 0 on agreement.

Exit codes: 0 success, 1 fetch failure (treat as transient, no alert).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/Users/bonnyagent/ibitlabs")
STATE_FILE = ROOT / "sol_sniper_state.json"
WATCHDOG_STATE = ROOT / "state" / "ghost_watchdog_state.json"
SYMBOL = "SLP-20DEC30-CDE"

# Per-contract margin at the bot's 2x leverage. SOL @ $84 × 5 SOL × 0.5 leverage
# ≈ $210 lock per contract. We use a wider band [50, 800] to tolerate price
# swings and edge cases without false-positive alarms.
MARGIN_BAND_LOW = 50.0
MARGIN_BAND_HIGH = 800.0

ALERT_AT_STREAK = 1   # log + ntfy on 1st mismatch
ESCALATE_AT_STREAK = 3  # log + ntfy + iMessage
BOOTOUT_AT_STREAK = 5   # bootout the bot

LOG_PREFIX = "[GHOST-WATCHDOG]"


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {LOG_PREFIX} {msg}", flush=True)


def read_bot_state() -> dict:
    if not STATE_FILE.exists():
        return {"position": None, "exists": False}
    try:
        s = json.loads(STATE_FILE.read_text())
        pos = s.get("position")
        return {"position": pos, "exists": bool(pos and pos.get("symbol"))}
    except Exception as e:
        return {"position": None, "exists": False, "err": str(e)}


def read_coinbase_state() -> dict:
    """Returns { api_has_position, locked_margin_has_position, total_usd, bp,
    api_position }. api_has_position and locked_margin_has_position are the
    two independent Coinbase signals."""
    try:
        # Lazy import — keep startup cheap, fail fast if not installed
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        from coinbase.rest import RESTClient

        c = RESTClient(
            api_key=os.environ.get("CB_API_KEY", ""),
            api_secret=os.environ.get("CB_API_SECRET", "").replace("\\n", "\n"),
        )

        # Source 2: get_futures_position
        # The SDK has two failure modes that both mean "no position":
        #   - HTTP 404 NOT_FOUND
        #   - Local TypeError "FCMPosition() argument after ** must be a
        #     mapping, not NoneType" — happens when the response carries
        #     position=null and the SDK tries to construct FCMPosition(None)
        api_position = None
        api_has_position = False
        try:
            r = c.get_futures_position(product_id=SYMBOL)
            p = r if isinstance(r, dict) else vars(r)
            p = p.get("position") if isinstance(p, dict) else p
            if isinstance(p, str):
                import ast
                try:
                    p = ast.literal_eval(p)
                except Exception:
                    p = None
            if isinstance(p, dict) and p.get("number_of_contracts"):
                api_position = p
                api_has_position = True
        except Exception as e:
            msg = str(e)
            if "404" in msg or "NOT_FOUND" in msg or "FCMPosition" in msg:
                api_has_position = False
            else:
                raise  # propagate other errors as fetch failure

        # Source 3: buying-power delta
        r = c.get_futures_balance_summary()
        bs = r if isinstance(r, dict) else vars(r)
        bs = bs.get("balance_summary", bs)
        if not isinstance(bs, dict):
            bs = vars(bs)

        def _v(field):
            x = bs.get(field, {})
            if isinstance(x, dict):
                return float(x.get("value", 0) or 0)
            return float(getattr(x, "value", 0) or 0)

        total_usd = _v("total_usd_balance")
        bp = _v("futures_buying_power")
        # Locked margin = how much of total_usd is held as collateral.
        # When flat, total_usd ≈ bp (Coinbase reserves a few cents).
        locked = total_usd - bp
        margin_has_position = MARGIN_BAND_LOW <= locked <= MARGIN_BAND_HIGH

        return {
            "ok": True,
            "api_has_position": api_has_position,
            "api_position": api_position,
            "locked_margin": locked,
            "margin_has_position": margin_has_position,
            "total_usd": total_usd,
            "bp": bp,
        }
    except Exception as e:
        return {"ok": False, "err": str(e)}


def read_streak() -> int:
    if not WATCHDOG_STATE.exists():
        return 0
    try:
        return int(json.loads(WATCHDOG_STATE.read_text()).get("streak", 0))
    except Exception:
        return 0


def write_streak(streak: int, last_check: dict) -> None:
    WATCHDOG_STATE.parent.mkdir(parents=True, exist_ok=True)
    WATCHDOG_STATE.write_text(json.dumps({
        "streak": streak,
        "last_check_ts": int(time.time()),
        "last_check": last_check,
    }, indent=2))


def ntfy(title: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC", "")
    if not topic:
        return
    # HTTP headers default to latin-1 in urllib — non-ASCII (emoji, CJK)
    # raises UnicodeEncodeError. ntfy.sh accepts UTF-8 via percent-encoded
    # `X-Title` header (RFC 5987 spirit) but the simpler & more portable
    # path is: keep title ASCII, push the rich content into body. Today's
    # 20:42 incident fired 8+ ntfy calls into thin air because every title
    # carried "⛔" / "⚠️" — operator received zero pushes during a real
    # bootout sequence. Strip non-ASCII and substitute readable tags.
    safe_title = title.encode("ascii", errors="replace").decode("ascii").replace("?", "")
    safe_title = safe_title.strip() or "ghost-watchdog"
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={"Title": safe_title, "Priority": "high"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        log(f"ntfy failed: {e}")


def imessage(text: str) -> None:
    """Best-effort iMessage via osascript. Silent on failure."""
    recipient = os.environ.get("IMESSAGE_RECIPIENT", "")
    if not recipient:
        return
    try:
        script = f'tell application "Messages" to send "{text}" to buddy "{recipient}"'
        subprocess.run(["osascript", "-e", script], timeout=10, check=False,
                       capture_output=True)
    except Exception as e:
        log(f"imessage failed: {e}")


def bootout_bot() -> None:
    uid = os.getuid()
    log("BOOTOUT: stopping com.ibitlabs.sniper")
    try:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}/com.ibitlabs.sniper"],
            timeout=15, check=False, capture_output=True,
        )
    except Exception as e:
        log(f"bootout failed: {e}")


def main() -> int:
    bot = read_bot_state()
    cb = read_coinbase_state()

    if not cb.get("ok"):
        # Transient API failure — log and exit non-zero, don't move streak.
        log(f"fetch failed: {cb.get('err')!r}")
        return 1

    bot_has = bot["exists"]
    api_has = cb["api_has_position"]
    margin_has = cb["margin_has_position"]
    locked = cb["locked_margin"]

    # Three independent signals on "is there a position?": bot state file,
    # Coinbase API get_futures_position, locked-margin delta.
    #
    # Ground-truth rule (post 2026-04-29 incident): MAJORITY of the three
    # votes is the truth; bot vs majority is the ghost test.
    #
    # Why not unanimous (the v1 rule): Coinbase's get_futures_position
    # endpoint is known to drop a real position from its response under load
    # while locked margin clearly shows the contract is held (see memory
    # `reference_coinbase_ui_position_ghost.md`). Under unanimous-required,
    # every API hiccup escalates to bootout — which is exactly what fired
    # at 20:42 today on a perfectly healthy SHORT @ 83.66, with bot+margin
    # both correctly saying "position open" and only api flaking. Majority
    # voting absorbs single-source flakes; only true 2-vs-1 mismatch
    # (bot disagrees with margin AND api together) escalates.
    votes = [bot_has, api_has, margin_has]
    majority_has_position = sum(1 for v in votes if v) >= 2
    agreement = (bot_has == majority_has_position)

    summary = (
        f"bot={bot_has} api={api_has} margin={margin_has} "
        f"(locked=${locked:+.2f})"
    )

    streak = read_streak()
    if agreement:
        if streak > 0:
            log(f"AGREEMENT (streak reset from {streak}): {summary}")
        else:
            log(f"agreement: {summary}")
        write_streak(0, {"agreement": True, **{k: cb.get(k) for k in
                                               ("api_has_position",
                                                "margin_has_position",
                                                "locked_margin")}})
        return 0

    # Disagreement
    streak += 1
    write_streak(streak, {"agreement": False, "summary": summary,
                          "bot_has": bot_has, "api_has": api_has,
                          "margin_has": margin_has, "locked": locked})
    log(f"DISAGREEMENT (streak={streak}): {summary}")

    if streak >= BOOTOUT_AT_STREAK:
        msg = (f"Ghost watchdog: {streak} consecutive mismatches. "
               f"Booting out sniper. {summary}")
        log(msg)
        ntfy("[BOOTOUT] GHOST: bot booted out", msg)
        imessage(f"iBitLabs ghost-watchdog: {summary} — sniper bootout fired.")
        bootout_bot()
    elif streak >= ESCALATE_AT_STREAK:
        msg = (f"Ghost watchdog: {streak} consecutive mismatches. "
               f"Bot still running. {summary}")
        log(msg)
        ntfy("[ALERT] GHOST persistent", msg)
        imessage(f"iBitLabs ghost-watchdog: {streak}x mismatch — {summary}")
    elif streak >= ALERT_AT_STREAK:
        ntfy("[ALERT] GHOST first hit", summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
