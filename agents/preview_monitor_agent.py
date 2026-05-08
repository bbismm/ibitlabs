"""
Preview Monitor Agent — 15-minute delayed, partial monitor data for free tier.
Reads monitor_state.json, stores snapshots in a deque, serves the one from ~15 min ago.
Strips sensitive fields (support/resistance, grid params, reasons, alert details).
TTL: 60s (delayed data, no need for frequent updates)
"""

import json
import os
import time
from collections import deque

from .base_agent import BaseAgent

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "monitor_state.json")

DELAY_SECONDS = 15 * 60  # 15 minutes
MAX_SNAPSHOTS = 20        # ~20 minutes of history at 60s intervals


class PreviewMonitorAgent(BaseAgent):
    def __init__(self):
        super().__init__("PreviewMonitorAgent", ttl_seconds=60)
        self._buffer: deque = deque(maxlen=MAX_SNAPSHOTS)

    def fetch(self) -> dict:
        # 1. Read current state and add to buffer
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    raw = json.load(f)
                snapshot = {
                    "ts": raw.get("ts", ""),
                    "action": raw.get("action", ""),
                    "regime": raw.get("regime", ""),
                    "sentiment": raw.get("sentiment", ""),
                    "whale_bias": raw.get("whale_bias", ""),
                    "funding_direction": "positive" if raw.get("funding_pressure", 0) >= 0 else "negative",
                    "fear_greed_index": raw.get("fear_greed_index", 50),
                    "fear_greed_label": raw.get("fear_greed_label", ""),
                    "regime_vol_percentile": raw.get("regime_vol_percentile", 50),
                    "alert_count": len(raw.get("alerts", [])),
                }
                self._buffer.append((time.time(), snapshot))
        except Exception:
            pass

        # 2. Return the snapshot from ~15 minutes ago
        target = time.time() - DELAY_SECONDS
        best = None
        for epoch, snap in self._buffer:
            if epoch <= target:
                best = snap
        if best:
            return {**best, "delayed": True, "delay_minutes": 15}

        # Not enough history yet
        return {
            "delayed": True,
            "delay_minutes": 15,
            "warming_up": True,
            "message": "System warming up — preview data available in ~15 minutes",
        }
