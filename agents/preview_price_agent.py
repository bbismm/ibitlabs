"""
Preview Price Agent — 15-minute delayed SOL price for free tier.
Uses Coinbase public API (no auth needed). Stores price snapshots in deque.
TTL: 60s
"""

import time
from collections import deque

import ccxt

from .base_agent import BaseAgent

DELAY_SECONDS = 15 * 60
MAX_SNAPSHOTS = 20


class PreviewPriceAgent(BaseAgent):
    def __init__(self):
        super().__init__("PreviewPriceAgent", ttl_seconds=60)
        self._buffer: deque = deque(maxlen=MAX_SNAPSHOTS)
        self._exchange = ccxt.coinbase({"enableRateLimit": True})

    def fetch(self) -> dict:
        # 1. Fetch current price and add to buffer
        try:
            ticker = self._exchange.fetch_ticker("SOL/USDC")
            price = ticker.get("last", 0) or 0
            self._buffer.append((time.time(), price))
        except Exception:
            pass

        # 2. Return the price from ~15 minutes ago
        target = time.time() - DELAY_SECONDS
        best_price = None
        for epoch, price in self._buffer:
            if epoch <= target:
                best_price = price
        if best_price is not None:
            return {"sol_price": best_price, "delayed": True}

        return {"sol_price": 0, "delayed": True, "warming_up": True}
