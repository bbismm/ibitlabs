"""
Autopilot Execution Agent — detects new owner fills in scalper.db and replicates them
proportionally to the customer's exchange.
One instance per customer. TTL: 10s (matches scalper check interval).
"""

import sqlite3
import logging
from pathlib import Path

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

SCALPER_DB = Path(__file__).parent.parent / "scalper.db"


class AutopilotExecutionAgent(BaseAgent):
    def __init__(self, customer_id: str, exchange, autopilot_db, owner_capital: float):
        super().__init__(f"AutopilotExec-{customer_id}", ttl_seconds=10)
        self.customer_id = customer_id
        self.exchange = exchange
        self.copy_db = autopilot_db
        self.owner_capital = owner_capital
        self._last_trade_id = copy_db.get_last_copied_trade_id(customer_id)

    def fetch(self) -> dict:
        result = {
            "customer_id": self.customer_id,
            "new_copies": 0,
            "last_trade_id": self._last_trade_id,
            "errors": [],
        }

        # Get new fills from owner's scalper.db
        new_fills = self._get_new_fills()
        if not new_fills:
            return result

        # Get customer's current capital for proportional sizing
        customer_capital = self._get_customer_capital()
        if customer_capital <= 0:
            result["errors"].append("Customer capital is 0 — skipping")
            return result

        ratio = customer_capital / self.owner_capital if self.owner_capital > 0 else 0

        for fill in new_fills:
            try:
                customer_size = round(fill["size"] * ratio, 6)
                if customer_size <= 0:
                    continue

                # Place order on customer's exchange
                order = self.exchange.create_order(
                    symbol=fill["symbol"],
                    type="market",
                    side=fill["side"],
                    amount=customer_size,
                )

                # Record in copy_trading.db
                self.copy_db.record_copy_trade(
                    customer_id=self.customer_id,
                    owner_trade_id=fill["id"],
                    symbol=fill["symbol"],
                    side=fill["side"],
                    owner_size=fill["size"],
                    customer_size=customer_size,
                    price=fill["price"],
                    customer_order_id=order.get("id", ""),
                )
                result["new_copies"] += 1
                self._last_trade_id = fill["id"]
                logger.info(f"[{self.name}] Autopilot trade {fill['id']}: {fill['side']} {customer_size} {fill['symbol']}")

            except Exception as e:
                err = f"Failed to execute trade {fill['id']}: {e}"
                logger.error(f"[{self.name}] {err}")
                result["errors"].append(err)
                self.copy_db.record_risk_event(self.customer_id, "ORDER_FAILED", err)

        return result

    def _get_new_fills(self) -> list[dict]:
        """Read new fills from owner's scalper.db since last copied trade."""
        fills = []
        try:
            if not SCALPER_DB.exists():
                return fills
            conn = sqlite3.connect(str(SCALPER_DB))
            conn.row_factory = sqlite3.Row
            if self._last_trade_id:
                rows = conn.execute(
                    "SELECT * FROM trade_log WHERE id > ? ORDER BY id ASC",
                    (self._last_trade_id,),
                ).fetchall()
            else:
                # First run: don't copy old trades, just record the latest ID
                row = conn.execute("SELECT id FROM trade_log ORDER BY id DESC LIMIT 1").fetchone()
                if row:
                    self._last_trade_id = str(row["id"])
                conn.close()
                return fills

            for row in rows:
                fills.append({
                    "id": str(row["id"]),
                    "symbol": row["symbol"],
                    "side": row["side"],
                    "size": float(row["amount"]),
                    "price": float(row["price"]),
                })
            conn.close()
        except Exception as e:
            logger.warning(f"[{self.name}] scalper.db read failed: {e}")
        return fills

    def _get_customer_capital(self) -> float:
        """Get customer's current buying power."""
        try:
            resp = self.exchange.v3PrivateGetBrokerageCfmBalanceSummary()
            return float(resp.get("balance_summary", {}).get("total_balance", 0))
        except Exception:
            return 0
