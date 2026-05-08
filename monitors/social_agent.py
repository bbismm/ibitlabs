"""
Social Sentiment Agent — External sentiment from Fear & Greed Index,
CoinGecko community data, Reddit r/solana, and black swan detection.
TTL: 120s (2 min — faster for emergency detection)
"""

import logging
import json
import re
import time
import sys
sys.path.insert(0, "..")
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Sentiment keywords
BULLISH_WORDS = {
    "bullish", "moon", "pump", "buy", "long", "breakout", "surge", "rally",
    "ath", "all time high", "upgrade", "launch", "partnership", "adoption",
    "undervalued", "accumulate", "support", "bounce", "recovery", "green",
}
BEARISH_WORDS = {
    "bearish", "dump", "sell", "short", "crash", "scam", "hack", "exploit",
    "rug", "fear", "overvalued", "resistance", "decline", "red", "drain",
    "vulnerable", "lawsuit", "sec", "fraud", "concern", "risk", "warning",
}

# Black swan keywords — immediate danger, trigger emergency pause
BLACK_SWAN_WORDS = {
    "hack", "hacked", "exploit", "exploited", "drained", "stolen",
    "rug pull", "rugged", "exit scam",
    "sec charges", "sec lawsuit", "sec sues", "indicted", "arrested",
    "insolvent", "bankrupt", "bankruptcy", "collapsed", "shutdown",
    "fatal bug", "critical vulnerability", "zero day",
    "depegged", "depeg", "bank run",
    "frozen", "funds frozen", "withdrawals halted", "suspended",
}

# Shill/pump keywords — sudden coordinated buying calls
SHILL_WORDS = {
    "100x", "1000x", "to the moon", "buy now", "last chance",
    "gem", "hidden gem", "next", "gonna explode", "send it",
    "all in", "loading up", "massive pump", "squeeze",
}


def _score_text(text):
    """Score text as bullish/bearish. Returns -1 to +1."""
    text_lower = text.lower()
    words = set(re.findall(r'\w+', text_lower))
    bull = len(words & BULLISH_WORDS)
    bear = len(words & BEARISH_WORDS)
    total = bull + bear
    if total == 0:
        return 0
    return (bull - bear) / total


class SocialSentimentAgent(BaseAgent):
    def __init__(self):
        super().__init__("SocialAgent", ttl_seconds=120)  # 2 min for faster emergency detection
        self.prev_post_count = 0
        self.prev_avg_upvotes = 0
        self.prev_fng = 50

    def fetch(self) -> dict:
        data = {
            "fear_greed_index": 50,
            "fear_greed_label": "Neutral",
            "fear_greed_spike": False,     # F&G changed >15 points since last check
            "coingecko_sentiment_up": 50,
            "coingecko_dev_commits_4w": 0,
            "reddit_score": 0,
            "reddit_top_posts": [],
            "reddit_activity_spike": False,  # Post count or upvotes surged
            "black_swan": False,             # Critical danger keywords detected
            "black_swan_posts": [],          # Posts that triggered black swan
            "shill_alert": False,            # Coordinated pump/shill detected
            "shill_posts": [],
            "overall_social": "neutral",
            "overall_score": 0,
            "emergency": None,               # "BLACK_SWAN" or "SHILL_PUMP" or None
        }

        # 1. Fear & Greed Index
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.alternative.me/fng/?limit=1",
                headers={"User-Agent": "GridTrader/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                fng = json.loads(resp.read())
            fng_data = fng.get("data", [{}])[0]
            data["fear_greed_index"] = int(fng_data.get("value", 50))
            data["fear_greed_label"] = fng_data.get("value_classification", "Neutral")
        except Exception as e:
            logger.warning(f"[Social] Fear & Greed fetch failed: {e}")

        # 2. CoinGecko SOL community data
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.coingecko.com/api/v3/coins/solana"
                "?localization=false&tickers=false&market_data=false"
                "&community_data=true&developer_data=true&sparkline=false",
                headers={"User-Agent": "GridTrader/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                cg = json.loads(resp.read())
            data["coingecko_sentiment_up"] = cg.get("sentiment_votes_up_percentage", 50) or 50
            dev = cg.get("developer_data", {})
            data["coingecko_dev_commits_4w"] = dev.get("commit_count_4_weeks", 0) or 0
        except Exception as e:
            logger.warning(f"[Social] CoinGecko fetch failed: {e}")

        # 3. Reddit r/solana — posts + black swan + shill detection
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://www.reddit.com/r/solana/new.json?limit=25",
                headers={"User-Agent": "GridTrader/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                reddit = json.loads(resp.read())
            posts = reddit.get("data", {}).get("children", [])
            scores = []
            total_upvotes = 0
            recent_count = 0  # Posts in last 2 hours

            now = time.time()
            for p in posts[:20]:
                pd_data = p.get("data", {})
                title = pd_data.get("title", "")
                title_lower = title.lower()
                upvotes = pd_data.get("score", 0)
                created = pd_data.get("created_utc", 0)
                total_upvotes += upvotes

                # Only analyze posts from last 2 hours
                age_hours = (now - created) / 3600
                if age_hours > 2:
                    continue

                recent_count += 1

                score = _score_text(title)
                scores.append(score * max(1, upvotes))
                data["reddit_top_posts"].append({
                    "title": title[:80],
                    "score": upvotes,
                    "sentiment": round(score, 2),
                    "age_h": round(age_hours, 1),
                })

                # Black swan detection — only recent posts matter
                for kw in BLACK_SWAN_WORDS:
                    if kw in title_lower:
                        data["black_swan"] = True
                        data["black_swan_posts"].append(f"[{age_hours:.0f}h ago] {title[:80]}")
                        logger.warning(f"[Social] BLACK SWAN: '{title[:60]}' ({age_hours:.0f}h ago, keyword: {kw})")
                        break

                # Shill/pump detection
                for kw in SHILL_WORDS:
                    if kw in title_lower:
                        data["shill_alert"] = True
                        data["shill_posts"].append(title[:100])
                        break

            if scores:
                data["reddit_score"] = round(sum(scores) / (sum(abs(s) for s in scores) or 1), 2)

            # Activity spike: posts or upvotes surged vs last check
            avg_upvotes = total_upvotes / max(1, len(posts))
            if self.prev_post_count > 0 and recent_count > self.prev_post_count * 2:
                data["reddit_activity_spike"] = True
                logger.warning(f"[Social] ACTIVITY SPIKE: {recent_count} posts in 2h (was {self.prev_post_count})")
            if self.prev_avg_upvotes > 0 and avg_upvotes > self.prev_avg_upvotes * 3:
                data["reddit_activity_spike"] = True
                logger.warning(f"[Social] UPVOTE SPIKE: avg {avg_upvotes:.0f} (was {self.prev_avg_upvotes:.0f})")

            self.prev_post_count = recent_count
            self.prev_avg_upvotes = avg_upvotes

        except Exception as e:
            logger.warning(f"[Social] Reddit fetch failed: {e}")

        # Fear & Greed spike detection
        fng_val = data["fear_greed_index"]
        if self.prev_fng > 0 and abs(fng_val - self.prev_fng) > 15:
            data["fear_greed_spike"] = True
            logger.warning(f"[Social] F&G SPIKE: {self.prev_fng} -> {fng_val}")
        self.prev_fng = fng_val

        # Emergency classification
        if data["black_swan"]:
            data["emergency"] = "BLACK_SWAN"
        elif data["shill_alert"] and data["reddit_activity_spike"]:
            data["emergency"] = "SHILL_PUMP"

        # Overall score: weighted combination
        # Fear & Greed: 0-100, convert to -50 to +50
        fng_score = data["fear_greed_index"] - 50  # -50 to +50

        # CoinGecko sentiment: 0-100%, convert to -50 to +50
        cg_score = data["coingecko_sentiment_up"] - 50  # -50 to +50

        # Reddit: -1 to +1, scale to -50 to +50
        reddit_scaled = data["reddit_score"] * 50

        # Weighted: Fear&Greed 50%, CoinGecko 20%, Reddit 30%
        overall = fng_score * 0.5 + cg_score * 0.2 + reddit_scaled * 0.3
        data["overall_score"] = round(overall, 1)

        if overall > 15:
            data["overall_social"] = "bullish"
        elif overall < -15:
            data["overall_social"] = "bearish"
        else:
            data["overall_social"] = "neutral"

        logger.info(
            f"[Social] F&G={data['fear_greed_index']} ({data['fear_greed_label']}) | "
            f"CoinGecko={data['coingecko_sentiment_up']:.0f}% up | "
            f"Reddit={data['reddit_score']:+.2f} | "
            f"Overall={data['overall_social']} ({data['overall_score']:+.1f})"
        )

        return data
