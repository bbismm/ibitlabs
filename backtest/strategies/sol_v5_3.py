"""SOL v5.3 LIVE — wraps sol_sniper_backtest.run_backtest with LIVE-current config.

Faithfulness to LIVE (snapshot 2026-05-21):
  + Mean-reversion signal (sol_sniper_backtest.generate_signal at line 300)
  + Regime classification (up / down / sideways)
  + SL / TP / trailing / timeout exit logic
  + Maker for TP/trailing, taker for SL/timeout, + funding per 8h
  + 4h SL cooldown
  + --no-grid via grid_size=0  (sniper fires in all regimes incl sideways since 5-08)
  + Trailing activate 0.004 + stop 0.005 (LIVE since 2026-05-14 21:19 EDT swap)
  + TP 3.0% / SL 3.5% (LIVE; engine default 1.5% / 5.0% is backtest-historical)
  - reverse_exit_C (SNIPER_REVERSE_EXIT=1 on LIVE) — NOT modeled by engine. ~10% gap.
    shadow_no_rev (5-15) is still attributing this mode; review n>=30 or 6-15.
    Cross-check by excluding LIVE trades with exit_reason='reverse_exit'.
"""

from __future__ import annotations
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # ~/ibitlabs/
from sol_sniper_backtest import SniperConfig, run_backtest  # noqa: E402


name = "sol_v5_3"
version = "5.3.0+sol_sniper_backtest+90pct"


config_for_manifest = {
    "engine": "sol_sniper_backtest.run_backtest",
    "leverage": 3,
    "position_pct": 0.80,
    "tp_pct": 0.030,
    "sl_pct": 0.035,
    "trailing_activate": 0.004,
    "trailing_stop": 0.005,
    "max_hold_bars": 192,
    "cooldown_bars": 16,
    "grid_size": 0.0,
    "grid_spacing": 0.005,
    "known_gaps": [
        "reverse_exit_C not modeled (LIVE has SNIPER_REVERSE_EXIT=1; shadow_no_rev review n>=30 or 6-15)",
    ],
}


def _live_config() -> SniperConfig:
    """LIVE config snapshot (post 5-14 21:19 EDT swap)."""
    cfg = SniperConfig()
    cfg.leverage = 3
    cfg.position_pct = 0.80
    cfg.tp_pct = 0.030
    cfg.sl_pct = 0.035
    cfg.trailing_activate = 0.004
    cfg.trailing_stop = 0.005
    return cfg


_BAR_15M_SECONDS = 900


def _trade_to_dict(t) -> dict:
    """Convert sol_sniper_backtest.Trade to our wire shape. entry_ts reconstructed from bars_held."""
    d = asdict(t)
    if not d.get("entry_ts") and d.get("exit_ts") and d.get("bars_held"):
        d["entry_ts"] = d["exit_ts"] - d["bars_held"] * _BAR_15M_SECONDS
    d["hours_held"] = d.get("bars_held", 0) * _BAR_15M_SECONDS / 3600
    return d


def run(bars_15m: list, bars_1h: list, **overrides) -> list:
    """Escape-hatch entrypoint. **overrides set SniperConfig fields for sweep / param study."""
    cfg = _live_config()
    for k, v in overrides.items():
        if not hasattr(cfg, k):
            raise ValueError(f"unknown SniperConfig field: {k!r}")
        setattr(cfg, k, v)
    bt = run_backtest(bars_15m, bars_1h, cfg, grid_spacing=0.005, grid_size=0.0)
    return [_trade_to_dict(t) for t in bt.trades]
