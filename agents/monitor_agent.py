"""
Monitor Dashboard Agent — reads monitor_state.json for dashboard display.
TTL: 10s
"""

import json
import os
from .base_agent import BaseAgent

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "monitor_state.json")


class MonitorDashboardAgent(BaseAgent):
    def __init__(self):
        super().__init__("MonitorDashAgent", ttl_seconds=10)

    def fetch(self) -> dict:
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"action": "offline", "reasons": ["Monitor未运行"]}
