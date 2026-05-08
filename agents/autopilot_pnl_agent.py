"""
Autopilot PnL Agent — calculates P&L and profit share for a Grid Autopilot customer.
Reads from autopilot.db. Implements high-water mark for profit share.
TTL: 60s
"""

import logging

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AutopilotPnLAgent(BaseAgent):
    def __init__(self, customer_id: str, autopilot_db):
        super().__init__(f"AutopilotPnL-{customer_id}", ttl_seconds=60)
        self.customer_id = customer_id
        self.copy_db = autopilot_db

    def fetch(self) -> dict:
        pnl_data = self.copy_db.get_customer_pnl(self.customer_id)
        customer = self.copy_db.get_customer(self.customer_id)
        recent_trades = self.copy_db.get_customer_trades(self.customer_id, limit=20)

        total_pnl = pnl_data.get("total_pnl", 0)
        total_trades = pnl_data.get("total_trades", 0)
        profit_share_pct = customer.get("profit_share_pct", 0.20) if customer else 0.20
        high_water_mark = customer.get("high_water_mark", 0) if customer else 0

        # Profit share: 20% of gains above high-water mark
        profit_share = 0
        if total_pnl > high_water_mark:
            profit_share = (total_pnl - high_water_mark) * profit_share_pct

        net_pnl = total_pnl - profit_share

        return {
            "customer_id": self.customer_id,
            "total_pnl": round(total_pnl, 2),
            "total_trades": total_trades,
            "profit_share_pct": profit_share_pct,
            "profit_share": round(profit_share, 2),
            "net_pnl": round(net_pnl, 2),
            "high_water_mark": round(high_water_mark, 2),
            "recent_trades": recent_trades,
            "capital_snapshot": customer.get("capital_snapshot", 0) if customer else 0,
        }
