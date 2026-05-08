"""
Marketing Agent — Autonomous Twitter/X content engine.

Reads trading performance data → generates tweets → posts via Twitter API.
Runs every 4 hours. Mixes content types: performance updates, market insights,
educational threads, engagement bait.

Required env vars:
  TWITTER_API_KEY, TWITTER_API_SECRET,
  TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
"""

import os
import json
import random
import time
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .base_growth_agent import BaseGrowthAgent

logger = logging.getLogger(__name__)

REPORT_STATE = Path(__file__).parent.parent / "report_state.json"
MONITOR_STATE = Path(__file__).parent.parent / "monitor_state.json"
SNIPER_STATE = Path(__file__).parent.parent / "sol_sniper_state.json"
SNIPER_DB = Path(__file__).parent.parent / "sol_sniper.db"

# Twitter API v2
TWITTER_TWEET_URL = "https://api.twitter.com/2/tweets"


class MarketingAgent(BaseGrowthAgent):
    """
    Auto-posts to Twitter/X based on real trading data.

    Content mix (rotates):
    1. Performance update — "iBitLabs +$X today, Y trades"
    2. Market insight — "SOL regime: ranging, fear index 35 — grid thriving"
    3. Educational — tips about grid trading, risk management
    4. Social proof — cumulative stats, win rate
    5. Engagement — polls, questions, hot takes

    Anti-spam: max 6 tweets/day, min 3h between tweets, no duplicate content.
    """

    CONTENT_TYPES = ["performance", "insight", "education", "social_proof", "engagement"]

    EDUCATION_TEMPLATES = [
        "Mean reversion is the most reliable pattern in crypto. SOL/USD ranges 70% of the time. iBitLabs Sniper catches every reversal — 82.5% win rate.",
        "Why 82.5% win rate? StochRSI + Bollinger Bands + volume confirmation + regime detection. 4 layers of signal validation before any trade.",
        "Most traders lose money chasing trends. Sniper trades against the crowd — buying extreme oversold, selling extreme overbought. Math beats emotions.",
        "Risk management > entry timing. iBitLabs Sniper: 1.5% TP, 5% SL, trailing stops, and automatic regime-based direction filtering.",
        "The Sniper edge: long in uptrends, short in downtrends, both in sideways. Regime detection adapts automatically — no manual switching needed.",
        "Sniper uses real-time order flow analysis — not just price. When whale walls form, when volume surges, when funding rates spike. All automated.",
        "Backtested over 13 months: +27.62% return while SOL dropped -40%. That's the power of mean reversion + short selling.",
        "Paper trading is how we validated 82.5% win rate over 1000+ simulated trades before going live. Data > hope.",
    ]

    ENGAGEMENT_TEMPLATES = [
        "What's your biggest challenge with crypto trading?\n\nA) Emotional decisions\nB) Timing entries\nC) Risk management\nD) Consistency\n\nDrop your answer below.",
        "Hot take: 90% of crypto traders would be more profitable running an AI sniper bot than day trading. Change my mind.",
        "If you could automate ONE thing about your trading, what would it be?",
        "The market doesn't care about your feelings. That's why we built an AI that doesn't have any.",
        "SOL dropped 40% in 13 months. Our Sniper returned +27.62% in the same period. The difference? Mean reversion + short selling.",
        "Which matters more for consistent profits?\n\nRT for: Win rate\nLike for: Risk management",
    ]

    def __init__(self):
        super().__init__("marketing", interval_seconds=4 * 3600)  # every 4 hours
        if "tweets_today" not in self.state:
            self.state["tweets_today"] = []
            self.state["tweet_date"] = ""
            self.state["content_index"] = 0
            self.state["total_tweets"] = 0
            self.state["posted_hashes"] = []

    def execute(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")

        # Reset daily counter
        if self.state.get("tweet_date") != today:
            self.state["tweets_today"] = []
            self.state["tweet_date"] = today

        # Max 6 tweets/day
        if len(self.state["tweets_today"]) >= 6:
            return {"action": "skip", "reason": "daily limit reached (6)"}

        # Generate tweet
        content_type = self._next_content_type()
        tweet_text = self._generate_tweet(content_type)

        if not tweet_text:
            return {"action": "skip", "reason": "no content generated"}

        # Dedup check
        tweet_hash = hashlib.md5(tweet_text.encode()).hexdigest()[:12]
        if tweet_hash in self.state.get("posted_hashes", []):
            return {"action": "skip", "reason": "duplicate content"}

        # Post to Twitter
        result = self._post_tweet(tweet_text)

        if result.get("success"):
            self.state["tweets_today"].append({
                "time": datetime.now().strftime("%H:%M"),
                "type": content_type,
                "text": tweet_text[:50],
            })
            self.state["total_tweets"] = self.state.get("total_tweets", 0) + 1
            # Keep last 100 hashes
            hashes = self.state.get("posted_hashes", [])
            hashes.append(tweet_hash)
            self.state["posted_hashes"] = hashes[-100:]
            self._log_action("TWEET", f"[{content_type}] {tweet_text[:80]}")
        else:
            self._log_action("TWEET_FAIL", result.get("error", "unknown"), "failed")

        return {
            "action": "tweet",
            "type": content_type,
            "text": tweet_text[:100],
            "posted": result.get("success", False),
            "tweets_today": len(self.state["tweets_today"]),
        }

    def _next_content_type(self) -> str:
        """Rotate content types for variety."""
        idx = self.state.get("content_index", 0) % len(self.CONTENT_TYPES)
        self.state["content_index"] = idx + 1
        return self.CONTENT_TYPES[idx]

    def _generate_tweet(self, content_type: str) -> str:
        if content_type == "performance":
            return self._tweet_performance()
        elif content_type == "insight":
            return self._tweet_insight()
        elif content_type == "education":
            return random.choice(self.EDUCATION_TEMPLATES)
        elif content_type == "social_proof":
            return self._tweet_social_proof()
        elif content_type == "engagement":
            return random.choice(self.ENGAGEMENT_TEMPLATES)
        return ""

    def _tweet_performance(self) -> str:
        sniper = self._load_sniper_state()
        report = self._load_report()

        # Primary: Sniper live state
        if sniper:
            cash = sniper.get("cash", 1000)
            pnl_pct = (cash - 1000) / 1000 * 100
            pos = sniper.get("position")
            grid = sniper.get("grid", {})
            grid_pnl = grid.get("pnl", 0)
            grid_trades = grid.get("trades", 0)
            grid_wins = grid.get("wins", 0)
            mode = sniper.get("mode", "paper")

            status = "LIVE" if mode == "live" else "PAPER"
            pos_text = f"{pos['direction'].upper()} @ ${pos['entry']:.2f}" if pos else "No position"

            return (
                f"iBitLabs Sniper [{status}]\n\n"
                f"Balance: ${cash:,.2f} ({pnl_pct:+.1f}%)\n"
                f"Position: {pos_text}\n"
                f"Grid: {grid_trades} trades, {grid_wins} wins, ${grid_pnl:+.2f}\n\n"
                f"Mean reversion on SOL/USD. 82.5% backtest win rate.\n"
                f"Fully automated. Zero emotions.\n\n"
                f"#SOL #CryptoTrading #MeanReversion #iBitLabs"
            )

        # Fallback: daily report
        if report:
            pnl = report.get("daily_pnl", {})
            total = pnl.get("total", 0)
            fills = report.get("fills_today", 0)
            sol_price = report.get("sol_price", 0)
            return (
                f"iBitLabs Sniper Update\n\n"
                f"PnL: ${total:+.2f}\n"
                f"Trades: {fills}\n"
                f"SOL: ${sol_price:.2f}\n\n"
                f"Mean reversion sniper. Automated. Backtested.\n\n"
                f"#SOL #CryptoTrading #iBitLabs"
            )

        return "iBitLabs Sniper is live — trading SOL/USD mean reversion 24/7. 82.5% backtest win rate. Real signals, automated execution, zero emotions."

    def _tweet_insight(self) -> str:
        monitor = self._load_monitor()
        sniper = self._load_sniper_state()

        if not monitor and not sniper:
            return "Markets are noise. iBitLabs Sniper finds the signal. StochRSI + Bollinger + Order Flow + Regime Detection = 82.5% win rate. #CryptoAI"

        lines = ["iBitLabs Sniper — Market Read\n"]

        if monitor:
            regime = monitor.get("regime", "ranging")
            fng = monitor.get("fear_greed_index", 50)
            fng_label = monitor.get("fear_greed_label", "Neutral")
            whale = monitor.get("whale_bias", "neutral")
            lines.append(f"Regime: {regime.upper()}")
            lines.append(f"Fear & Greed: {fng} ({fng_label})")
            lines.append(f"Whale flow: {whale}")

            # Sniper adapts direction based on regime
            if regime.startswith("trending_up"):
                lines.append("Sniper mode: LONG ONLY (uptrend detected)")
            elif regime.startswith("trending_down"):
                lines.append("Sniper mode: SHORT ONLY (downtrend detected)")
            else:
                lines.append("Sniper mode: LONG + SHORT (ranging market)")

        if sniper and sniper.get("position"):
            pos = sniper["position"]
            lines.append(f"\nActive: {pos['direction'].upper()} SOL @ ${pos['entry']:.2f}")

        lines.append("\nMean reversion sniper. Regime adaptive. Fully automated.\n")
        lines.append("#SOL #CryptoSignals #iBitLabs")

        return "\n".join(lines)

    def _tweet_social_proof(self) -> str:
        sniper = self._load_sniper_state()
        sniper_db = self._load_sniper_db_stats()

        if sniper_db:
            return (
                f"iBitLabs Sniper Stats\n\n"
                f"Total trades: {sniper_db.get('total_trades', 0)}\n"
                f"Wins: {sniper_db.get('wins', 0)} | Losses: {sniper_db.get('losses', 0)}\n"
                f"Win rate: {sniper_db.get('win_rate', 82.5):.1f}%\n"
                f"Total PnL: ${sniper_db.get('total_pnl', 0):+.2f}\n"
                f"Backtest: +27.62% over 13mo (SOL -40%)\n\n"
                f"Proof over promises.\n\n"
                f"#CryptoTrading #AlgoTrading #iBitLabs"
            )

        if sniper:
            cash = sniper.get("cash", 1000)
            grid = sniper.get("grid", {})
            return (
                f"iBitLabs Sniper Stats\n\n"
                f"Balance: ${cash:,.2f}\n"
                f"Grid trades: {grid.get('trades', 0)}\n"
                f"Grid wins: {grid.get('wins', 0)}\n"
                f"Backtest win rate: 82.5%\n"
                f"13mo backtest: +27.62% (SOL -40%)\n\n"
                f"Mean reversion works. Data proves it.\n\n"
                f"#CryptoTrading #iBitLabs"
            )

        return "iBitLabs Sniper: Mean reversion on SOL/USD. 82.5% backtest win rate. +27.62% return over 13 months while SOL dropped 40%. #iBitLabs #CryptoAI"

    def _post_tweet(self, text: str) -> dict:
        """Post tweet via Twitter API v2 with OAuth 1.0a."""
        api_key = os.environ.get("TWITTER_API_KEY", "")
        api_secret = os.environ.get("TWITTER_API_SECRET", "")
        access_token = os.environ.get("TWITTER_ACCESS_TOKEN", "")
        access_secret = os.environ.get("TWITTER_ACCESS_SECRET", "")

        if not all([api_key, api_secret, access_token, access_secret]):
            logger.warning("[marketing] Twitter credentials not set — tweet queued only")
            return {"success": False, "error": "no_credentials", "queued": text}

        try:
            from requests_oauthlib import OAuth1
            auth = OAuth1(api_key, api_secret, access_token, access_secret)
            resp = requests.post(
                TWITTER_TWEET_URL,
                json={"text": text},
                auth=auth,
                timeout=15,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                tweet_id = data.get("data", {}).get("id", "")
                return {"success": True, "tweet_id": tweet_id}
            else:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except ImportError:
            logger.warning("[marketing] requests_oauthlib not installed — pip install requests-oauthlib")
            return {"success": False, "error": "missing_dependency", "queued": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _load_sniper_state(self) -> dict:
        try:
            if SNIPER_STATE.exists():
                return json.loads(SNIPER_STATE.read_text())
        except Exception:
            pass
        return {}

    def _load_sniper_db_stats(self) -> dict:
        """Read aggregate stats from sol_sniper.db."""
        try:
            if not SNIPER_DB.exists():
                return {}
            import sqlite3
            conn = sqlite3.connect(str(SNIPER_DB))
            cur = conn.cursor()
            # Try trades table
            cur.execute("SELECT COUNT(*), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), SUM(CASE WHEN pnl<=0 THEN 1 ELSE 0 END), SUM(pnl) FROM trades")
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                total = row[0]
                wins = row[1] or 0
                losses = row[2] or 0
                pnl = row[3] or 0
                return {
                    "total_trades": total,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": wins / max(total, 1) * 100,
                    "total_pnl": pnl,
                }
        except Exception:
            pass
        return {}

    def _load_report(self) -> dict:
        try:
            if REPORT_STATE.exists():
                data = json.loads(REPORT_STATE.read_text())
                reports = data.get("reports", [])
                return reports[0] if reports else {}
        except Exception:
            pass
        return {}

    def _load_all_reports(self) -> list:
        try:
            if REPORT_STATE.exists():
                data = json.loads(REPORT_STATE.read_text())
                return data.get("reports", [])
        except Exception:
            pass
        return []

    def _load_monitor(self) -> dict:
        try:
            if MONITOR_STATE.exists():
                return json.loads(MONITOR_STATE.read_text())
        except Exception:
            pass
        return {}
