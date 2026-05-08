"""
Trading Safety Agent — Balance verification, position anomaly detection,
unauthorized order detection.
TTL: 60s
"""

import time
import logging
import sys
sys.path.insert(0, "..")
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class TradingSafetyAgent(BaseAgent):
    def __init__(self, exchange):
        super().__init__("TradingSafetyAgent", ttl_seconds=60)
        self.exchange = exchange
        self.prev_balance = None
        self.prev_positions = None
        self.prev_order_count = None
        self.balance_history = []  # (timestamp, balance) for trend

    def fetch(self) -> dict:
        data = {
            "balance_ok": True,
            "positions_ok": True,
            "orders_ok": True,
            "current_balance": 0,
            "balance_change": 0,
            "balance_change_pct": 0,
            "position_count": 0,
            "position_exposure": 0,
            "order_count": 0,
            "issues": [],
            "alerts": [],
            "auto_action": None,  # None = no action, "pause_scalper" = kill scalper, "emergency_flat" = close all
        }

        # 1. Balance check
        try:
            bal = self.exchange.v3PrivateGetBrokerageCfmBalanceSummary()
            bs = bal.get("balance_summary", {})
            # Same formula as dashboard: buying_power + orders_hold + margin + unrealized
            buying_power = float(bs.get("futures_buying_power", {}).get("value", 0))
            orders_hold = abs(float(bs.get("total_open_orders_hold_amount", {}).get("value", 0)))
            init_margin = float(bs.get("initial_margin", {}).get("value", 0))
            unrealized = float(bs.get("unrealized_pnl", {}).get("value", 0))
            current = buying_power + orders_hold + init_margin + unrealized
            data["current_balance"] = current

            self.balance_history.append((time.time(), current))
            # Keep 1 hour of history
            cutoff = time.time() - 3600
            self.balance_history = [(t, b) for t, b in self.balance_history if t > cutoff]

            if self.prev_balance is not None:
                change = current - self.prev_balance
                change_pct = (change / self.prev_balance * 100) if self.prev_balance > 0 else 0
                data["balance_change"] = round(change, 2)
                data["balance_change_pct"] = round(change_pct, 2)

                # Alert: balance dropped more than 5% since last check
                if change_pct < -5 and len(self.balance_history) > 10:
                    data["balance_ok"] = False
                    data["alerts"].append(f"BALANCE DROP: ${change:+.2f} ({change_pct:+.1f}%)")
                    data["auto_action"] = "pause_scalper"
                    logger.warning(f"[Security] Balance dropped {change_pct:.1f}% — AUTO PAUSING SCALPER")

                # Alert: balance dropped more than 10% in 1 hour — emergency
                if len(self.balance_history) > 10:
                    oldest = self.balance_history[0][1]
                    hour_change_pct = (current - oldest) / oldest * 100 if oldest > 0 else 0
                    if hour_change_pct < -10:
                        data["balance_ok"] = False
                        data["alerts"].append(f"1H BALANCE DROP: {hour_change_pct:+.1f}%")
                        data["auto_action"] = "emergency_flat"
                        logger.warning(f"[Security] 1h balance drop {hour_change_pct:.1f}% — EMERGENCY FLAT")

            self.prev_balance = current
        except Exception as e:
            data["issues"].append(f"Balance check failed: {str(e)[:60]}")

        # 2. Position check
        try:
            resp = self.exchange.v3PrivateGetBrokerageCfmPositions()
            positions = resp.get("positions", [])
            total_exposure = 0

            for pos in positions:
                qty = float(pos.get("number_of_contracts", 0) or 0)
                price = float(pos.get("current_price", 0) or 0)
                exposure = abs(qty) * price
                total_exposure += exposure

                # Alert: unexpected large position (> $500) — auto pause
                if exposure > 500:
                    data["positions_ok"] = False
                    data["alerts"].append(
                        f"LARGE POSITION: {pos.get('product_id')} "
                        f"{qty} contracts = ${exposure:.0f}"
                    )
                    data["auto_action"] = "pause_scalper"

                # Alert: unrealized loss > $50
                unrealized = float(pos.get("unrealized_pnl", 0) or 0)
                if unrealized < -50:
                    data["alerts"].append(
                        f"HEAVY LOSS: {pos.get('product_id')} "
                        f"unrealized ${unrealized:.2f}"
                    )

            data["position_count"] = len([p for p in positions if float(p.get("number_of_contracts", 0) or 0) != 0])
            data["position_exposure"] = round(total_exposure, 2)

            # Alert: position count changed unexpectedly
            if self.prev_positions is not None:
                if data["position_count"] != self.prev_positions:
                    data["issues"].append(
                        f"Position count changed: {self.prev_positions} -> {data['position_count']}"
                    )
            self.prev_positions = data["position_count"]

        except Exception as e:
            data["issues"].append(f"Position check failed: {str(e)[:60]}")

        # 3. Order check
        try:
            resp = self.exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                "order_status": "OPEN",
                "product_type": "FUTURE",
                "limit": "100",
            })
            orders = resp.get("orders", [])
            data["order_count"] = len(orders)

            # Alert: too many open orders (> 30)
            if len(orders) > 30:
                data["orders_ok"] = False
                data["alerts"].append(f"TOO MANY ORDERS: {len(orders)} open")

            # Alert: order count spike (doubled since last check)
            if self.prev_order_count is not None:
                if len(orders) > self.prev_order_count * 2 and len(orders) > 10:
                    data["orders_ok"] = False
                    data["alerts"].append(
                        f"ORDER SPIKE: {self.prev_order_count} -> {len(orders)}"
                    )

            # Alert: orders on unexpected products
            expected_products = {"SLP-20DEC30-CDE"}
            for o in orders:
                pid = o.get("product_id", "")
                if pid and pid not in expected_products:
                    data["orders_ok"] = False
                    data["alerts"].append(f"UNEXPECTED ORDER: {pid}")
                    break

            self.prev_order_count = len(orders)

        except Exception as e:
            data["issues"].append(f"Order check failed: {str(e)[:60]}")

        # Summary
        all_ok = data["balance_ok"] and data["positions_ok"] and data["orders_ok"]
        if not data["issues"] and not data["alerts"]:
            data["status"] = "ALL CLEAR"
        elif data["alerts"]:
            data["status"] = "ALERT"
        else:
            data["status"] = "WARNING"

        return data
