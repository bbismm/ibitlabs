"""
Report Dashboard Agent — reads report_state.json for dashboard display.
TTL: 60s
"""

import json
import os
from .base_agent import BaseAgent

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "report_state.json")


class ReportDashAgent(BaseAgent):
    def __init__(self):
        super().__init__("ReportDashAgent", ttl_seconds=60)

    def fetch(self) -> dict:
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"reports": []}
