"""
Notifier Agent -Push notifications for trade events
Channels: iMessage + ntfy + Telegram

Audience: paid subscribers + spectators watching the $1000→$10,000 challenge.
Every message should tell the story: what happened, how much, where we stand.
"""

import os
import logging
import subprocess
import time
import urllib.request
import urllib.error
import json

logger = logging.getLogger(__name__)

IMESSAGE_TO = os.environ.get("NOTIFY_IMESSAGE", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")

# Goal raised 2026-04-11 from $3k to $10k (see project_sniper_10x_goal.md)
GOAL = 10000.0
LIVE_URL = "https://www.ibitlabs.com"


def _progress_bar(balance: float) -> str:
    pct = min((balance - 1000) / (GOAL - 1000) * 100, 100)
    filled = int(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"[{bar}] {pct:.1f}% -> $10,000"


def _footer() -> str:
    return f"\nLive: {LIVE_URL}"


class Notifier:
    def __init__(self):
        self.to = IMESSAGE_TO
        self.enabled = True
        channels = []
        if self.to:
            channels.append("iMessage")
        if NTFY_TOPIC:
            channels.append(f"ntfy/{NTFY_TOPIC}")
        if TG_BOT_TOKEN and TG_CHAT_ID:
            channels.append("Telegram")
        logger.info(f"[Notify] Channels: {', '.join(channels) or 'none'}")

    def _send(self, title: str, body: str, priority: str = "default"):
        """Send to all channels + write log"""
        if not self.enabled:
            return

        msg = f"[{title}] {body}"

        # iMessage
        if self.to:
            try:
                script = (
                    'tell application "Messages"\n'
                    '  set targetService to 1st account whose service type = iMessage\n'
                    '  set targetBuddy to participant "{to}" of targetService\n'
                    '  send "{msg}" to targetBuddy\n'
                    'end tell'
                ).format(
                    to=self.to,
                    msg=msg.replace('"', '\\"').replace('\n', ' '),
                )
                subprocess.run(
                    ["osascript", "-e", script],
                    timeout=10, capture_output=True,
                )
            except Exception as e:
                logger.warning(f"[Notify] iMessage failed: {e}")

        # ntfy
        if NTFY_TOPIC:
            try:
                tags = "chart_with_upwards_trend" if "WIN" in title or "OPEN" in title else "robot"
                if "LOSS" in title or "STOP" in title:
                    tags = "warning"
                # ntfy headers must be ASCII
                safe_title = title.encode("ascii", "replace").decode("ascii")
                req = urllib.request.Request(
                    f"https://ntfy.sh/{NTFY_TOPIC}",
                    data=body.encode("utf-8"),
                    headers={
                        "Title": safe_title,
                        "Priority": priority,
                        "Tags": tags,
                    },
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                logger.warning(f"[Notify] ntfy failed: {e}")

        # Telegram
        if TG_BOT_TOKEN and TG_CHAT_ID:
            try:
                text = f"*{title}*\n{body}"
                payload = json.dumps({
                    "chat_id": TG_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown",
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                logger.warning(f"[Notify] Telegram failed: {e}")

        # Log
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open("notifications.log", "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    # ── Public API (called by trading engine) ──

    def on_trade_closed(self, direction: str, entry: float, exit_price: float,
                        pnl_usd: float, balance: float, win_rate: float,
                        total_trades: int, reason: str = "TP"):
        """A completed trade -the main event subscribers care about."""
        emoji = "WIN" if pnl_usd >= 0 else "LOSS"
        sign = "+" if pnl_usd >= 0 else ""
        pnl_pct = abs(exit_price - entry) / entry * 100 if entry > 0 else 0

        body = (
            f"{direction.upper()} SOL ${entry:.2f} -> ${exit_price:.2f}\n"
            f"PnL: {sign}${pnl_usd:.2f} ({sign}{pnl_pct:.2f}%)\n"
            f"Balance: ${balance:.2f} | WR: {win_rate:.0f}% ({total_trades} trades)\n"
            f"{_progress_bar(balance)}{_footer()}"
        )
        pri = "high" if abs(pnl_usd) > 5 else "default"
        self._send(f"TRADE {emoji} -{reason.upper()}", body, priority=pri)

    def on_position_opened(self, direction: str, price: float,
                           reasons: list, balance: float):
        """New position opened -subscribers want to know what we're in."""
        why = ", ".join(reasons[:3]) if reasons else "signal"
        body = (
            f"{direction.upper()} SOL @ ${price:.2f}\n"
            f"Signal: {why}\n"
            f"Balance: ${balance:.2f}{_footer()}"
        )
        self._send(f"POSITION OPEN -{direction.upper()}", body)

    def on_stop_loss(self, symbol: str, price: float, pnl_usd: float,
                     balance: float, cooldown_hours: float):
        """Stop loss hit -high priority alert."""
        body = (
            f"{symbol} stopped @ ${price:.2f}\n"
            f"Loss: ${pnl_usd:.2f}\n"
            f"Balance: ${balance:.2f} | Cooldown: {cooldown_hours}h\n"
            f"{_progress_bar(balance)}{_footer()}"
        )
        self._send("STOP LOSS", body, priority="high")

    def on_daily_summary(self, balance: float, day_pnl: float,
                         day_trades: int, day_wins: int, win_rate: float):
        """End-of-day recap."""
        sign = "+" if day_pnl >= 0 else ""
        body = (
            f"Today: {sign}${day_pnl:.2f} | {day_wins}/{day_trades} wins\n"
            f"Balance: ${balance:.2f} | Overall WR: {win_rate:.0f}%\n"
            f"{_progress_bar(balance)}{_footer()}"
        )
        self._send("DAILY RECAP", body)

    def on_startup(self, exchange: str, balance: float):
        body = (
            f"{exchange} | Balance: ${balance:.2f}\n"
            f"{_progress_bar(balance)}{_footer()}"
        )
        self._send("BOT ONLINE", body)

    def on_shutdown(self, balance: float, total_pnl: float):
        sign = "+" if total_pnl >= 0 else ""
        body = (
            f"Total PnL: {sign}${total_pnl:.2f}\n"
            f"Balance: ${balance:.2f}\n"
            f"{_progress_bar(balance)}{_footer()}"
        )
        self._send("BOT OFFLINE", body)

    # ── Legacy API (backward compat with current engine calls) ──

    def on_order_filled(self, side: str, symbol: str, price: float,
                        quantity: float, pnl: float = 0):
        """Legacy -keep for backward compat but suppress noise."""
        pass  # Replaced by on_trade_closed / on_position_opened

    def on_grid_created(self, symbol: str, levels: int, mode: str):
        """Grid activation -internal, don't notify subscribers."""
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open("notifications.log", "a", encoding="utf-8") as f:
                f.write(f"[{ts}] [GRID ON] {symbol} {mode} {levels} levels\n")
        except Exception:
            pass

    def on_cooldown_end(self, symbol: str):
        self._send("TRADING RESUMED", f"{symbol} -scanning for signals")
