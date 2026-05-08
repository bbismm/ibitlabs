"""
Order Agent — fetches open orders (spot + futures) and positions.
TTL: 15s
"""

from .base_agent import BaseAgent


class OrderAgent(BaseAgent):
    def __init__(self, spot_exchange, futures_exchange, config):
        super().__init__("OrderAgent", ttl_seconds=15)
        self.spot_exchange = spot_exchange
        self.futures_exchange = futures_exchange
        self.config = config

    def fetch(self) -> dict:
        data = {"spot_orders": [], "futures_orders": [], "positions": []}

        # Spot orders (Coinbase Advanced Trade)
        if self.futures_exchange:
            try:
                resp = self.futures_exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                    "order_status": "OPEN",
                    "product_type": "SPOT",
                    "limit": "50",
                })
                for o in resp.get("orders", []):
                    cfg = o.get("order_configuration", {}).get("limit_limit_gtc", {})
                    price = float(cfg.get("limit_price", 0) or 0)
                    qty = float(cfg.get("base_size", 0) or 0)
                    created = o.get("created_time", "")
                    try:
                        from datetime import datetime
                        utc_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        time_str = utc_dt.astimezone().strftime("%m-%d %H:%M:%S")
                    except Exception:
                        time_str = ""
                    data["spot_orders"].append({
                        "symbol": o.get("product_id", ""),
                        "side": o.get("side", ""),
                        "price": price,
                        "quantity": qty,
                        "value": price * qty,
                        "order_id": o.get("order_id", ""),
                        "time": time_str,
                    })
            except Exception:
                pass

        if not self.futures_exchange:
            return data

        # Futures orders (Coinbase CFM)
        try:
            resp = self.futures_exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                "order_status": "OPEN",
                "product_type": "FUTURE",
                "limit": "50",
            })
            for o in resp.get("orders", []):
                cfg = o.get("order_configuration", {}).get("limit_limit_gtc", {})
                price = float(cfg.get("limit_price", 0) or 0)
                qty = float(cfg.get("base_size", 0) or 0)
                data["futures_orders"].append({
                    "symbol": o.get("product_id", ""),
                    "side": o.get("side", ""),
                    "price": price,
                    "quantity": qty,
                    "value": price * qty,
                    "order_id": o.get("order_id", ""),
                })
        except Exception:
            pass

        # Futures positions — try CFM API first, then IntxPositions as fallback
        try:
            resp = self.futures_exchange.v3PrivateGetBrokerageCfmPositions()
            for pos in resp.get("positions", []):
                qty = float(pos.get("number_of_contracts", 0) or 0)
                if qty == 0:
                    continue
                data["positions"].append({
                    "symbol": pos.get("product_id", ""),
                    "side": pos.get("side", "LONG" if qty > 0 else "SHORT"),
                    "contracts": abs(qty),
                    "entry_price": float(pos.get("avg_entry_price", 0) or 0),
                    "unrealized_pnl": float(pos.get("unrealized_pnl", 0) or 0),
                })
        except Exception:
            # Fallback: IntxPositions (coinbaseadvanced format)
            try:
                resp = self.futures_exchange.v3PrivateGetBrokerageIntxPositions()
                for pos in resp.get("positions", []):
                    qty = float(pos.get("number_of_contracts", 0) or 0)
                    if qty != 0:
                        data["positions"].append({
                            "symbol": pos.get("product_id", ""),
                            "side": "LONG" if qty > 0 else "SHORT",
                            "contracts": abs(qty),
                            "entry_price": float(pos.get("entry_vwap", {}).get("value", 0) or 0),
                            "unrealized_pnl": float(pos.get("unrealized_pnl", {}).get("value", 0) or 0),
                        })
            except Exception:
                pass
        except Exception:
            pass

        return data
