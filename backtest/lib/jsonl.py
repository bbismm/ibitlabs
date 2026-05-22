"""JSONL event writer — schema mirrors breakout_sniper_spot_v01.jsonl + entry_confidence_map.jsonl."""

from __future__ import annotations
import json
from pathlib import Path


SCHEMA_VERSION = 1


def write_events(
    path: Path,
    trades: list[dict],
    *,
    symbol: str,
    strategy_name: str,
    strategy_version: str,
) -> int:
    """Write trades to JSONL as paired ENTRY+EXIT events. Returns event count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_events = 0
    with path.open("w") as f:
        for t in trades:
            entry_event = {
                "schema_version": SCHEMA_VERSION,
                "kind": "ENTRY",
                "ts": t.get("entry_ts"),
                "symbol": symbol,
                "direction": t.get("direction"),
                "entry_price": t.get("entry_price"),
                "quantity": t.get("quantity"),
                "regime": t.get("regime"),
                "strategy_name": strategy_name,
                "strategy_version": strategy_version,
            }
            exit_event = {
                "schema_version": SCHEMA_VERSION,
                "kind": "EXIT",
                "ts": t.get("exit_ts"),
                "symbol": symbol,
                "direction": t.get("direction"),
                "entry_price": t.get("entry_price"),
                "exit_price": t.get("exit_price"),
                "quantity": t.get("quantity"),
                "pnl": t.get("pnl"),
                "fees": t.get("fees"),
                "hours_held": t.get("hours_held"),
                "exit_reason": t.get("exit_reason"),
                "regime": t.get("regime"),
                "strategy_name": strategy_name,
                "strategy_version": strategy_version,
            }
            f.write(json.dumps(entry_event) + "\n")
            f.write(json.dumps(exit_event) + "\n")
            n_events += 2
    return n_events
