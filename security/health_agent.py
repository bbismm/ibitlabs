"""
Health Agent — Process alive checks, API connectivity, auto-restart.
TTL: 30s
"""

import os
import subprocess
import time
import logging
import sys
sys.path.insert(0, "..")
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class HealthAgent(BaseAgent):
    def __init__(self, exchange):
        super().__init__("HealthAgent", ttl_seconds=30)
        self.exchange = exchange
        self.last_restart_time = 0

    def fetch(self) -> dict:
        data = {
            "scalper_alive": False,  # Key kept for dashboard compat (now checks sniper)
            "monitor_alive": False,
            "dashboard_alive": False,
            "api_connected": False,
            "api_latency_ms": 0,
            "issues": [],
            "actions_taken": [],
        }

        # 1. Process checks — Sniper (active trading engine)
        try:
            result = subprocess.run(
                ["pgrep", "-fl", "sol_sniper_main"],
                capture_output=True, text=True, timeout=5,
            )
            data["scalper_alive"] = "sol_sniper_main" in result.stdout
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["pgrep", "-fl", "monitor_harness"],
                capture_output=True, text=True, timeout=5,
            )
            data["monitor_alive"] = "monitor_harness" in result.stdout
        except Exception:
            pass

        try:
            result = subprocess.run(
                ["pgrep", "-fl", "owner_harness"],
                capture_output=True, text=True, timeout=5,
            )
            data["dashboard_alive"] = "owner_harness" in result.stdout
        except Exception:
            pass

        # 2. API connectivity + latency
        try:
            t0 = time.time()
            self.exchange.fetch_ticker("SOL/USDC")
            latency = (time.time() - t0) * 1000
            data["api_connected"] = True
            data["api_latency_ms"] = round(latency)
            if latency > 5000:
                data["issues"].append(f"High API latency: {latency:.0f}ms")
        except Exception as e:
            data["api_connected"] = False
            data["issues"].append(f"API connection failed: {str(e)[:80]}")

        # 3. Report issues (only for active services)
        if not data["monitor_alive"]:
            data["issues"].append("Monitor process is DOWN")
        if not data["dashboard_alive"]:
            data["issues"].append("Dashboard process is DOWN")

        # Note: Scalper auto-restart disabled — legacy service, start manually if needed

        return data
