"""ETH v5.1 — wraps sol_sniper_backtest.run_backtest with ETH v5.1 paper config.

Per [ETH=v5.1, SOL=v5.3 founder policy 2026-05-19]: ETH paper bot (eth_paper) runs
v5.1, NOT v5.3. Promote-to-live gate: n>=30 + PF>=1.2 + WR>=60% + >=1 complete regime
cycle. $1k account stays 100% on SOL until ETH crosses gate.

Faithfulness to LIVE eth_paper bot:
  + Same mean-reversion engine (sol_sniper_backtest.run_backtest) — same fee model,
    regime classifier, signal logic
  + v5.1 trailing activate 0.008 + stop 0.005 (NOT v5.3's 0.004/0.005)
  + TP 3.0% / SL 3.5% (LIVE values, same as v5.3)
  + No reverse_exit_C — v5.1 doesn't have it. So unlike SOL v5.3 (~90% faithful),
    THIS wrapper has no known gap.
  + No regime_gate at entry — v5.1 doesn't have it
  + --no-grid via grid_size=0

Engine's `SniperConfig` defaults ARE v5.1-shape (the v5.3 add-ons live OUTSIDE the
engine, in sol_sniper_executor's wiring). So overriding just TP/SL/trailing/leverage
gives a 1:1 LIVE eth_paper match.
"""

from __future__ import annotations
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # ~/ibitlabs/
from sol_sniper_backtest import SniperConfig, run_backtest  # noqa: E402


name = "eth_v5_1"
version = "5.1.0+sol_sniper_backtest+faithful"


config_for_manifest = {
    "engine": "sol_sniper_backtest.run_backtest",
    "leverage": 3,
    "position_pct": 0.80,
    "tp_pct": 0.030,
    "sl_pct": 0.035,
    "trailing_activate": 0.008,
    "trailing_stop": 0.005,
    "max_hold_bars": 192,
    "cooldown_bars": 16,
    "grid_size": 0.0,
    "grid_spacing": 0.005,
    "policy": "ETH=v5.1, SOL=v5.3 (founder call 2026-05-19); $1k stays on SOL until ETH crosses promote gate",
    "known_gaps": [],
}


def _live_config() -> SniperConfig:
    """LIVE eth_paper config (v5.1)."""
    cfg = SniperConfig()
    cfg.leverage = 3
    cfg.position_pct = 0.80
    cfg.tp_pct = 0.030
    cfg.sl_pct = 0.035
    cfg.trailing_activate = 0.008
    cfg.trailing_stop = 0.005
    return cfg


_BAR_15M_SECONDS = 900


def _trade_to_dict(t) -> dict:
    """Convert Trade dataclass to wire shape; reconstruct entry_ts from bars_held."""
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
