#!/usr/bin/env python3
"""
TIER 2: Free Preview Harness — public, no auth (ibitlabs.com)
Port 8081 — 2 agents, 15-min delayed + partial data.

No API keys needed. Reads monitor_state.json + Coinbase public API.

Usage:
  python3 preview_harness.py
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from agents.preview_monitor_agent import PreviewMonitorAgent
from agents.preview_price_agent import PreviewPriceAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class PreviewHarness:
    """Tier 2: Free preview — 2 agents, delayed + stripped data."""

    def __init__(self):
        self.agents = {
            "monitor": PreviewMonitorAgent(),
            "price": PreviewPriceAgent(),
        }
        logger.info(f"Preview Harness: {len(self.agents)} agents")
        for name, agent in self.agents.items():
            logger.info(f"  [{name}] TTL={agent.ttl}s")

    def get_preview(self) -> dict:
        monitor = self.agents["monitor"].get()
        price = self.agents["price"].get()
        result = {**monitor}
        result["sol_price"] = price.get("sol_price", 0)
        if price.get("warming_up") and not monitor.get("warming_up"):
            result["warming_up"] = True
        return result


harness = PreviewHarness()
INDEX_PATH = Path(__file__).parent / "index.html"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/preview":
            self._json_response(harness.get_preview())
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
        self.wfile.write(INDEX_PATH.read_bytes())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = 8081
    server = HTTPServer(("127.0.0.1", port), Handler)
    logger.info(f"Preview Harness (Tier 2) running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Preview Harness stopped.")
