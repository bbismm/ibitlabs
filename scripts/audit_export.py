#!/usr/bin/env python3
"""
audit_export.py — unified read-only export of iBitLabs trading state.

Aggregates the six existing data sources into two artifacts:
  1. trades.jsonl   — one JSON event per trade row, all instances unioned
  2. state.json     — current live snapshot (open position + watchdog + reconciliation)

Read-only. Touches nothing the bot writes. Safe to run while the bot is live.

Usage:
    python3 audit_export.py
    python3 audit_export.py --out-dir ~/ibitlabs/audit_export
    python3 audit_export.py --summary           # also print stats to stdout
    python3 audit_export.py --instance live     # filter to one instance

Designed to be runnable on demand and re-runnable. Output is deterministic:
re-running with the same DBs produces the same files (modulo "exported_at").
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LIVE_STATUS_URL = os.environ.get("LIVE_STATUS_URL", "http://localhost:8086/api/live-status")

IBITLABS = Path(os.environ.get("IBITLABS_DIR", os.path.expanduser("~/ibitlabs")))

# (db_filename, instance_label). Add new instances here when promoted.
INSTANCES: list[tuple[str, str]] = [
    ("sol_sniper.db", "live"),
    ("sol_sniper_shadow.db", "shadow"),
    ("sol_sniper_eth_paper.db", "eth_paper"),
]

TRADE_COLS = (
    "id, symbol, side, direction, entry_price, exit_price, quantity, "
    "pnl, fees, funding, exit_reason, regime, mfe, mae, "
    "strategy_version, strategy_intent, trigger_rule, instance_name, timestamp"
)


def utc_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def export_trades(out_path: Path, instance_filter: str | None) -> dict:
    """Read every db, emit one JSONL line per trade_log row, return per-instance counts."""
    counts: dict[str, int] = {}
    with out_path.open("w", encoding="utf-8") as f:
        for fname, label in INSTANCES:
            if instance_filter and label != instance_filter:
                continue
            db = IBITLABS / fname
            if not db.exists():
                continue
            try:
                conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                cur = conn.execute(f"SELECT {TRADE_COLS} FROM trade_log ORDER BY id")
                cols = [c[0] for c in cur.description]
                for row in cur:
                    rec = dict(zip(cols, row))
                    rec["instance"] = label
                    rec["ts_utc"] = utc_iso(rec.pop("timestamp"))
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    counts[label] = counts.get(label, 0) + 1
                conn.close()
            except sqlite3.Error as e:
                print(f"WARN: skipped {fname}: {e}", file=sys.stderr)
    return counts


def fetch_live_status() -> dict | None:
    """Best-effort fetch of /api/live-status — fail silently if bot/API down."""
    try:
        with urllib.request.urlopen(LIVE_STATUS_URL, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def export_state(out_path: Path) -> dict:
    """Snapshot of operational state — open position, watchdog, reconciliation,
    AND canonical PnL from /api/live-status (the public number).

    Writes both 'balance_pnl' (= API total_pnl, balance - starting_capital,
    canonical for $1k → $10k narrative) and 'strategy_pnl' (= sum trade_log.pnl,
    closed trades only). Difference = unrealized + funding revenue."""
    snap: dict = {"exported_at": utc_iso(datetime.now(tz=timezone.utc).timestamp())}

    for key, rel in [
        ("position",       "sol_sniper_state.json"),
        ("ghost_watchdog", "state/ghost_watchdog_state.json"),
        ("reconciliation", "state/reconciliation_status.json"),
    ]:
        p = IBITLABS / rel
        snap[key] = json.loads(p.read_text()) if p.exists() else None

    live = fetch_live_status()
    if live:
        snap["live_status"] = {
            "ts": live.get("ts"),
            "snapshot_seq": live.get("snapshot_seq"),
            "balance": live.get("balance"),
            "starting_capital": live.get("starting_capital"),
            "balance_pnl_canonical": live.get("total_pnl"),     # = balance - starting_capital
            "strategy_pnl_closed_trades": live.get("strategy_pnl"),  # = sum trade_log.pnl
            "unrealized_pnl": live.get("unrealized_pnl"),
            "funding_cost": live.get("funding_cost"),
            "total_fees": live.get("total_fees"),
            "total_trades": live.get("total_trades"),
            "win_rate": live.get("win_rate"),
            "regime": live.get("regime"),
            "mode": live.get("mode"),
        }
    else:
        snap["live_status"] = None  # bot/API unreachable at export time

    out_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False))
    return snap


def print_summary(jsonl_path: Path) -> None:
    by_inst: dict[str, dict] = {}
    with jsonl_path.open() as f:
        for line in f:
            r = json.loads(line)
            inst = r["instance"]
            d = by_inst.setdefault(inst, {"n": 0, "wins": 0, "losses": 0, "pnl": 0.0, "fees": 0.0, "funding": 0.0})
            d["n"] += 1
            pnl = r.get("pnl") or 0
            if r.get("exit_price") is not None:  # closed trade
                if pnl > 0: d["wins"] += 1
                elif pnl < 0: d["losses"] += 1
            d["pnl"] += pnl or 0
            d["fees"] += r.get("fees") or 0
            d["funding"] += r.get("funding") or 0

    print(f"{'instance':<12} {'rows':>6} {'closes':>7} {'wins':>5} {'losses':>7} {'win%':>6} {'pnl_usd':>10} {'fees':>8} {'funding':>9}")
    print("-" * 78)
    for inst, d in sorted(by_inst.items()):
        closes = d["wins"] + d["losses"]
        wr = (d["wins"] / closes * 100) if closes else 0.0
        print(f"{inst:<12} {d['n']:>6} {closes:>7} {d['wins']:>5} {d['losses']:>7} {wr:>5.1f}% {d['pnl']:>10.2f} {d['fees']:>8.2f} {d['funding']:>9.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(IBITLABS / "audit_export"))
    ap.add_argument("--instance", default=None, help="filter to one instance")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    out = Path(os.path.expanduser(args.out_dir))
    out.mkdir(parents=True, exist_ok=True)
    jsonl = out / "trades.jsonl"
    state = out / "state.json"

    counts = export_trades(jsonl, args.instance)
    snap = export_state(state)

    print(f"trades.jsonl  → {jsonl}  ({sum(counts.values())} rows: {counts})")
    print(f"state.json    → {state}  (position={'OPEN' if (snap.get('position') or {}).get('position') else 'flat'})")
    if snap.get("live_status"):
        ls = snap["live_status"]
        print(f"  canonical balance PnL (API):  {ls['balance_pnl_canonical']:+.2f}")
        print(f"  strategy PnL (closed trades): {ls['strategy_pnl_closed_trades']:+.2f}")
    else:
        print(f"  live-status API unreachable — state.json has no canonical balance PnL")

    if args.summary:
        print()
        print_summary(jsonl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
