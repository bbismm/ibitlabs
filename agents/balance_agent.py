"""
Balance Agent — fetches spot (HTX) + futures (Coinbase CFM) balances.
TTL: 30s
"""

from .base_agent import BaseAgent


class BalanceAgent(BaseAgent):
    def __init__(self, spot_exchange, futures_exchange):
        super().__init__("BalanceAgent", ttl_seconds=30)
        self.spot_exchange = spot_exchange
        self.futures_exchange = futures_exchange

    def fetch(self) -> dict:
        data = {
            "balances": [],
            "futures_balance": {
                "total_balance": 0, "cash_balance": 0, "buying_power": 0,
                "orders_hold": 0, "unrealized_pnl": 0, "daily_pnl": 0,
            },
        }

        # Spot balances (HTX)
        if self.spot_exchange:
            try:
                balance = self.spot_exchange.fetch_balance()
                for asset in ["USDT", "UNI", "BTC", "ETH", "SOL"]:
                    bal = balance.get(asset, {})
                    free = float(bal.get("free", 0)) if isinstance(bal, dict) else 0
                    used = float(bal.get("used", 0)) if isinstance(bal, dict) else 0
                    if free > 0 or used > 0:
                        data["balances"].append({
                            "asset": f"{asset} (HTX)",
                            "free": free, "used": used, "total": free + used,
                        })
            except Exception:
                pass

        # Spot balances (Coinbase Advanced Trade — USD, USDC, SOL)
        if self.futures_exchange:
            try:
                accounts = self.futures_exchange.v3PrivateGetBrokerageAccounts({"limit": "100"})
                sol_price = 0
                try:
                    ticker = self.futures_exchange.fetch_ticker("SOL/USDC")
                    sol_price = float(ticker.get("last", 0))
                except Exception:
                    pass
                for acc in accounts.get("accounts", []):
                    cur = acc.get("currency", "")
                    avail = float(acc.get("available_balance", {}).get("value", 0) or 0)
                    hold = float(acc.get("hold", {}).get("value", 0) or 0)
                    total = avail + hold
                    if total < 0.0001:
                        continue
                    if cur == "SOL":
                        usd_val = total * sol_price if sol_price > 0 else 0
                        data["balances"].append({
                            "asset": "SOL",
                            "free": avail, "used": hold, "total": total,
                            "usd_value": usd_val, "price": sol_price,
                        })
                    elif cur in ("USD", "USDC"):
                        data["balances"].append({
                            "asset": cur,
                            "free": avail, "used": hold, "total": total,
                            "usd_value": total, "price": 1.0,
                        })
            except Exception:
                pass

            try:
                bal = self.futures_exchange.v3PrivateGetBrokerageCfmBalanceSummary()
                bs = bal.get("balance_summary", {})
                cfm_cash = float(bs.get("cfm_usd_balance", {}).get("value", 0))
                orders_hold = abs(float(bs.get("total_open_orders_hold_amount", {}).get("value", 0)))
                initial_margin = float(bs.get("initial_margin", {}).get("value", 0))
                unrealized_pnl = float(bs.get("unrealized_pnl", {}).get("value", 0))

                # Use portfolio breakdown API — exact same number as Coinbase page
                buying_power = float(bs.get("futures_buying_power", {}).get("value", 0))
                spot_usdc = buying_power
                try:
                    portfolio = self.futures_exchange.v3PrivateGetBrokeragePortfoliosPortfolioUuid({
                        "portfolio_uuid": "691e8414-c649-50f3-ab61-687ac553ff68",
                    })
                    grand_total = float(
                        portfolio.get("breakdown", {})
                        .get("portfolio_balances", {})
                        .get("total_balance", {})
                        .get("value", 0)
                    )
                except Exception:
                    grand_total = buying_power + orders_hold + initial_margin + unrealized_pnl

                data["futures_balance"] = {
                    "total_balance": grand_total,
                    "cash_balance": cfm_cash,
                    "spot_usdc": spot_usdc,
                    "buying_power": float(bs.get("futures_buying_power", {}).get("value", 0)),
                    "orders_hold": orders_hold,
                    "initial_margin": initial_margin,
                    "unrealized_pnl": unrealized_pnl,
                    "daily_pnl": float(bs.get("daily_realized_pnl", {}).get("value", 0))
                                 + unrealized_pnl
                                 + float(bs.get("funding_pnl", {}).get("value", 0)),
                }
            except Exception:
                pass

        return data
