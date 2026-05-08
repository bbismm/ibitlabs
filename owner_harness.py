#!/usr/bin/env python3
"""
TIER 1: Owner Harness — Full trading dashboard (local, behind Cloudflare Tunnel)
Port 8080 — 7 agents, all account + monitor + security data.

Usage:
  export CB_API_KEY='your_key'
  export CB_API_SECRET='your_secret'
  python3 owner_harness.py
"""

import json
import os
import time
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import ccxt

from config import Config
from state_db import StateDB
from agents import BalanceAgent, PriceAgent, OrderAgent, TradeAgent, MonitorDashboardAgent, SecurityDashAgent, ReportDashAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Exchange Setup ──

config = Config()
has_spot = bool(config.api_key and config.api_secret)
has_futures = bool(os.environ.get("CB_API_KEY") and os.environ.get("CB_API_SECRET"))

spot_exchange = None
if has_spot:
    spot_exchange = getattr(ccxt, config.exchange_id)({
        "apiKey": config.api_key,
        "secret": config.api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })

futures_exchange = None
if has_futures:
    futures_exchange = ccxt.coinbaseadvanced({
        "apiKey": os.environ.get("CB_API_KEY", ""),
        "secret": os.environ.get("CB_API_SECRET", ""),
        "enableRateLimit": True,
    })
    futures_exchange.load_markets()
    logger.info("Coinbase Advanced markets loaded")

cb_public = ccxt.coinbase({"enableRateLimit": True})
cb_public.load_markets()
logger.info("Coinbase public markets loaded")

spot_db = StateDB(config.db_path)
futures_db = StateDB(config.futures_db_path)


# ── Owner Harness ──

class OwnerHarness:
    """Tier 1: Full data access — 7 agents for owner dashboard."""

    def __init__(self):
        self.agents = {
            "balance": BalanceAgent(spot_exchange, futures_exchange),
            "price": PriceAgent(spot_exchange, cb_public, config),
            "order": OrderAgent(spot_exchange, futures_exchange, config),
            "trade": TradeAgent(spot_db, futures_db, spot_exchange, config, futures_exchange),
            "monitor": MonitorDashboardAgent(),
            "security": SecurityDashAgent(),
            "report": ReportDashAgent(),
        }
        logger.info(f"Owner Harness: {len(self.agents)} agents")
        for name, agent in self.agents.items():
            logger.info(f"  [{name}] TTL={agent.ttl}s")

    def get_agent_data(self, agent_name: str) -> dict:
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"Unknown agent: {agent_name}"}
        return agent.get()

    def get_status(self) -> dict:
        """Full dashboard data — all agents merged."""
        bal = self.agents["balance"].get()
        prices = self.agents["price"].get()
        orders = self.agents["order"].get()
        trades = self.agents["trade"].get()
        monitor = self.agents["monitor"].get()
        security = self.agents["security"].get()
        report = self.agents["report"].get()

        futures_orders = orders.get("futures_orders", [])
        futures_prices = prices.get("futures_prices", [])

        return {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "monitor": monitor,
            "security": security,
            "report": report,
            "spot": {
                "balances": bal.get("balances", []),
                "prices": prices.get("spot_prices", []),
                "orders": orders.get("spot_orders", []),
                "pnl": trades.get("spot_pnl", 0),
                "trades": trades.get("spot_trades", []),
                "performance": trades.get("performance", {}),
            },
            "futures": {
                "balance": bal.get("futures_balance", {}),
                "prices": futures_prices,
                "orders": futures_orders,
                "positions": orders.get("positions", []),
                "pnl": trades.get("futures_pnl", 0),
                "trades": trades.get("futures_trades", []),
            },
            "cooling": trades.get("cooling", []),
        }


harness = OwnerHarness()
UI_PATH = Path(__file__).parent / "dashboard_ui.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            self._json_response(harness.get_status())
        elif self.path.startswith("/api/"):
            agent_name = self.path[5:]
            self._json_response(harness.get_agent_data(agent_name))
        else:
            self._serve_html()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(UI_PATH.read_bytes())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = 8080
    server = HTTPServer(("127.0.0.1", port), Handler)
    logger.info(f"Owner Harness (Tier 1) running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Owner Harness stopped.")
