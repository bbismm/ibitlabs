"""OHLCV loader — wraps sol_sniper_backtest.fetch_ohlcv_coinbase + resample_to_1h."""

from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # ~/ibitlabs/
from sol_sniper_backtest import fetch_ohlcv_coinbase, resample_to_1h  # noqa: E402


_PERIOD_RE = re.compile(r"^(\d+)([dh])$")


def _parse_period_days(period: str) -> int:
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(f"period must be like '90d' or '720h', got {period!r}")
    n, unit = int(m.group(1)), m.group(2)
    if unit == "d":
        return n
    if unit == "h":
        return max(1, n // 24)
    raise ValueError(f"unsupported period unit {unit!r}")


def load_ohlcv(symbol: str, period: str) -> tuple[list[dict], list[dict]]:
    """Return (bars_15m, bars_1h). v0: symbol='SOL' only — fetch_ohlcv_coinbase is SOL-USD hardcoded."""
    if symbol.upper() != "SOL":
        raise NotImplementedError(
            f"v0: only SOL supported (sol_sniper_backtest.fetch_ohlcv_coinbase is SOL-USD hardcoded). "
            f"Asked for {symbol!r}. ETH/multi-symbol work belongs in v0.1."
        )
    days = _parse_period_days(period)
    bars_15m = fetch_ohlcv_coinbase(days=days, granularity=900)
    bars_1h = resample_to_1h(bars_15m)
    return bars_15m, bars_1h
