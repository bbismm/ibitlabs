"""Harness bridge — converts ibit-backtest run output into harness-compatible inputs.

Emits 3 artifacts from a single backtest run:
  - fires.jsonl       : one fire per ENTRY event (shape per harness promotion_bar.py)
  - trade_log.db      : SQLite with trade_log table (mock for harness pair_with_closes)
  - proposal.yaml     : harness Proposal YAML pointing at fires.jsonl

Then user invokes:
  python3 ~/ibitlabs/harness/bin/promote_bar.py <proposal.yaml> --db <trade_log.db>

This makes 模拟 (ibit-backtest) → 治理 (harness) bridge real without patching harness.
"""

from __future__ import annotations
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


SCHEMA_VERSION = 1
HARNESS_ROOT = Path.home() / "ibitlabs"


def _slugify(s: str) -> str:
    """Convert run_id to proposal_id pattern: ^[a-z][a-z0-9_]*$"""
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    result = "".join(out).strip("_")
    while "__" in result:
        result = result.replace("__", "_")
    if not result or not result[0].isalpha():
        result = "p_" + result
    return result


def _load_run(run_dir: Path) -> tuple[dict, list]:
    """Return (manifest_dict, list_of_event_dicts)."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    events: list = []
    for line in (run_dir / "events.jsonl").read_text().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return manifest, events


def _write_fires_jsonl(path: Path, entries: list, proposal_id: str, rule_name: str) -> int:
    """Write one fire per ENTRY event in harness-expected shape."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w") as f:
        for e in entries:
            fire = {
                "schema_version": SCHEMA_VERSION,
                "event": f"{rule_name}_fired",
                "proposal_id": proposal_id,
                "rule_name": rule_name,
                "fire_ts": e["ts"],
                "entry_ts": e["ts"],
                "symbol": e["symbol"],
                "direction": e["direction"],
                "entry_price": e["entry_price"],
                "quantity": e.get("quantity"),
                "regime": e.get("regime"),
                "strategy_version": e.get("strategy_version"),
                "source": "ibit_backtest",
            }
            f.write(json.dumps(fire) + "\n")
            n += 1
    return n


def _write_trade_log_db(db_path: Path, exits: list) -> int:
    """Build mock SQLite trade_log from EXIT events. Matches schema queried by promotion_bar.py."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                pnl REAL,
                timestamp REAL,
                side TEXT
            )
        """)
        n = 0
        for e in exits:
            conn.execute(
                "INSERT INTO trade_log "
                "(symbol, direction, entry_price, exit_price, pnl, timestamp, side) "
                "VALUES (?, ?, ?, ?, ?, ?, 'SELL')",
                (
                    e["symbol"],
                    e["direction"],
                    e["entry_price"],
                    e.get("exit_price"),
                    e.get("pnl"),
                    e["ts"],
                ),
            )
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()


def _build_proposal_dict(
    *,
    proposal_id: str,
    rule_name: str,
    manifest: dict,
    entries: list,
    fires_path_rel_ibitlabs: str,
    min_entries: int,
    min_spread_pp: float,
    direction: str,
) -> dict:
    """Build a schema-valid Proposal dict. proposed_at is backdated to match window."""
    period_days = int(manifest["period"].rstrip("dh")) if manifest.get("period") else 90
    proposed_at = datetime.now(timezone.utc) - timedelta(days=period_days)

    return {
        "proposal_id": proposal_id,
        "domain": "trading",
        "rule_name": rule_name,
        "proposed_by": None,
        "proposed_in": f"ibit-backtest run {manifest.get('run_id', '?')}",
        "proposed_at": proposed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hypothesis": (
            f"Backtest of {manifest['strategy_name']} v{manifest['strategy_version']} "
            f"on {manifest['symbol']} over {manifest['period']} shows tradable edge. "
            f"Engine: {manifest.get('config', {}).get('engine', 'unknown')}. "
            f"Known gaps: {manifest.get('known_gaps') or 'none'}."
        ),
        "direction": direction,
        "shadow_log_jsonl": fires_path_rel_ibitlabs,
        "control_flow_impact": "log_only",
        "real_data_gate": {
            "evidence_threshold": 3,
            "evidence_seen": len(entries),
            "source": f"ibit-backtest 90d window; manifest config_hash={manifest.get('config_hash', '?')[:16]}",
        },
        "shadow_budget": {
            "cap": 2,
            "current_active": 0,
        },
        "contributor_credit": {
            "ping_required": False,
            "pinged_at": None,
            "ping_wait_hours": 48,
            "ack_received": False,
        },
        "promotion_bar": {
            "min_entries": max(30, min_entries),
            "min_observation_days": 30,
            "min_hit_rate_spread_pp": max(5, min_spread_pp),
            "direction_match_required": False,
            "retire_after_days": max(30, period_days),
        },
        "rollback": {
            "on_bar_fail": "retire_and_archive",
            "on_bug_discovered": "reset_capital_and_window",
            "on_confounding_shadow": "isolate_and_continue",
        },
    }


def export_shadow(
    run_dir_str: str,
    output_dir_str: str | None = None,
    rule_name: str | None = None,
    min_entries: int = 30,
    min_spread_pp: float = 5.0,
    direction: str = "both",
) -> int:
    """Convert a backtest run into harness-compatible inputs. Returns exit code."""
    run_dir = Path(run_dir_str).expanduser().resolve()
    if not run_dir.exists():
        print(f"[export-shadow] run dir not found: {run_dir}", file=sys.stderr)
        return 2

    try:
        manifest, events = _load_run(run_dir)
    except Exception as e:
        print(f"[export-shadow] failed to load run: {e}", file=sys.stderr)
        return 2

    entries = [e for e in events if e.get("kind") == "ENTRY"]
    exits = [e for e in events if e.get("kind") == "EXIT"]
    if not entries:
        print(f"[export-shadow] no ENTRY events in {run_dir}", file=sys.stderr)
        return 2

    base_name = rule_name or manifest["strategy_name"]
    proposal_id = _slugify(f"backtest_{manifest['run_id']}")
    out_dir = Path(output_dir_str).expanduser().resolve() if output_dir_str else run_dir / "harness-export"
    out_dir.mkdir(parents=True, exist_ok=True)

    fires_path = out_dir / "fires.jsonl"
    try:
        fires_rel = str(fires_path.relative_to(HARNESS_ROOT))
    except ValueError:
        print(
            f"[export-shadow] output dir {out_dir} must be under {HARNESS_ROOT} "
            f"(harness requires shadow_log_jsonl relative to ~/ibitlabs/)",
            file=sys.stderr,
        )
        return 2

    n_fires = _write_fires_jsonl(fires_path, entries, proposal_id, base_name)
    db_path = out_dir / "trade_log.db"
    n_closes = _write_trade_log_db(db_path, exits)
    proposal = _build_proposal_dict(
        proposal_id=proposal_id,
        rule_name=base_name,
        manifest=manifest,
        entries=entries,
        fires_path_rel_ibitlabs=fires_rel,
        min_entries=min_entries,
        min_spread_pp=min_spread_pp,
        direction=direction,
    )
    proposal_path = out_dir / "proposal.yaml"
    proposal_path.write_text(yaml.safe_dump(proposal, sort_keys=False, allow_unicode=True))

    print(f"[export-shadow] {n_fires} fires -> {fires_path}")
    print(f"[export-shadow] {n_closes} closes -> {db_path}")
    print(f"[export-shadow] proposal -> {proposal_path}")
    print()
    print("Run harness gate:")
    print(f"  python3 {HARNESS_ROOT}/harness/bin/promote_bar.py {proposal_path} --db {db_path}")
    return 0
