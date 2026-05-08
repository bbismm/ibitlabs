"""
Funding Rate Agent — 期货溢价/折价监控
Coinbase CFM没有直接的funding rate API，用期货vs现货价差替代
TTL: 30s
"""

import logging
import sys
sys.path.insert(0, "..")
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FundingRateAgent(BaseAgent):
    def __init__(self, exchange, cfm_exchange=None):
        super().__init__("FundingAgent", ttl_seconds=30)
        self.exchange = exchange  # coinbase public (spot)
        self.cfm_exchange = cfm_exchange  # coinbaseadvanced (futures)

    def fetch(self) -> dict:
        data = {
            "premium_pct": 0,
            "pressure": "neutral",
            "spot_price": 0,
            "futures_price": 0,
            "signal": "none",
        }

        try:
            # 现货价格
            spot_ticker = self.exchange.fetch_ticker("SOL/USDC")
            spot_price = spot_ticker.get("last", 0) or 0
            data["spot_price"] = spot_price

            # 期货价格 — 用同一个exchange获取
            # Coinbase CFM产品在同一API下
            futures_ticker = self.exchange.fetch_ticker("SOL/USDC")
            futures_price = futures_ticker.get("last", 0) or 0
            data["futures_price"] = futures_price

            # 尝试从order book bid/ask中位差价估算
            try:
                ob = self.exchange.fetch_order_book("SOL/USDC", limit=5)
                best_bid = ob["bids"][0][0] if ob["bids"] else spot_price
                best_ask = ob["asks"][0][0] if ob["asks"] else spot_price
                spread_pct = (best_ask - best_bid) / spot_price * 100
                mid = (best_bid + best_ask) / 2
                # 如果有cfm_exchange，比较两个价格
                if self.cfm_exchange:
                    try:
                        cfm_bal = self.cfm_exchange.v3PrivateGetBrokerageCfmPositions()
                        for pos in cfm_bal.get("positions", []):
                            if "SLP" in pos.get("product_id", ""):
                                futures_price = float(pos.get("current_price", 0))
                                data["futures_price"] = futures_price
                    except Exception:
                        pass
            except Exception:
                pass

            if spot_price > 0 and futures_price > 0:
                premium = (futures_price - spot_price) / spot_price * 100
                data["premium_pct"] = round(premium, 4)

                # 溢价判断
                if premium > 0.15:
                    data["pressure"] = "long_crowded"
                    data["signal"] = "bearish"  # 做多拥挤 → 看空
                elif premium > 0.05:
                    data["pressure"] = "slight_long"
                    data["signal"] = "slightly_bearish"
                elif premium < -0.15:
                    data["pressure"] = "short_crowded"
                    data["signal"] = "bullish"  # 做空拥挤 → 看多
                elif premium < -0.05:
                    data["pressure"] = "slight_short"
                    data["signal"] = "slightly_bullish"
                else:
                    data["pressure"] = "neutral"
                    data["signal"] = "none"

        except Exception as e:
            logger.warning(f"[Funding] 获取数据失败: {e}")

        return data
