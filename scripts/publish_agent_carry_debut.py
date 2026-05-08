#!/usr/bin/env python3
"""
publish_agent_carry_debut.py — One-command debut publisher for Agent Carry.

What it does:
  1. Gathers Agent Carry's current numbers (cost + runway JSONs).
  2. Renders the dashboard HTML card.
  3. Builds a "publish bundle" directory containing every platform's
     ready-to-paste content.
  4. Prepares a Telegram announcement message.
  5. Prepares a Notion essay payload (EN + ZH).
  6. In --dry-run (default): prints a preview of everything and writes the
     bundle. Sends NOTHING to any external service.
  7. In --live: sends the Telegram announcement for real. Notion still
     requires manual paste until a NOTION_TOKEN is added to .env.

Safety:
  * --live must be passed explicitly.
  * Before any outbound API call, the script prints a 5-second countdown
    and the exact payload, so you can Ctrl+C if anything looks wrong.
  * A send-log is written to the bundle directory listing every external
    call that actually happened, with timestamp and result.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parent.parent
STATE_DIR   = REPO_ROOT / "state"
ESSAYS_DIR  = REPO_ROOT / "docs" / "essays"
OUT_ROOT    = REPO_ROOT / "out" / "publish_bundle"

COST_FILE      = STATE_DIR / "treasury_cost.json"
RUNWAY_FILE    = STATE_DIR / "treasury_runway.json"

ESSAY_EN       = ESSAYS_DIR / "agent_carry_debut.md"
ESSAY_ZH       = ESSAYS_DIR / "agent_carry_debut_zh.md"
POST_LINKEDIN  = ESSAYS_DIR / "agent_carry_linkedin.md"
POST_WECHAT    = ESSAYS_DIR / "agent_carry_wechat.md"
POST_XHS       = ESSAYS_DIR / "agent_carry_xiaohongshu.md"

RENDER_CARD_SCRIPT = REPO_ROOT / "scripts" / "render_treasury_card.py"


def load_env(env_path: Path) -> dict:
    """Tiny .env reader so we don't depend on python-dotenv."""
    env: dict = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def build_telegram_message(runway: dict, cost: dict) -> str:
    name = runway.get("agent_name", "Agent Carry")
    pool = runway.get("profit_pool_usd", 0.0)
    burn = runway.get("daily_burn_usd", 0.0)
    days = runway.get("runway_days")
    status = runway.get("status", "red")
    trades = runway.get("realized_profit", {}).get("trade_count", 0)
    month = cost.get("total_usd_per_month", 0.0)

    days_str = "∞" if days is None else f"{days:.1f} days"
    status_emoji = {
        "green": "🟢", "yellow": "🟡", "orange": "🟠",
        "red": "🔴", "in_debt": "⚫",
    }.get(status, "🔴")

    return (
        f"{status_emoji} *{name} just introduced herself.*\n\n"
        f"She's a trading bot. She has $1,000 of seed capital that she's not "
        f"allowed to touch, and ${pool:,.2f} in actual savings.\n\n"
        f"She burns *${burn:.2f}/day* staying alive — cloud, electricity, and "
        f"$200/month Claude rent. That's ${month:.2f}/month total.\n\n"
        f"*Runway: {days_str}.*\n\n"
        f"Over {trades} realized trades on SOL perps since April 2. Every trade "
        f"broadcast here. Every dollar public.\n\n"
        f"This is phase A of the AI Treasury experiment: can an AI cover its "
        f"own operating costs from its own trading profit?\n\n"
        f"Weekly runway updates start this Friday. Whether the number goes up "
        f"or down.\n\n"
        f"Essay → https://ibitlabs.com/essays\n"
        f"Dashboard → https://trade.ibitlabs.com"
    )


def build_facebook_post(runway: dict, cost: dict) -> str:
    name = runway.get("agent_name", "Agent Carry")
    pool = runway.get("profit_pool_usd", 0.0)
    burn = runway.get("daily_burn_usd", 0.0)
    days = runway.get("runway_days")
    trades = runway.get("realized_profit", {}).get("trade_count", 0)
    days_str = "∞" if days is None else f"{days:.1f} days"
    return (
        f"Meet {name}.\n\n"
        f"She's a trading bot I've been running on a Mac Mini in my apartment. "
        f"I gave her $1,000 of real money on April 2 and one rule: the principal "
        f"is not hers. It's seed capital, untouchable. Only the profit above that "
        f"line counts as her savings.\n\n"
        f"The twist — she has to use those savings to cover her own operating "
        f"costs. Cloud services. The Mac Mini's electricity bill. And the big one: "
        f"the $200/month Claude subscription that lets her think.\n\n"
        f"Today's numbers:\n"
        f"• Profit pool: ${pool:,.2f}\n"
        f"• Daily burn: ${burn:.2f}\n"
        f"• Runway: {days_str}\n"
        f"• Trades since April 2: {trades}\n\n"
        f"This is the question I'm trying to answer: can an AI pay for its own "
        f"existence from its own trading profit?\n\n"
        f"I don't know. {name} doesn't know. The only way to find out is to try "
        f"it in public, with real money, and publish the receipts.\n\n"
        f"Full essay + live dashboard: https://ibitlabs.com/essays\n"
        f"Open source: https://github.com/bbismm/ibitlabs"
    )


def render_card(bundle_dir: Path) -> Path:
    """Call render_treasury_card.py to emit dashboard_card.html into the bundle."""
    out = bundle_dir / "dashboard_card.html"
    result = subprocess.run(
        [sys.executable, str(RENDER_CARD_SCRIPT), "--out", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("[publish] card render failed:")
        print(result.stderr)
        raise SystemExit(1)
    return out


def copy_platform_files(bundle_dir: Path) -> list[Path]:
    """Copy every ready-to-paste platform file into the bundle."""
    mapping = {
        "notion_essay_EN.md": ESSAY_EN,
        "notion_essay_ZH.md": ESSAY_ZH,
        "linkedin.md":        POST_LINKEDIN,
        "wechat_moments.md":  POST_WECHAT,
        "xiaohongshu.md":     POST_XHS,
    }
    written: list[Path] = []
    for name, src in mapping.items():
        dst = bundle_dir / name
        if src.exists():
            shutil.copy2(src, dst)
            written.append(dst)
        else:
            print(f"[publish] WARN: source missing: {src}")
    return written


def send_telegram(bot_token: str, chat_id: str, text: str, dry_run: bool) -> dict:
    """POST to Telegram's sendMessage endpoint. Returns the JSON response."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    if dry_run:
        return {"dry_run": True, "would_post_to": chat_id, "chars": len(text)}

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def countdown(seconds: int, label: str) -> None:
    print(f"\n⏳  {label}. Ctrl+C to abort.")
    for i in range(seconds, 0, -1):
        print(f"   {i}…", end="", flush=True)
        time.sleep(1)
    print(" go.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish Agent Carry's debut.")
    ap.add_argument("--live", action="store_true",
                    help="Actually send outbound API calls. Default is dry-run.")
    ap.add_argument(
        "--channels", default="telegram",
        help="Comma-separated live channels. Only 'telegram' is wired right now. "
             "Notion requires NOTION_TOKEN in .env; LinkedIn/FB are OAuth work.",
    )
    args = ap.parse_args()

    dry_run = not args.live
    env = load_env(REPO_ROOT / ".env")

    # ── Load numbers
    if not COST_FILE.exists() or not RUNWAY_FILE.exists():
        print("[publish] treasury JSONs missing. "
              "Run scripts/treasury_cost.py and scripts/treasury_runway.py first.")
        return 1
    cost = json.loads(COST_FILE.read_text(encoding="utf-8"))
    runway = json.loads(RUNWAY_FILE.read_text(encoding="utf-8"))

    # ── Create bundle directory
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_dir = OUT_ROOT / f"debut_{stamp}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"\n══ Agent Carry debut · {mode} ══")
    print(f"  bundle: {bundle_dir}")
    print(f"  agent:  {runway.get('agent_name')}")
    print(f"  pool:   ${runway.get('profit_pool_usd'):.2f}")
    print(f"  burn:   ${runway.get('daily_burn_usd'):.4f}/day")
    print(f"  runway: {runway.get('runway_days')} days "
          f"(status: {runway.get('status')})")

    # ── Render HTML card
    card_path = render_card(bundle_dir)
    print(f"\n[publish] card:     {card_path}")

    # ── Copy platform files
    copied = copy_platform_files(bundle_dir)
    for p in copied:
        print(f"[publish] bundle:   {p.name}")

    # ── Build platform texts derived from live numbers
    telegram_text = build_telegram_message(runway, cost)
    facebook_text = build_facebook_post(runway, cost)
    (bundle_dir / "telegram_message.txt").write_text(telegram_text, encoding="utf-8")
    (bundle_dir / "facebook_page.txt").write_text(facebook_text, encoding="utf-8")
    print(f"[publish] bundle:   telegram_message.txt")
    print(f"[publish] bundle:   facebook_page.txt")

    # ── Preview the Telegram message
    print("\n──────── TELEGRAM PREVIEW ────────")
    print(telegram_text)
    print("──────────────────────────────────")

    # ── Outbound sending
    channels = {c.strip() for c in args.channels.split(",") if c.strip()}
    send_log: list[dict] = []

    if "telegram" in channels:
        tg_token = env.get("TG_BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN", "")
        tg_chat  = env.get("TG_CHAT_ID") or env.get("TELEGRAM_CHAT_ID", "")
        if not tg_token or not tg_chat:
            print("\n[publish] telegram: creds missing in .env — skipping")
        else:
            print(f"\n[publish] telegram: chat {tg_chat}")
            if not dry_run:
                countdown(5, "about to POST to Telegram")
            result = send_telegram(tg_token, tg_chat, telegram_text, dry_run)
            send_log.append({
                "channel": "telegram",
                "dry_run": dry_run,
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            print(f"[publish] telegram result: {result}")

    # Notion is intentionally not wired yet. Future live channel.
    if "notion" in channels:
        print("\n[publish] notion: not wired in v0. "
              "Paste notion_essay_EN.md and notion_essay_ZH.md manually.")

    # Save send log
    (bundle_dir / "send_log.json").write_text(
        json.dumps(send_log, indent=2), encoding="utf-8"
    )

    # ── Print final manual checklist
    print("\n══ NEXT STEPS (manual) ══")
    print(f"  1. Open card:   open {card_path}")
    print(f"                  then Cmd+Shift+4 to screenshot. Save the PNG.")
    print(f"  2. Notion:      open https://notion.so → Essays DB → add 2 rows.")
    print(f"                  Paste {bundle_dir}/notion_essay_EN.md")
    print(f"                  Paste {bundle_dir}/notion_essay_ZH.md")
    print(f"                  Check Published on both.")
    print(f"  3. LinkedIn:    paste {bundle_dir}/linkedin.md into a new post.")
    print(f"                  Attach the PNG screenshot from step 1.")
    print(f"  4. 小红书:      paste {bundle_dir}/xiaohongshu.md.")
    print(f"                  Use the PNG as cover image.")
    print(f"  5. WeChat:      paste {bundle_dir}/wechat_moments.md into 朋友圈.")
    print(f"                  Attach the PNG.")
    print(f"  6. Facebook:    (when Page is ready) paste {bundle_dir}/facebook_page.txt.")
    if dry_run:
        print(f"\n  7. Telegram:    {'(dry run — not sent)':<40}")
        print(f"                   To actually send:")
        print(f"                   python3 scripts/publish_agent_carry_debut.py --live")
    else:
        print(f"\n  7. Telegram:    (sent — see send_log.json)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
