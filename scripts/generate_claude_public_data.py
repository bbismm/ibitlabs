#!/usr/bin/env python3
"""
Generate the public-facing JSON for /lab/claude.

Reads ~/ibitlabs/logs/claude-trader/decisions.jsonl and produces a curated,
public-safe snapshot at ~/ibitlabs/web/public/data/claude_trader.json with the
latest decision + last 20 decisions + summary stats.

Called by run_claude_trader.sh after each fire. Idempotent on the input file —
no state, no side effects beyond the output JSON.
"""

import json
import os
import sys
import time
from pathlib import Path
from collections import Counter

HOME = Path.home()
DECISIONS_FILE = HOME / "ibitlabs/logs/claude-trader/decisions.jsonl"
OUTPUT_FILE = HOME / "ibitlabs/web/public/data/claude_trader.json"

# How many decisions to include in the public "recent" stream.
RECENT_LIMIT = 20

# Schema version of the OUTPUT artifact (separate from per-decision schema_version).
PUBLIC_SCHEMA_VERSION = 1


def load_decisions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines; never break public output on parse error.
                continue
    return out


def sanitize(d: dict) -> dict:
    """Return a public-safe view of a decision. Today the input is already
    public-safe (no secrets, no operational data beyond balance), but keep this
    boundary so future schema additions are intentional, not accidental."""
    return {
        "fire_ts": d.get("fire_ts"),
        "fire_iso": d.get("fire_iso"),
        "session_phase": d.get("session_phase"),
        "balance_usd": d.get("balance_usd"),
        "position_at_fire": d.get("position_at_fire"),
        "current_price": d.get("current_price"),
        "regime": d.get("regime"),
        "market_snapshot": d.get("market_snapshot"),
        "decision": d.get("decision"),
        "direction": d.get("direction"),
        "symbol": d.get("symbol"),
        "quantity": d.get("quantity"),
        "leverage": d.get("leverage"),
        "confidence": d.get("confidence"),
        "reasoning": d.get("reasoning"),
        "expected_holding_hours": d.get("expected_holding_hours"),
        "expected_pnl_pct_target": d.get("expected_pnl_pct_target"),
        "abort_conditions": d.get("abort_conditions"),
    }


def compute_summary(decisions: list[dict]) -> dict:
    """Aggregate counts + simple stats. All HOLDs today, but schema supports
    ENTER/EXIT as they arrive."""
    actions = Counter(d.get("decision") for d in decisions)
    confs = Counter(d.get("confidence") for d in decisions)
    reasoning_chars = [len(d.get("reasoning") or "") for d in decisions]
    avg_chars = sum(reasoning_chars) // len(reasoning_chars) if reasoning_chars else 0
    last_chars = (
        sum(reasoning_chars[-10:]) // min(10, len(reasoning_chars))
        if reasoning_chars
        else 0
    )

    first_fire = decisions[0].get("fire_iso") if decisions else None
    last_fire = decisions[-1].get("fire_iso") if decisions else None
    balance_latest = (
        decisions[-1].get("balance_usd") if decisions else None
    )
    starting_balance = 1000.0  # Per project memory: $1k → $10k experiment.

    pnl_delta = (
        round(balance_latest - starting_balance, 2)
        if balance_latest is not None
        else None
    )

    return {
        "decisions_total": len(decisions),
        "actions": dict(actions),
        "confidence": dict(confs),
        "reasoning_chars_avg_all": avg_chars,
        "reasoning_chars_avg_last10": last_chars,
        "first_fire_iso": first_fire,
        "last_fire_iso": last_fire,
        "balance_usd_latest": balance_latest,
        "starting_balance_usd": starting_balance,
        "pnl_total_usd": pnl_delta,
    }


def main() -> int:
    decisions = load_decisions(DECISIONS_FILE)
    if not decisions:
        print(f"WARN: no decisions found at {DECISIONS_FILE}", file=sys.stderr)
        # Still write an empty-state file so the page renders cleanly.
        out = {
            "public_schema_version": PUBLIC_SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "experiment": "iBitLabs claude-trader Phase 0",
            "mode": "DRY_RUN",
            "summary": {"decisions_total": 0},
            "latest": None,
            "recent": [],
        }
    else:
        sanitized = [sanitize(d) for d in decisions]
        out = {
            "public_schema_version": PUBLIC_SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "experiment": "iBitLabs claude-trader Phase 0",
            "mode": "DRY_RUN",
            "summary": compute_summary(sanitized),
            "latest": sanitized[-1],
            "recent": list(reversed(sanitized[-RECENT_LIMIT:])),
        }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
    os.replace(tmp, OUTPUT_FILE)
    print(
        f"wrote {OUTPUT_FILE} | "
        f"decisions={out['summary'].get('decisions_total', 0)} | "
        f"latest={out['latest']['decision'] if out['latest'] else 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
