"""
Trade Agent — fetches recent trades, PnL, win rate, cooldowns from SQLite.
TTL: 60s (DB data changes less frequently)
"""

import time

from .base_agent import BaseAgent


class TradeAgent(BaseAgent):
    def __init__(self, spot_db, futures_db, spot_exchange, config, futures_exchange=None):
        super().__init__("TradeAgent", ttl_seconds=60)
        self.spot_db = spot_db
        self.futures_db = futures_db
        self.spot_exchange = spot_exchange
        self.futures_exchange = futures_exchange
        self.config = config
        from state_db import StateDB
        self.scalper_db = StateDB(config.scalper_db_path)

    def _read_trades(self, db, limit=10):
        trades = []
        try:
            conn = db._connect()
            rows = conn.execute("SELECT * FROM trade_log ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            for r in rows:
                d = dict(r)
                trades.append({
                    "symbol": d["symbol"], "side": d["side"], "price": d["price"],
                    "quantity": d["quantity"], "pnl": d["pnl"],
                    "time": time.strftime("%m-%d %H:%M:%S", time.localtime(d["timestamp"])),
                })
            conn.close()
        except Exception:
            pass
        return trades

    def _read_exchange_fills(self, product_type="FUTURE", limit=20):
        """Read actual filled orders from Coinbase API — source of truth."""
        trades = []
        if not self.futures_exchange:
            return trades
        try:
            resp = self.futures_exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                "order_status": "FILLED",
                "product_type": product_type,
                "limit": str(limit),
            })
            for o in resp.get("orders", []):
                price = float(o.get("average_filled_price", 0) or 0)
                qty = float(o.get("filled_size", 0) or 0)
                if price == 0:
                    cfg = o.get("order_configuration", {}).get("limit_limit_gtc", {})
                    price = float(cfg.get("limit_price", 0) or 0)
                    qty = float(cfg.get("base_size", 0) or 0)
                created = o.get("created_time", "")
                try:
                    from datetime import datetime
                    utc_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    local_dt = utc_dt.astimezone()
                    time_str = local_dt.strftime("%m-%d %H:%M:%S")
                except Exception:
                    time_str = created[:19]
                trades.append({
                    "symbol": o.get("product_id", ""),
                    "side": o.get("side", ""),
                    "price": price,
                    "quantity": qty,
                    "pnl": 0,
                    "time": time_str,
                })
        except Exception:
            pass
        return trades

    def fetch(self) -> dict:
        data = {
            "spot_trades": [], "futures_trades": [],
            "spot_pnl": 0, "futures_pnl": 0,
            "performance": {"total_trades": 0, "win_rate": 0, "avg_pnl": 0},
            "cooling": [],
        }

        # Spot trades — Coinbase API fills (source of truth)
        spot_fills = self._read_exchange_fills(product_type="SPOT", limit=30)
        db_spot = self._read_trades(self.spot_db) + self._read_trades(self.scalper_db)
        seen_spot = {t["time"] for t in spot_fills}
        for t in db_spot:
            if t["time"] not in seen_spot:
                spot_fills.append(t)
        data["spot_trades"] = sorted(spot_fills, key=lambda x: x["time"], reverse=True)[:50]
        data["spot_pnl"] = self.spot_db.get_total_pnl() + self.scalper_db.get_total_pnl()

        # Futures trades — exchange fills as primary, local DB as supplement
        exchange_fills = self._read_exchange_fills(product_type="FUTURE")
        db_trades = self._read_trades(self.futures_db)
        # Merge: exchange fills first, then any DB-only trades
        seen_times = {t["time"] for t in exchange_fills}
        for t in db_trades:
            if t["time"] not in seen_times:
                exchange_fills.append(t)
        data["futures_trades"] = sorted(exchange_fills, key=lambda x: x["time"], reverse=True)[:50]
        # Pull realized PnL directly from Coinbase — local DB always stores pnl=0
        futures_pnl = 0
        if self.futures_exchange:
            try:
                bal = self.futures_exchange.v3PrivateGetBrokerageCfmBalanceSummary()
                bs = bal.get("balance_summary", {})
                futures_pnl = float(bs.get("daily_realized_pnl", {}).get("value", 0) or 0)
            except Exception:
                futures_pnl = self.futures_db.get_total_pnl() + self.scalper_db.get_total_pnl()
        data["futures_pnl"] = futures_pnl

        # Win rate
        try:
            from risk_manager import RiskManager
            rm = RiskManager(self.spot_exchange, self.config, self.spot_db, None)
            data["performance"] = rm.get_performance()
        except Exception:
            pass

        # Cooldowns
        now = time.time()
        for db_inst in [self.spot_db, self.futures_db, self.scalper_db]:
            for c in db_inst.get_all_cooling():
                remaining_h = (c["end_time"] - now) / 3600
                if remaining_h > 0:
                    data["cooling"].append({
                        "symbol": c["symbol"],
                        "remaining_h": round(remaining_h, 1),
                    })

        return data
