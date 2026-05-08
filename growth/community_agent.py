"""
Community Agent — Discord/Telegram bot for iBitLabs community.

Auto-manages community:
1. Welcome new members with onboarding sequence
2. Post daily trading updates to #signals channel
3. Answer FAQs automatically using knowledge base
4. Moderate spam/scam messages
5. Track engagement metrics

Required env vars:
  DISCORD_BOT_TOKEN — Discord bot token
  DISCORD_GUILD_ID — Server ID
  DISCORD_SIGNALS_CHANNEL — Channel ID for signals
  DISCORD_GENERAL_CHANNEL — Channel ID for general chat
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path

import requests

from .base_growth_agent import BaseGrowthAgent

logger = logging.getLogger(__name__)

REPORT_STATE = Path(__file__).parent.parent / "report_state.json"
MONITOR_STATE = Path(__file__).parent.parent / "monitor_state.json"
DISCORD_API = "https://discord.com/api/v10"


class CommunityAgent(BaseGrowthAgent):
    """
    Discord community auto-manager.

    Channels:
    - #signals: automated trading updates (from trading data)
    - #general: FAQ bot, engagement
    - #announcements: weekly reports, milestones

    Features:
    - Welcome DM to new members
    - Auto-post trading signals every 2 hours
    - FAQ matching with keyword detection
    - Spam/scam detection and auto-delete
    - Daily engagement stats
    """

    FAQ_DB = {
        "what is bibsus": "iBitLabs Sniper is an AI-powered mean reversion trading system for SOL/USD. It uses StochRSI, Bollinger Bands, order flow, and regime detection to snipe reversals. 82.5% backtest win rate. Free dashboard at www.ibitlabs.com.",
        "how does it work": "The Sniper detects extreme oversold/overbought conditions on SOL/USD using 4 signal confirmations (StochRSI + Bollinger + volume + trend). It goes long in uptrends, short in downtrends, both in sideways. Fully automated.",
        "win rate": "Backtested win rate is 82.5% across 1000+ simulated trades. 13-month backtest: +27.62% return while SOL dropped -40%. The Sniper profits in all 3 regimes.",
        "pricing": "Academy: Free (8-module course)\nDashboard: $19/mo (real-time signals, manual copy-trade) or $199/year\nAutopilot: $49/mo (automated trading, $5K+ recommended) or $499/year",
        "is it safe": "Risk management is core to iBitLabs Sniper. Every trade has 1.5% TP + 5% SL + trailing stop. Max 2x leverage. 4-hour cooldown after stop loss. Regime detection pauses trading in dangerous conditions.",
        "autopilot": "Alpha Autopilot connects to your Coinbase account via API (read/trade permissions only, no withdrawals). The Sniper executes the same mean reversion strategy running on our live system. $199/mo + 20% of profits.",
        "academy": "Alpha Academy is an 8-module course teaching mean reversion trading from signal theory to building your own Sniper system. Includes 1-on-1 session with the founder and all source code. $299 one-time.",
        "minimum investment": "There's no minimum for the free dashboard. For Autopilot, we recommend at least $1,000 in your Coinbase account. The Sniper uses 2x leverage with 80% capital allocation per trade.",
        "supported exchanges": "Currently Coinbase (spot + futures) for live Sniper trading. The dashboard works with public market data.",
    }

    SCAM_KEYWORDS = [
        "free bitcoin", "send me", "dm me for", "guaranteed profit",
        "100x", "airdrop", "click this link", "verify your wallet",
        "give away", "admin will never dm", "whatsapp",
    ]

    WELCOME_MESSAGE = (
        "Welcome to iBitLabs! Here's how to get started:\n\n"
        "1. Take the free Academy course at www.ibitlabs.com/academy\n"
        "2. Follow #signals for real-time trading updates\n"
        "3. Ask questions in #general — our bot (and community) are here to help\n\n"
        "Plans:\n"
        "- Academy: FREE — learn the Sniper strategy\n"
        "- Dashboard ($19/mo): Real-time signals, copy-trade manually\n"
        "- Autopilot ($49/mo): Automated trading on your Coinbase ($5K+ recommended)\n\n"
        "Let's make money together!"
    )

    def __init__(self):
        super().__init__("community", interval_seconds=2 * 3600)  # every 2 hours

    def execute(self) -> dict:
        actions = []
        token = os.environ.get("DISCORD_BOT_TOKEN", "")

        # 1. Post trading update to #signals
        update_posted = self._post_trading_update(token)
        if update_posted:
            actions.append("signals_update")

        # 2. Check and respond to questions in #general
        questions_answered = self._answer_questions(token)
        if questions_answered:
            actions.append(f"answered_{questions_answered}_questions")

        # 3. Moderate (check for scam messages)
        moderated = self._moderate(token)
        if moderated:
            actions.append(f"moderated_{moderated}_messages")

        # 4. Track engagement
        stats = self._track_engagement(token)

        self._log_action("COMMUNITY_CYCLE", f"Actions: {', '.join(actions) or 'monitoring'}")

        return {"actions": actions, "engagement": stats}

    def _post_trading_update(self, token: str) -> bool:
        channel_id = os.environ.get("DISCORD_SIGNALS_CHANNEL", "")
        if not token or not channel_id:
            logger.info("[community] Discord not configured — skipping signal post")
            return False

        # Build signal message from live data
        monitor = self._load_monitor()
        report = self._load_report()

        if not monitor and not report:
            return False

        lines = ["**iBitLabs Signal Update**\n"]

        if report:
            pnl = report.get("daily_pnl", {})
            lines.append(f"Today's PnL: **${pnl.get('total', 0):+.2f}**")
            lines.append(f"Trades: **{report.get('fills_today', 0)}**")
            lines.append(f"SOL: **${report.get('sol_price', 0):.2f}**")

        if monitor:
            action_emoji = {"run": "RUN", "pause": "PAUSE", "widen": "WIDEN", "tighten": "TIGHT"}
            action = monitor.get("action", "?")
            lines.append(f"\nSystem: **{action_emoji.get(action, action)}**")
            lines.append(f"Regime: {monitor.get('regime', '?')}")
            lines.append(f"Fear & Greed: {monitor.get('fear_greed_index', '?')}")
            lines.append(f"Whale: {monitor.get('whale_bias', '?')}")

            alerts = monitor.get("alerts", [])
            if alerts:
                lines.append(f"\nAlerts: {', '.join(alerts)}")

        message = "\n".join(lines)
        return self._send_discord_message(token, channel_id, message)

    def _answer_questions(self, token: str) -> int:
        channel_id = os.environ.get("DISCORD_GENERAL_CHANNEL", "")
        if not token or not channel_id:
            return 0

        # Get recent messages
        messages = self._get_recent_messages(token, channel_id, limit=20)
        answered = 0

        last_processed = self.state.get("last_message_id", "0")

        for msg in messages:
            msg_id = msg.get("id", "0")
            if msg_id <= last_processed:
                continue

            # Skip bot messages
            if msg.get("author", {}).get("bot", False):
                continue

            content = msg.get("content", "").lower()

            # Check if it's a question
            if "?" not in content:
                continue

            # Match against FAQ
            answer = self._match_faq(content)
            if answer:
                self._send_discord_message(
                    token, channel_id,
                    f"<@{msg['author']['id']}> {answer}"
                )
                answered += 1

            self.state["last_message_id"] = msg_id

        return answered

    def _match_faq(self, question: str) -> str:
        question_lower = question.lower()
        best_match = ""
        best_score = 0

        for keywords, answer in self.FAQ_DB.items():
            words = keywords.split()
            score = sum(1 for w in words if w in question_lower)
            if score > best_score and score >= len(words) * 0.5:
                best_score = score
                best_match = answer

        return best_match

    def _moderate(self, token: str) -> int:
        channel_id = os.environ.get("DISCORD_GENERAL_CHANNEL", "")
        if not token or not channel_id:
            return 0

        messages = self._get_recent_messages(token, channel_id, limit=30)
        deleted = 0

        for msg in messages:
            if msg.get("author", {}).get("bot", False):
                continue

            content = msg.get("content", "").lower()
            for keyword in self.SCAM_KEYWORDS:
                if keyword in content:
                    self._delete_discord_message(token, channel_id, msg["id"])
                    self._log_action("MODERATE", f"Deleted scam: {content[:50]}")
                    deleted += 1
                    break

        return deleted

    def _track_engagement(self, token: str) -> dict:
        stats = {
            "timestamp": datetime.now().isoformat(),
            "members": 0,
            "online": 0,
        }

        guild_id = os.environ.get("DISCORD_GUILD_ID", "")
        if token and guild_id:
            try:
                resp = requests.get(
                    f"{DISCORD_API}/guilds/{guild_id}?with_counts=true",
                    headers={"Authorization": f"Bot {token}"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    stats["members"] = data.get("approximate_member_count", 0)
                    stats["online"] = data.get("approximate_presence_count", 0)
            except Exception:
                pass

        self.state["latest_engagement"] = stats
        return stats

    def _send_discord_message(self, token: str, channel_id: str, content: str) -> bool:
        if not token:
            logger.info(f"[community] Would post to Discord: {content[:80]}")
            return False
        try:
            resp = requests.post(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                headers={
                    "Authorization": f"Bot {token}",
                    "Content-Type": "application/json",
                },
                json={"content": content},
                timeout=10,
            )
            return resp.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"[community] Discord post failed: {e}")
            return False

    def _get_recent_messages(self, token: str, channel_id: str, limit: int = 20) -> list:
        if not token:
            return []
        try:
            resp = requests.get(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {token}"},
                params={"limit": limit},
                timeout=10,
            )
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return []

    def _delete_discord_message(self, token: str, channel_id: str, message_id: str) -> bool:
        if not token:
            return False
        try:
            resp = requests.delete(
                f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}",
                headers={"Authorization": f"Bot {token}"},
                timeout=10,
            )
            return resp.status_code == 204
        except Exception:
            return False

    def _load_report(self) -> dict:
        try:
            if REPORT_STATE.exists():
                data = json.loads(REPORT_STATE.read_text())
                reports = data.get("reports", [])
                return reports[0] if reports else {}
        except Exception:
            pass
        return {}

    def _load_monitor(self) -> dict:
        try:
            if MONITOR_STATE.exists():
                return json.loads(MONITOR_STATE.read_text())
        except Exception:
            pass
        return {}
