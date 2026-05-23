"""OHLCV loader — multi-symbol Coinbase fetch + 1h resample."""

from __future__ import annotations
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # ~/ibitlabs/
from sol_sniper_backtest import resample_to_1h  # noqa: E402  -- pure math, reuse


_PERIOD_RE = re.compile(r"^(\d+)([dh])$")


_SYMBOL_TO_PRODUCT = {
    "SOL": "SOL-USD",
    "ETH": "ETH-USD",
    "BTC": "BTC-USD",
}


def _parse_period_days(period: str) -> int:
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(f"period must be like '90d' or '720h', got {period!r}")
    n, unit = int(m.group(1)), m.group(2)
    return n if unit == "d" else max(1, n // 24)


def _resolve_product_id(symbol: str) -> str:
    pid = _SYMBOL_TO_PRODUCT.get(symbol.upper())
    if not pid:
        raise ValueError(
            f"unknown symbol {symbol!r}; supported: {sorted(_SYMBOL_TO_PRODUCT)}"
        )
    return pid


def fetch_coinbase_candles(product_id: str, days: int, granularity: int = 900) -> list:
    """Fetch OHLCV from Coinbase Exchange public API. Returns chronologically-sorted bars."""
    end_ts = int(time.time())
    start_ts = end_ts - days * 86400
    batch_secs = 300 * granularity
    cur = start_ts
    seen = set()
    bars: list = []

    print(f"  fetching {product_id} {granularity}s candles ({days}d)...")
    while cur < end_ts:
        cur_end = min(cur + batch_secs, end_ts)
        url = (
            f"https://api.exchange.coinbase.com/products/{product_id}/candles"
            f"?granularity={granularity}&start={cur}&end={cur_end}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "ibit-backtest/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        for row in data:
            ts = row[0]
            if ts in seen:
                continue
            seen.add(ts)
            bars.append({
                "ts": ts,
                "low": row[1],
                "high": row[2],
                "open": row[3],
                "close": row[4],
                "volume": row[5],
            })
        cur = cur_end

    bars.sort(key=lambda b: b["ts"])
    if bars:
        print(f"  fetched {len(bars)} bars  |  {bars[0]['ts']} -> {bars[-1]['ts']}")
    return bars


def load_ohlcv(symbol: str, period: str) -> tuple:
    """Return (bars_15m, bars_1h). Supports SOL/ETH/BTC; period like '90d' or '720h'."""
    product_id = _resolve_product_id(symbol)
    days = _parse_period_days(period)
    bars_15m = fetch_coinbase_candles(product_id, days, granularity=900)
    bars_1h = resample_to_1h(bars_15m)
    return bars_15m, bars_1h
