"""
Autopilot Account Agent — fetches a Grid Autopilot customer's balance and positions.
One instance per customer, using their own authenticated exchange.
TTL: 30s
"""

import logging

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AutopilotAccountAgent(BaseAgent):
    def __init__(self, customer_id: str, exchange):
        super().__init__(f"AutopilotAccount-{customer_id}", ttl_seconds=30)
        self.customer_id = customer_id
        self.exchange = exchange

    def fetch(self) -> dict:
        data = {
            "customer_id": self.customer_id,
            "total_balance": 0,
            "buying_power": 0,
            "positions": [],
            "exposure": 0,
        }
        try:
            # Coinbase CFM balance
            resp = self.exchange.v3PrivateGetBrokerageCfmBalanceSummary()
            summary = resp.get("balance_summary", {})
            data["total_balance"] = float(summary.get("total_balance", 0))
            data["buying_power"] = float(summary.get("buying_power", 0))
        except Exception as e:
            logger.warning(f"[{self.name}] balance fetch failed: {e}")

        try:
            # Positions
            resp = self.exchange.v3PrivateGetBrokerageCfmPositions()
            positions = resp.get("positions", [])
            for pos in positions:
                size = float(pos.get("number_of_contracts", 0))
                if size != 0:
                    data["positions"].append({
                        "symbol": pos.get("product_id", ""),
                        "size": size,
                        "side": pos.get("side", ""),
                        "entry_price": float(pos.get("avg_entry_price", 0)),
                        "unrealized_pnl": float(pos.get("unrealized_pnl", 0)),
                    })
            data["exposure"] = sum(abs(p["size"] * p["entry_price"]) for p in data["positions"])
        except Exception as e:
            logger.warning(f"[{self.name}] positions fetch failed: {e}")

        return data
