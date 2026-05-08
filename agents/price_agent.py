"""
Price Agent — fetches spot + futures ticker prices with 24h stats.
TTL: 10s (prices need frequent updates)
"""

from .base_agent import BaseAgent


class PriceAgent(BaseAgent):
    def __init__(self, spot_exchange, cb_public, config):
        super().__init__("PriceAgent", ttl_seconds=10)
        self.spot_exchange = spot_exchange
        self.cb_public = cb_public
        self.config = config

    def fetch(self) -> dict:
        data = {"spot_prices": [], "futures_prices": []}

        # Spot prices (HTX)
        if self.spot_exchange:
            spot_symbols = self.config.forced_symbols if self.config.forced_symbols else []
            for sym in spot_symbols:
                try:
                    ticker = self.spot_exchange.fetch_ticker(sym)
                    data["spot_prices"].append({
                        "symbol": sym,
                        "price": ticker.get("last", 0),
                        "change": ticker.get("percentage", 0),
                        "high": ticker.get("high", 0),
                        "low": ticker.get("low", 0),
                    })
                except Exception:
                    pass

        # Futures prices (Coinbase public)
        for sym in self.config.scalper_symbols:
            try:
                ticker = self.cb_public.fetch_ticker(sym)
                price = ticker.get("last", 0) or 0
                ohlcv = self.cb_public.fetch_ohlcv(sym, "1h", limit=24)
                high_24h = max(c[2] for c in ohlcv) if ohlcv else 0
                low_24h = min(c[3] for c in ohlcv) if ohlcv else 0
                open_24h = ohlcv[0][1] if ohlcv else price
                change_pct = ((price - open_24h) / open_24h * 100) if open_24h > 0 else 0
                data["futures_prices"].append({
                    "symbol": sym, "price": price,
                    "change": round(change_pct, 2),
                    "high": high_24h, "low": low_24h,
                })
            except Exception:
                pass

        return data
