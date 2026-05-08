"""
Base Growth Agent — autonomous agent with action queue, logging, and auto-execute.

Unlike trading agents (data fetchers), growth agents TAKE ACTIONS:
- Post tweets, send DMs, generate content, respond to users
- All actions are logged to growth_actions.log
- Auto-mode: actions execute immediately (no approval needed)
- Each agent has its own state file for persistence across restarts
"""

import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

GROWTH_DIR = Path(__file__).parent.parent / "growth_state"
GROWTH_DIR.mkdir(exist_ok=True)
ACTION_LOG = GROWTH_DIR / "growth_actions.log"


class BaseGrowthAgent:
    def __init__(self, name: str, interval_seconds: int = 300):
        self.name = name
        self.interval = interval_seconds
        self.state_file = GROWTH_DIR / f"{name}_state.json"
        self.state = self._load_state()
        self._last_run = 0.0
        self.stats = {"actions_taken": 0, "errors": 0, "last_action": None}

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {}

    def _save_state(self):
        try:
            self.state_file.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"[{self.name}] state save failed: {e}")

    def _log_action(self, action_type: str, detail: str, result: str = "ok"):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] [{self.name}] [{action_type}] {detail} → {result}\n"
        try:
            with open(ACTION_LOG, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass
        self.stats["actions_taken"] += 1
        self.stats["last_action"] = ts
        logger.info(f"[{self.name}] {action_type}: {detail[:80]}")

    def should_run(self) -> bool:
        return time.time() - self._last_run >= self.interval

    def run(self) -> dict:
        """Execute one cycle. Returns summary dict."""
        if not self.should_run():
            return {"skipped": True}
        self._last_run = time.time()
        try:
            result = self.execute()
            self._save_state()
            return result
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"[{self.name}] execute failed: {e}", exc_info=True)
            self._log_action("ERROR", str(e), "failed")
            return {"error": str(e)}

    def execute(self) -> dict:
        """Override this. Do the agent's work, return summary."""
        raise NotImplementedError

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "interval_seconds": self.interval,
            "stats": self.stats,
            "state_keys": list(self.state.keys()),
        }
