#!/usr/bin/env python3
"""
SOL 操盘团队 — Monitor Harness
4个独立监控Agent + 决策协调器
输出 monitor_state.json 供 scalper 读取

用法:
  export CB_API_KEY='...'
  export CB_API_SECRET='...'
  python3 monitor_harness.py
"""

import json
import os
import sys
import time
import logging
import signal

import ccxt

from monitors import MarketSentimentAgent, FundingRateAgent, WhaleFlowAgent, RegimeDetectorAgent, SocialSentimentAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("monitor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

running = True
STATE_FILE = os.path.join(os.path.dirname(__file__), "monitor_state.json")


def signal_handler(sig, frame):
    global running
    logger.info("[Monitor] 收到终止信号...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class MonitorHarness:
    """协调4个监控Agent，汇总输出决策"""

    def __init__(self, exchange, cfm_exchange=None):
        self.agents = {
            "sentiment": MarketSentimentAgent(exchange),
            "funding": FundingRateAgent(exchange, cfm_exchange),
            "whale": WhaleFlowAgent(exchange),
            "regime": RegimeDetectorAgent(exchange),
            "social": SocialSentimentAgent(),
        }
        logger.info(f"Monitor Team initialized: {len(self.agents)} agents")

    def run_cycle(self) -> dict:
        """运行一个完整周期，返回汇总决策"""
        sentiment = self.agents["sentiment"].get()
        funding = self.agents["funding"].get()
        whale = self.agents["whale"].get()
        regime = self.agents["regime"].get()
        social = self.agents["social"].get()

        # === WEIGHTED SCORING DECISION ENGINE ===
        #
        # Each agent contributes a RISK SCORE (-100 to +100):
        #   Negative = danger (widen/pause)
        #   Positive = safe (run/tighten)
        #   Zero = neutral
        #
        # Weights reflect reliability:
        #   RegimeAgent:    40%  — objective data, core
        #   FundingAgent:   25%  — proven professional signal
        #   WhaleAgent:     15%  — useful but spoofing risk
        #   SentimentAgent: 10%  — correlation breaks in extremes
        #   SocialAgent:     10% — noisy, black swan only
        #
        # Final score → action:
        #   < -60: PAUSE
        #   -60 to -20: WIDEN
        #   -20 to +20: RUN
        #   > +20: TIGHTEN

        reasons = []
        alerts = []
        scores = {}

        # --- RegimeAgent (40%) ---
        regime_state = regime.get("regime", "ranging")
        momentum = regime.get("momentum_30m", 0)
        vol_pct = regime.get("vol_percentile", 50)
        if regime_state == "volatile":
            scores["regime"] = -100
            reasons.append(f"[REGIME -100] Volatile (vol %ile={vol_pct}%)")
            alerts.append("HIGH_VOLATILITY")
        elif regime_state.startswith("trending"):
            scores["regime"] = -50
            reasons.append(f"[REGIME -50] {regime_state} (strength={regime.get('trend_strength')}, momentum={momentum:+.2f}%)")
        elif vol_pct < 30:
            scores["regime"] = 30
            reasons.append(f"[REGIME +30] Low vol ranging (vol %ile={vol_pct}%)")
        else:
            scores["regime"] = 10
            reasons.append(f"[REGIME +10] Ranging (vol %ile={vol_pct}%)")

        # --- FundingAgent (25%) ---
        pressure = funding.get("pressure", "neutral")
        if pressure == "long_crowded":
            scores["funding"] = -60
            reasons.append(f"[FUNDING -60] Longs crowded (premium={funding.get('premium_pct'):.3f}%)")
            alerts.append("LONG_CROWDED")
        elif pressure == "short_crowded":
            scores["funding"] = -40
            reasons.append(f"[FUNDING -40] Shorts crowded (discount={funding.get('premium_pct'):.3f}%)")
        elif pressure in ("slight_long", "slight_short"):
            scores["funding"] = -10
            reasons.append(f"[FUNDING -10] Slight {pressure}")
        else:
            scores["funding"] = 10
            reasons.append(f"[FUNDING +10] Neutral")

        # --- WhaleAgent (15%) ---
        whale_bias = whale.get("whale_bias", "neutral")
        if whale.get("wall_eaten"):
            scores["whale"] = -80
            wall_event = whale.get("wall_disappeared", "")
            reasons.append(f"[WHALE -80] Wall eaten ({wall_event}) — strong directional move")
            alerts.append(f"WALL_EATEN")
        elif whale.get("wall_pulled"):
            scores["whale"] = -20
            reasons.append(f"[WHALE -20] Wall pulled — possible spoof")
            alerts.append("POSSIBLE_SPOOF")
        elif whale_bias == "sell_heavy":
            scores["whale"] = -15
            reasons.append(f"[WHALE -15] Sell-heavy (sell ${whale.get('large_sell_volume',0):.0f} vs buy ${whale.get('large_buy_volume',0):.0f})")
        elif whale_bias == "buy_heavy":
            scores["whale"] = 15
            reasons.append(f"[WHALE +15] Buy-heavy (buy ${whale.get('large_buy_volume',0):.0f} vs sell ${whale.get('large_sell_volume',0):.0f})")
        else:
            scores["whale"] = 0

        if whale.get("buy_wall"):
            reasons.append(f"[WHALE] Buy wall @${whale['buy_wall']['price']:.2f} (ref)")
        if whale.get("sell_wall"):
            reasons.append(f"[WHALE] Sell wall @${whale['sell_wall']['price']:.2f} (ref)")

        # --- SentimentAgent (10%) ---
        sent = sentiment.get("sentiment", "neutral")
        conf = sentiment.get("confidence", 0)
        if sent == "bearish" and conf > 0.7:
            scores["sentiment"] = -40
            reasons.append(f"[SENTIMENT -40] Bearish ({conf:.0%})")
        elif sent == "bearish":
            scores["sentiment"] = -15
            reasons.append(f"[SENTIMENT -15] Slightly bearish ({conf:.0%})")
        elif sent == "bullish" and conf > 0.7:
            scores["sentiment"] = 30
            reasons.append(f"[SENTIMENT +30] Bullish ({conf:.0%})")
        elif sent == "bullish":
            scores["sentiment"] = 10
            reasons.append(f"[SENTIMENT +10] Slightly bullish ({conf:.0%})")
        else:
            scores["sentiment"] = 0

        if sentiment.get("divergence"):
            alerts.append(f"DIVERGENCE_{sentiment['divergence'].upper()}")
            reasons.append(f"[SENTIMENT] SOL/{sentiment['divergence']} divergence from BTC")

        # --- SocialAgent (10%) ---
        social_emergency = social.get("emergency")
        fng = social.get("fear_greed_index", 50)
        if social_emergency == "BLACK_SWAN":
            scores["social"] = -50
            alerts.append("BLACK_SWAN_ADVISORY")
            for post in social.get("black_swan_posts", [])[:2]:
                reasons.append(f"[SOCIAL] BLACK SWAN: {post[:50]}")
        elif fng <= 10:
            scores["social"] = -30
            reasons.append(f"[SOCIAL -30] Extreme Fear (F&G={fng})")
        elif fng <= 25:
            scores["social"] = -10
            reasons.append(f"[SOCIAL -10] Fear (F&G={fng})")
        elif fng >= 75:
            scores["social"] = -15
            reasons.append(f"[SOCIAL -15] Extreme Greed (F&G={fng}) — reversal risk")
        else:
            scores["social"] = 0

        if social_emergency == "SHILL_PUMP":
            alerts.append("SHILL_PUMP_ADVISORY")

        # === WEIGHTED FINAL SCORE ===
        weights = {"regime": 0.40, "funding": 0.25, "whale": 0.15, "sentiment": 0.10, "social": 0.10}
        final_score = sum(scores.get(k, 0) * w for k, w in weights.items())
        final_score = round(final_score, 1)

        # Score → Action
        if final_score < -60:
            action = "pause"
        elif final_score < -20:
            action = "widen"
        elif final_score > 5:
            action = "tighten"
        else:
            action = "run"

        reasons.insert(0, f"=== SCORE: {final_score} → {action.upper()} ===")
        score_detail = " | ".join(f"{k}={v:+d}" for k, v in scores.items())
        reasons.insert(1, f"Breakdown: {score_detail}")

        if social.get("reddit_activity_spike"):
            alerts.append("REDDIT_SPIKE")
            reasons.append("Reddit activity spike — unusual volume of posts")

        if social.get("fear_greed_spike"):
            alerts.append("FNG_SPIKE")
            reasons.append(f"Fear & Greed sudden change")

        # Social sentiment
        social_mood = social.get("overall_social", "neutral")
        fng = social.get("fear_greed_index", 50)
        fng_label = social.get("fear_greed_label", "Neutral")
        reasons.append(f"Fear & Greed: {fng} ({fng_label})")

        if fng <= 20:
            # Extreme fear — usually a buy signal, but widen grid for safety
            if action == "run":
                action = "widen"
            reasons.append("Extreme fear — widening for safety")
            alerts.append("EXTREME_FEAR")
        elif fng >= 80:
            alerts.append("EXTREME_GREED")
            reasons.append("Extreme greed — reversal risk")

        if social_mood == "bearish" and social.get("overall_score", 0) < -25:
            reasons.append(f"Social bearish (score={social.get('overall_score',0):+.0f})")
            if action == "run":
                action = "widen"
        elif social_mood == "bullish" and social.get("overall_score", 0) > 25:
            reasons.append(f"Social bullish (score={social.get('overall_score',0):+.0f})")

        # Reddit notable posts
        reddit_posts = social.get("reddit_top_posts", [])
        bearish_posts = [p for p in reddit_posts if p.get("sentiment", 0) < -0.3 and p.get("score", 0) > 10]
        if bearish_posts:
            reasons.append(f"Reddit alert: {bearish_posts[0]['title'][:50]}")

        # Spacing suggestion
        spacing_mult = regime.get("suggested_spacing_mult", 1.0)
        base_spacing = 0.004
        suggested_spacing = round(base_spacing * spacing_mult, 4)

        # Levels suggestion
        suggested_levels = 10
        if action == "widen":
            suggested_levels = 8
        elif action == "tighten":
            suggested_levels = 12

        # Wall-bounded grid: if valid, override spacing to fit within walls
        wall_valid = whale.get("wall_range_valid", False)
        wall_low = whale.get("wall_low", 0)
        wall_high = whale.get("wall_high", 0)
        wall_range_pct = whale.get("wall_range_pct", 0)

        # Wall disappearance — emergency: fall back to normal grid
        wall_gone = whale.get("wall_disappeared")
        if wall_gone in ("buy", "sell"):
            action = "widen"
            alerts.append(f"WALL_GONE: {wall_gone} wall disappeared")
            reasons.append(f"Wall removed — falling back to wide grid for safety")

        elif wall_valid and wall_range_pct > 0.3 and action != "pause":
            # Only use wall grid if walls are stable (4+ consecutive checks)
            wall_stable = whale.get("wall_stable", False)
            if wall_stable:
                half_range = (wall_high - wall_low) / 2
                optimal_levels = min(6, max(3, int(wall_range_pct / 0.2)))
                wall_spacing = half_range / optimal_levels
                wall_spacing_pct = wall_spacing / ((wall_low + wall_high) / 2)
                suggested_spacing = round(wall_spacing_pct, 4)
                suggested_levels = optimal_levels
                reasons.append(
                    f"Wall-bounded grid: ${wall_low:.2f}-${wall_high:.2f} "
                    f"({wall_range_pct:.1f}%), {optimal_levels} levels, "
                    f"stable {whale.get('wall_stable_count', 0)} checks"
                )
                action = "wall_grid"
            else:
                reasons.append(
                    f"Walls found ${wall_low:.2f}-${wall_high:.2f} "
                    f"but not stable yet ({whale.get('wall_stable_count', 0)}/4)"
                )

        state = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "sentiment": sent,
            "sentiment_confidence": sentiment.get("confidence", 0.5),
            "funding_pressure": funding.get("premium_pct", 0),
            "whale_bias": whale_bias,
            "regime": regime_state,
            "regime_vol_percentile": regime.get("vol_percentile", 50),
            "regime_trend_strength": regime.get("trend_strength", 0),
            "suggested_spacing_pct": suggested_spacing,
            "suggested_levels": suggested_levels,
            "support_level": whale.get("support_level", 0),
            "resistance_level": whale.get("resistance_level", 0),
            "wall_range_valid": wall_valid,
            "wall_low": wall_low,
            "wall_high": wall_high,
            "wall_range_pct": wall_range_pct,
            "wall_buy_strength": whale.get("wall_buy_strength", 0),
            "wall_sell_strength": whale.get("wall_sell_strength", 0),
            "fear_greed_index": fng,
            "fear_greed_label": fng_label,
            "social_mood": social_mood,
            "social_score": social.get("overall_score", 0),
            "reasons": reasons,
            "alerts": alerts,
            "raw": {
                "sentiment": sentiment,
                "funding": funding,
                "whale": whale,
                "regime": regime,
                "social": social,
            },
        }

        return state

    def write_state(self, state):
        """写入共享状态文件"""
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Monitor] 写入状态文件失败: {e}")


def main():
    # Exchange setup
    exchange = ccxt.coinbase({"enableRateLimit": True})
    exchange.load_markets()
    logger.info("Coinbase public markets loaded")

    cfm_exchange = None
    if os.environ.get("CB_API_KEY"):
        cfm_exchange = ccxt.coinbaseadvanced({
            "apiKey": os.environ.get("CB_API_KEY", ""),
            "secret": os.environ.get("CB_API_SECRET", ""),
            "enableRateLimit": True,
        })
        cfm_exchange.load_markets()
        logger.info("Coinbase Advanced loaded")

    harness = MonitorHarness(exchange, cfm_exchange)

    logger.info("=" * 60)
    logger.info("  SOL Monitor Team — Harness")
    logger.info("  Agents: Sentiment, Funding, Whale, Regime")
    logger.info(f"  Output: {STATE_FILE}")
    logger.info("  Refresh: 60s")
    logger.info("=" * 60)

    cycle = 0
    while running:
        try:
            cycle += 1
            state = harness.run_cycle()
            harness.write_state(state)

            action_emoji = {"run": "RUN", "pause": "PAUSE", "widen": "WIDEN", "tighten": "TIGHT"}
            logger.info(
                f"[Monitor] #{cycle} | {action_emoji.get(state['action'], '?')} | "
                f"sentiment={state['sentiment']} | regime={state['regime']} | "
                f"whale={state['whale_bias']} | "
                f"spacing={state['suggested_spacing_pct']*100:.2f}%"
            )
            if state["reasons"]:
                logger.info(f"  reasons: {'; '.join(state['reasons'])}")
            if state["alerts"]:
                logger.warning(f"  alerts: {', '.join(state['alerts'])}")

            time.sleep(60)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"[Monitor] 异常: {e}", exc_info=True)
            time.sleep(10)

    logger.info("[Monitor] 已停止")


if __name__ == "__main__":
    main()
