#!/usr/bin/env python3
"""
TIER 4: Grid Autopilot Harness (legacy — paid autopilot tier discontinued)
Port 8083 — 5 agents (2 shared + 3 per-customer), auto-execution on customer exchanges.

Requires: AUTOPILOT_MASTER_KEY env var for customer API key encryption.

Usage:
  export AUTOPILOT_MASTER_KEY='your_master_key'
  python3 autopilot_harness.py
"""

import json
import time
import logging
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import ccxt

from agents.monitor_agent import MonitorDashboardAgent
from agents.signals_price_agent import SignalsPriceAgent
from agents.autopilot_account_agent import AutopilotAccountAgent
from agents.autopilot_execution_agent import AutopilotExecutionAgent
from agents.autopilot_pnl_agent import AutopilotPnLAgent
from auth import verify_access
from autopilot_state import AutopilotStateDB
import key_vault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Owner capital — used for proportional sizing
OWNER_CAPITAL = 1700.0  # Updated periodically or from config


class AutopilotHarness:
    """Tier 4: Grid Autopilot — shared agents + per-customer agents."""

    def __init__(self):
        self.db = AutopilotStateDB()
        self.shared_agents = {
            "monitor": MonitorDashboardAgent(),
            "price": SignalsPriceAgent(),
        }
        # Per-customer agent sets: {customer_id: {account, execution, pnl}}
        self.customer_agents: dict[str, dict] = {}
        logger.info("Autopilot Harness: 2 shared agents + per-customer agents")

        # Load existing active customers
        self._load_customers()

    def _load_customers(self):
        """Restore agent sets for all active customers on startup."""
        for customer in self.db.get_active_customers():
            cid = customer["customer_id"]
            try:
                self._init_customer_agents(cid)
                logger.info(f"  Loaded customer {cid}")
            except Exception as e:
                logger.error(f"  Failed to load customer {cid}: {e}")

    def _init_customer_agents(self, customer_id: str):
        """Create the 3 per-customer agents with their authenticated exchange."""
        api_key, api_secret = key_vault.load(customer_id)
        exchange = ccxt.coinbaseadvanced({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
        exchange.load_markets()

        self.customer_agents[customer_id] = {
            "account": AutopilotAccountAgent(customer_id, exchange),
            "execution": AutopilotExecutionAgent(customer_id, exchange, self.db, OWNER_CAPITAL),
            "pnl": AutopilotPnLAgent(customer_id, self.db),
        }

    def register_customer(self, access_code: str, api_key: str, api_secret: str) -> dict:
        """Register a new Grid Autopilot customer."""
        customer_id = str(uuid.uuid4())[:8]

        # Store encrypted keys
        key_vault.store(customer_id, api_key, api_secret)

        # Verify the keys work by checking balance
        try:
            exchange = ccxt.coinbaseadvanced({
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            })
            exchange.load_markets()
            resp = exchange.v3PrivateGetBrokerageCfmBalanceSummary()
            capital = float(resp.get("balance_summary", {}).get("total_balance", 0))
        except Exception as e:
            key_vault.delete(customer_id)
            return {"error": f"Invalid API keys: {e}"}

        # Store in DB
        self.db.add_customer(customer_id, access_code, capital)

        # Init agents
        self._init_customer_agents(customer_id)

        logger.info(f"Registered customer {customer_id} with ${capital:.2f} capital")
        return {"customer_id": customer_id, "capital": capital, "status": "active"}

    def get_signals(self) -> dict:
        """Same signals as Tier 3."""
        monitor = self.shared_agents["monitor"].get()
        price = self.shared_agents["price"].get()
        return {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sol_price": price.get("sol_price", 0),
            "action": monitor.get("action", ""),
            "regime": monitor.get("regime", ""),
            "regime_trend_strength": monitor.get("regime_trend_strength", 0),
            "regime_vol_percentile": monitor.get("regime_vol_percentile", 50),
            "sentiment": monitor.get("sentiment", ""),
            "sentiment_confidence": monitor.get("sentiment_confidence", 0),
            "funding_pressure": monitor.get("funding_pressure", 0),
            "whale_bias": monitor.get("whale_bias", ""),
            "social_mood": monitor.get("social_mood", ""),
            "social_score": monitor.get("social_score", 0),
            "fear_greed_index": monitor.get("fear_greed_index", 50),
            "fear_greed_label": monitor.get("fear_greed_label", ""),
            "support_level": monitor.get("support_level", 0),
            "resistance_level": monitor.get("resistance_level", 0),
            "suggested_spacing_pct": monitor.get("suggested_spacing_pct", 0),
            "suggested_levels": monitor.get("suggested_levels", 0),
            "reasons": monitor.get("reasons", []),
            "alerts": monitor.get("alerts", []),
        }

    def get_customer_status(self, customer_id: str) -> dict:
        """Full autopilot status for a customer."""
        agents = self.customer_agents.get(customer_id)
        if not agents:
            return {"error": "Customer not found or not loaded"}

        account = agents["account"].get()
        pnl = agents["pnl"].get()
        execution = agents["execution"].get()

        return {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "customer_id": customer_id,
            "account": account,
            "pnl": pnl,
            "execution": {
                "new_copies": execution.get("new_copies", 0),
                "last_trade_id": execution.get("last_trade_id", ""),
                "errors": execution.get("errors", []),
            },
        }

    def pause_customer(self, customer_id: str) -> dict:
        self.db.pause_customer(customer_id)
        if customer_id in self.customer_agents:
            del self.customer_agents[customer_id]
        return {"customer_id": customer_id, "status": "paused"}

    def resume_customer(self, customer_id: str) -> dict:
        self.db.resume_customer(customer_id)
        try:
            self._init_customer_agents(customer_id)
            return {"customer_id": customer_id, "status": "active"}
        except Exception as e:
            return {"error": f"Failed to resume: {e}"}


harness = AutopilotHarness()
UI_PATH = Path(__file__).parent / "autopilot_ui.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/autopilot/signals":
            code = self.headers.get("X-Access-Code", "")
            if not verify_access(code):
                self._json_response({"error": "Invalid or expired access code"})
            else:
                self._json_response(harness.get_signals())
        elif self.path.startswith("/api/autopilot/status"):
            code = self.headers.get("X-Access-Code", "")
            customer_id = self.headers.get("X-Customer-ID", "")
            if not verify_access(code):
                self._json_response({"error": "Invalid or expired access code"})
            elif not customer_id:
                self._json_response({"error": "Missing X-Customer-ID header"})
            else:
                self._json_response(harness.get_customer_status(customer_id))
        else:
            self._serve_html()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}

        if self.path == "/api/verify":
            code = body.get("code", "")
            self._json_response({"valid": verify_access(code)})

        elif self.path == "/api/register":
            code = self.headers.get("X-Access-Code", "")
            if not verify_access(code):
                self._json_response({"error": "Invalid or expired access code"})
                return
            api_key = body.get("api_key", "")
            api_secret = body.get("api_secret", "")
            if not api_key or not api_secret:
                self._json_response({"error": "api_key and api_secret required"})
                return
            result = harness.register_customer(code, api_key, api_secret)
            self._json_response(result)

        elif self.path == "/api/autopilot/pause":
            code = self.headers.get("X-Access-Code", "")
            customer_id = body.get("customer_id", "")
            if not verify_access(code):
                self._json_response({"error": "Invalid or expired access code"})
            else:
                self._json_response(harness.pause_customer(customer_id))

        elif self.path == "/api/autopilot/resume":
            code = self.headers.get("X-Access-Code", "")
            customer_id = body.get("customer_id", "")
            if not verify_access(code):
                self._json_response({"error": "Invalid or expired access code"})
            else:
                self._json_response(harness.resume_customer(customer_id))

        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code, X-Customer-ID")
        self.end_headers()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code, X-Customer-ID")
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
    port = 8083
    server = HTTPServer(("127.0.0.1", port), Handler)
    logger.info(f"Grid Autopilot Harness (Tier 4) running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Grid Autopilot Harness stopped.")
