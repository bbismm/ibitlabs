"""
Market Sentiment Agent — BTC/ETH/SOL 相关性 + 多空情绪
TTL: 60s
"""

import logging
import sys
sys.path.insert(0, "..")
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class MarketSentimentAgent(BaseAgent):
    def __init__(self, exchange):
        super().__init__("SentimentAgent", ttl_seconds=60)
        self.exchange = exchange

    def fetch(self) -> dict:
        data = {
            "sentiment": "neutral",
            "confidence": 0.5,
            "btc_change_5m": 0, "eth_change_5m": 0, "sol_change_5m": 0,
            "sol_btc_correlation": 0,
            "divergence": None,
            "order_book_ratio": 1.0,
        }

        try:
            # 获取BTC/ETH/SOL最近12根5分钟K线 (1小时)
            btc_ohlcv = self.exchange.fetch_ohlcv("BTC/USDC", "5m", limit=12)
            eth_ohlcv = self.exchange.fetch_ohlcv("ETH/USDC", "5m", limit=12)
            sol_ohlcv = self.exchange.fetch_ohlcv("SOL/USDC", "5m", limit=12)

            if len(btc_ohlcv) < 6 or len(sol_ohlcv) < 6:
                return data

            btc_closes = [c[4] for c in btc_ohlcv]
            eth_closes = [c[4] for c in eth_ohlcv]
            sol_closes = [c[4] for c in sol_ohlcv]

            # 5分钟变化率
            data["btc_change_5m"] = (btc_closes[-1] / btc_closes[-2] - 1) * 100
            data["eth_change_5m"] = (eth_closes[-1] / eth_closes[-2] - 1) * 100
            data["sol_change_5m"] = (sol_closes[-1] / sol_closes[-2] - 1) * 100

            # SOL vs BTC 1小时相关性 (简化: 收益率方向一致性)
            btc_returns = [btc_closes[i] / btc_closes[i-1] - 1 for i in range(1, len(btc_closes))]
            sol_returns = [sol_closes[i] / sol_closes[i-1] - 1 for i in range(1, len(sol_closes))]
            min_len = min(len(btc_returns), len(sol_returns))
            same_dir = sum(1 for i in range(min_len) if btc_returns[i] * sol_returns[i] > 0)
            data["sol_btc_correlation"] = same_dir / min_len if min_len > 0 else 0

            # 背离检测: BTC涨但SOL没跟
            btc_1h_change = (btc_closes[-1] / btc_closes[0] - 1) * 100
            sol_1h_change = (sol_closes[-1] / sol_closes[0] - 1) * 100

            if btc_1h_change > 0.5 and sol_1h_change < -0.2:
                data["divergence"] = "bearish"  # BTC涨SOL跌 → SOL弱势
            elif btc_1h_change < -0.5 and sol_1h_change > 0.2:
                data["divergence"] = "bullish"  # BTC跌SOL涨 → SOL强势

            # 买卖盘深度比 (order book)
            try:
                ob = self.exchange.fetch_order_book("SOL/USDC", limit=20)
                bid_depth = sum(b[1] * b[0] for b in ob["bids"][:10])
                ask_depth = sum(a[1] * a[0] for a in ob["asks"][:10])
                data["order_book_ratio"] = round(bid_depth / ask_depth, 2) if ask_depth > 0 else 1.0
            except Exception:
                pass

            # 综合情绪判断
            bullish_score = 0
            bearish_score = 0

            if sol_1h_change > 1:
                bullish_score += 2
            elif sol_1h_change > 0.3:
                bullish_score += 1
            if sol_1h_change < -1:
                bearish_score += 2
            elif sol_1h_change < -0.3:
                bearish_score += 1

            if data["divergence"] == "bullish":
                bullish_score += 2
            elif data["divergence"] == "bearish":
                bearish_score += 2

            if data["order_book_ratio"] > 1.3:
                bullish_score += 1
            elif data["order_book_ratio"] < 0.7:
                bearish_score += 1

            if bullish_score > bearish_score + 1:
                data["sentiment"] = "bullish"
                data["confidence"] = min(0.9, 0.5 + bullish_score * 0.1)
            elif bearish_score > bullish_score + 1:
                data["sentiment"] = "bearish"
                data["confidence"] = min(0.9, 0.5 + bearish_score * 0.1)
            else:
                data["sentiment"] = "neutral"
                data["confidence"] = 0.5

        except Exception as e:
            logger.warning(f"[Sentiment] 获取数据失败: {e}")

        return data
