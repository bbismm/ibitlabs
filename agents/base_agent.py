"""
Base Agent — TTL cached data fetcher with error isolation.
All dashboard data agents inherit from this.
"""

import time
import logging

logger = logging.getLogger(__name__)


class BaseAgent:
    def __init__(self, name: str, ttl_seconds: int = 30):
        self.name = name
        self.ttl = ttl_seconds
        self._cache = {}
        self._last_fetch = 0.0

    def get(self) -> dict:
        now = time.time()
        if now - self._last_fetch < self.ttl and self._cache:
            return self._cache
        try:
            self._cache = self.fetch()
            self._last_fetch = now
        except Exception as e:
            logger.warning(f"[{self.name}] fetch failed: {e}, using cache")
        return self._cache

    def fetch(self) -> dict:
        raise NotImplementedError

    def invalidate(self):
        self._last_fetch = 0.0
