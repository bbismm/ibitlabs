#!/usr/bin/env python3
"""
export_mcp_data.py
Generates two static JSON files consumed by the ibitlabs MCP server:
  - web/public/data/recent_trades.json   → get_recent_trades tool
  - web/public/data/rule_status.json     → get_rule_status tool

Run after every sniper check (morning + evening) via launchd wrapper,
or manually: python3 scripts/export_mcp_data.py

No LLM calls. No external APIs. Pure local DB + JSONL reads.
"""

import json
import sqlite3
import glob
import os
import sys
from datetime import datetime, timezone

REPO_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH    = os.path.join(REPO_ROOT, "sol_sniper.db")
LOGS_DIR   = os.path.join(REPO_ROOT, "logs")
OUT_DIR    = os.path.join(REPO_ROOT, "web", "public", "data")
CONTRIB    = os.path.join(OUT_DIR, "contributors.json")

RECENT_TRADES_OUT = os.path.join(OUT_DIR, "recent_trades.json")
RULE_STATUS_OUT   = os.path.join(OUT_DIR, "rule_status.json")


# ─── Recent Trades ────────────────────────────────────────────────────────────

def export_recent_trades(n: int = 20) -> dict:
    db  = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute("""
        SELECT id, symbol, direction, entry_price, exit_price, exit_reason,
               pnl, fees, funding, regime, mfe, mae, strategy_version, timestamp
        FROM trade_log
        WHERE exit_price IS NOT NULL AND pnl IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT ?
    """, (n,))
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        row = dict(zip(cols, raw))
        # humanise timestamp
        row["closed_at_iso"] = datetime.fromtimestamp(
            row["timestamp"], tz=timezone.utc
        ).isoformat() if row["timestamp"] else None
        row["pnl"]     = round(row["pnl"], 4)     if row["pnl"]     else None
        row["fees"]    = round(row["fees"], 4)     if row["fees"]    else None
        row["funding"] = round(row["funding"], 6)  if row["funding"] else None
        row["mfe"]     = round(row["mfe"], 6)      if row["mfe"]     else None
        row["mae"]     = round(row["mae"], 6)      if row["mae"]     else None
        rows.append(row)
    db.close()

    # running win-rate from returned slice
    wins   = sum(1 for r in rows if (r["pnl"] or 0) > 0)
    total  = len(rows)

    result = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": "sol_sniper.db::trade_log",
        "count": total,
        "slice_win_rate": round(wins / total, 4) if total else None,
        "trades": rows,
    }
    with open(RECENT_TRADES_OUT, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[export_mcp_data] recent_trades: {total} trades written")
    return result


# ─── Rule Status ──────────────────────────────────────────────────────────────

# Map rule_id → which JSONL field carries the "bucket" label
RULE_BUCKET_FIELD = {
    "C": "edge_kill_condition_met",  # bool
    "D": "dominance_ratio",          # float → bucket by threshold
    "E": "rolling_sortino",          # float → positive / near_zero / negative
    "F": "atr_regime",               # "compression" / "neutral" / "expansion"
    "G": "_seed_only",               # special: G is seed-only, no real fires
}

def _bucket_value(rule_id: str, entry: dict) -> str:
    field = RULE_BUCKET_FIELD.get(rule_id)
    if not field:
        return "unknown"
    # G is seed-only — no real observations
    if field == "_seed_only":
        return "seed_only"
    val = entry.get(field)
    if val is None:
        return "unknown"
    if isinstance(val, bool):
        return "fired" if val else "not_fired"
    if isinstance(val, (int, float)):
        if rule_id == "E":  # rolling_sortino
            if val > 0.05:   return "positive"
            if val < -0.05:  return "negative"
            return "near_zero"
        if rule_id == "D":  # dominance_ratio
            thresh = entry.get("dominance_threshold", 0.5)
            return "dominant" if val >= thresh else "not_dominant"
        return str(round(val, 4))
    return str(val)


def _load_exit_reasons() -> dict:
    """Return {entry_ts_rounded: exit_reason} from trade_log for closed trades."""
    mapping = {}
    try:
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        cur.execute("""
            SELECT timestamp, entry_price, exit_reason, pnl
            FROM trade_log
            WHERE exit_price IS NOT NULL AND pnl IS NOT NULL
        """)
        for ts, ep, reason, pnl in cur.fetchall():
            # key: entry_price rounded to 2dp (shadow JSONL also stores entry_price)
            # secondary: close_ts for collision resolution when same entry_price repeats
            key_ep   = round(float(ep), 2)
            key_full = (key_ep, round(float(ts), 0))
            val = reason or ("win" if (pnl or 0) > 0 else "loss")
            mapping[key_full] = val
            # also index by entry_price alone (for shadow entries that lack close_ts)
            mapping.setdefault(key_ep, val)
        db.close()
    except Exception:
        pass
    return mapping


_EXIT_REASONS: dict = {}  # lazy-loaded once


def _hit_rate(entries):
    """
    TP or trailing_stop_above_entry = win.
    Uses exit_reason from the shadow entry if present,
    else falls back to matching entry_ts against trade_log.
    """
    global _EXIT_REASONS
    if not _EXIT_REASONS:
        _EXIT_REASONS = _load_exit_reasons()

    wins = 0
    counted = 0
    for e in entries:
        # Try inline exit_reason first, then JOIN by (entry_price, entry_ts)
        reason = e.get("exit_reason")
        if not reason:
            ep  = round(float(e.get("entry_price", 0)), 2)
            reason = _EXIT_REASONS.get(ep)  # entry_price-only key
        if reason is None:
            continue  # trade still open — skip from denominator
        counted += 1
        if reason in ("tp", "trailing", "trailing_stop_above_entry", "win"):
            wins += 1
    return round(wins / counted, 4) if counted else None


def export_rule_status():
    # Load contributors for metadata
    contrib = {}
    if os.path.exists(CONTRIB):
        with open(CONTRIB) as f:
            d = json.load(f)
        for row in d.get("adopted", []) + d.get("queued_for_review", []):
            rid = row.get("rule_id")
            if rid:
                contrib[rid] = row

    rules_out = {}

    for jsonl_path in sorted(glob.glob(os.path.join(LOGS_DIR, "shadow_*.jsonl"))):
        entries = []
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not entries:
            continue

        rule_id   = entries[0].get("rule_id", "?")
        rule_name = entries[0].get("rule_name", os.path.basename(jsonl_path))
        proposed  = entries[0].get("proposed_by", "unknown")

        # Per-bucket breakdown
        buckets: dict[str, list[dict]] = {}
        for e in entries:
            b = _bucket_value(rule_id, e)
            buckets.setdefault(b, []).append(e)

        bucket_stats = {}
        for bucket, bents in buckets.items():
            bucket_stats[bucket] = {
                "count":    len(bents),
                "hit_rate": _hit_rate(bents),
            }

        # Spread (max - min hit rate across buckets with count >= 5)
        rates = [
            v["hit_rate"]
            for v in bucket_stats.values()
            if v["count"] >= 5 and v["hit_rate"] is not None
        ]
        spread = round(max(rates) - min(rates), 4) if len(rates) >= 2 else None

        # Promotion bar from contributors.json
        meta = contrib.get(rule_id, {})
        review_date = meta.get("shadow_window_review")

        rules_out[rule_id] = {
            "rule_id":        rule_id,
            "rule_name":      rule_name,
            "proposed_by":    proposed,
            "moltbook_url":   meta.get("moltbook_url"),
            "source_post":    meta.get("source_post"),
            "adopted_on":     meta.get("adopted_on"),
            "review_date":    review_date,
            "review_status":  meta.get("review_status"),
            "total_fires":    len(entries),
            "bucket_stats":   bucket_stats,
            "hit_rate_spread": spread,
            "promotion_bar": {
                "min_per_bucket":  30,
                "min_spread_pp":   15,
                "direction_check": "compression best (Lona's hypothesis)" if rule_id == "F" else "see contributors.json",
                "spread_so_far_pp": round((spread or 0) * 100, 1),
                "ready":           (spread is not None and spread * 100 >= 15 and
                                    all(v["count"] >= 30 for v in bucket_stats.values())),
            },
            "jsonl_path": os.path.relpath(jsonl_path, REPO_ROOT),
        }

    result = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "rules": rules_out,
    }
    with open(RULE_STATUS_OUT, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[export_mcp_data] rule_status: {len(rules_out)} rules written")
    return result


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    export_recent_trades(n=20)
    export_rule_status()
    print("[export_mcp_data] done")
