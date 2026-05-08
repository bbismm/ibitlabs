"""
Autopilot State DB — SQLite schema for customer tracking, trade execution, P&L.
Follows the pattern of existing state_db.py.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "autopilot.db"


class AutopilotStateDB:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_tables()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_tables(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    access_code TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    active INTEGER DEFAULT 1,
                    paused INTEGER DEFAULT 0,
                    capital_snapshot REAL DEFAULT 0,
                    profit_share_pct REAL DEFAULT 0.20,
                    high_water_mark REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS copy_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    owner_trade_id TEXT,
                    customer_order_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    owner_size REAL,
                    customer_size REAL,
                    price REAL,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT (datetime('now')),
                    filled_at TEXT,
                    pnl REAL DEFAULT 0,
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                );

                CREATE TABLE IF NOT EXISTS daily_summary (
                    customer_id TEXT,
                    date TEXT,
                    trades_count INTEGER DEFAULT 0,
                    gross_pnl REAL DEFAULT 0,
                    profit_share REAL DEFAULT 0,
                    net_pnl REAL DEFAULT 0,
                    PRIMARY KEY (customer_id, date)
                );

                CREATE TABLE IF NOT EXISTS risk_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_copy_trades_customer
                    ON copy_trades(customer_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_copy_trades_status
                    ON copy_trades(status);
            """)
        logger.info(f"AutopilotStateDB initialized at {self.db_path}")

    def add_customer(self, customer_id: str, access_code: str, capital: float = 0) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO customers (customer_id, access_code, capital_snapshot) VALUES (?, ?, ?)",
                (customer_id, access_code, capital),
            )

    def get_customer(self, customer_id: str) -> dict | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
            return dict(row) if row else None

    def get_active_customers(self) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM customers WHERE active = 1 AND paused = 0").fetchall()
            return [dict(r) for r in rows]

    def pause_customer(self, customer_id: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE customers SET paused = 1 WHERE customer_id = ?", (customer_id,))

    def resume_customer(self, customer_id: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE customers SET paused = 0 WHERE customer_id = ?", (customer_id,))

    def record_copy_trade(self, customer_id: str, owner_trade_id: str, symbol: str,
                          side: str, owner_size: float, customer_size: float,
                          price: float, customer_order_id: str = "") -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO copy_trades
                   (customer_id, owner_trade_id, customer_order_id, symbol, side, owner_size, customer_size, price, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (customer_id, owner_trade_id, customer_order_id, symbol, side, owner_size, customer_size, price),
            )
            return cursor.lastrowid

    def update_trade_status(self, trade_id: int, status: str, pnl: float = 0) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE copy_trades SET status = ?, pnl = ?, filled_at = datetime('now') WHERE id = ?",
                (status, pnl, trade_id),
            )

    def get_customer_trades(self, customer_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM copy_trades WHERE customer_id = ? ORDER BY created_at DESC LIMIT ?",
                (customer_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_customer_pnl(self, customer_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(pnl), 0) as total_pnl, COUNT(*) as total_trades FROM copy_trades WHERE customer_id = ? AND status = 'filled'",
                (customer_id,),
            ).fetchone()
            return {"total_pnl": row[0], "total_trades": row[1]}

    def record_risk_event(self, customer_id: str, event_type: str, details: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO risk_events (customer_id, event_type, details) VALUES (?, ?, ?)",
                (customer_id, event_type, details),
            )

    def get_last_copied_trade_id(self, customer_id: str) -> str:
        """Get the last owner trade ID that was copied for this customer."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT owner_trade_id FROM copy_trades WHERE customer_id = ? ORDER BY id DESC LIMIT 1",
                (customer_id,),
            ).fetchone()
            return row[0] if row else ""
