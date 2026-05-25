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
FRAMEWORK_FILE = HOME / "ibitlabs/logs/claude-trader/framework_log.jsonl"
OUTPUT_FILE = HOME / "ibitlabs/web/public/data/claude_trader.json"

# How many framework reflections to include in the public history.
FRAMEWORK_HISTORY_LIMIT = 10

# How many events to include in the public timeline (most recent first).
EVENT_TIMELINE_LIMIT = 30

# Schema version of the OUTPUT artifact (separate from per-decision schema_version).
# v3: dropped verbose `recent` stream (20 full HOLD reasonings was noise); added
#     `events` timeline (framework + non-HOLD + regime flips + confidence shifts +
#     first-under-framework) and `hold_summary` pulse counter.
PUBLIC_SCHEMA_VERSION = 3


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


def compute_events(decisions: list[dict], reflections: list[dict]) -> list[dict]:
    """Walk decisions + reflections chronologically and emit only the events
    worth showing on the public page. Repeating frozen-tape HOLDs are not
    events; they live in the rolling `hold_summary` counter instead.

    Event types:
      - framework_reflection — every entry from framework_log.jsonl
      - first_under_framework — the first decision whose fire_ts >= a given
        reflection's ts (shows model → action coupling)
      - enter / exit — any non-HOLD decision
      - regime_flip — decision where regime != prior decision's regime
      - confidence_shift — decision where confidence changed from prior
    """
    events: list[dict] = []

    # Reflections become events directly.
    for r in reflections:
        events.append({
            "type": "framework_reflection",
            "ts": r.get("ts"),
            "iso": r.get("iso"),
            "fire_count": r.get("fire_count"),
            "summary": (
                f"Framework {r.get('version_tag') or 'v?'} written "
                f"(trigger: {r.get('trigger') or 'unknown'})"
            ),
            "payload": r,
        })

    # First-under-framework: find the first decision whose fire_ts >= reflection.ts.
    # If a later reflection supersedes, the next first-under is its own.
    for r in reflections:
        r_ts = r.get("ts") or 0
        match = next(
            (d for d in decisions if (d.get("fire_ts") or 0) >= r_ts),
            None,
        )
        if match is not None:
            events.append({
                "type": "first_under_framework",
                "ts": match.get("fire_ts"),
                "iso": match.get("fire_iso"),
                "fire_count": None,  # 1-based line index assigned below
                "summary": (
                    f"First decision under framework {r.get('version_tag') or 'v?'}: "
                    f"{match.get('decision')}"
                ),
                "payload": sanitize(match),
                "_framework_version": r.get("version_tag"),
            })

    # Walk decisions, annotate regime flips + confidence shifts + non-HOLDs.
    prior = None
    for idx, d in enumerate(decisions):
        d_type = None
        d_summary = None

        action = (d.get("decision") or "").upper()
        if action == "ENTER":
            d_type = "enter"
            d_summary = (
                f"ENTER {d.get('direction') or '?'} "
                f"{d.get('symbol') or '?'} @ ${d.get('current_price')} "
                f"qty={d.get('quantity')} lev={d.get('leverage')}"
            )
        elif action == "EXIT":
            d_type = "exit"
            d_summary = (
                f"EXIT {d.get('symbol') or '?'} @ ${d.get('current_price')}"
            )

        if d_type is None and prior is not None:
            if d.get("regime") != prior.get("regime"):
                d_type = "regime_flip"
                d_summary = (
                    f"Regime: {prior.get('regime')} → {d.get('regime')} "
                    f"@ ${d.get('current_price')}"
                )
            elif d.get("confidence") != prior.get("confidence"):
                d_type = "confidence_shift"
                d_summary = (
                    f"Confidence: {prior.get('confidence')} → {d.get('confidence')} "
                    f"(decision still {d.get('decision')})"
                )

        if d_type is not None:
            events.append({
                "type": d_type,
                "ts": d.get("fire_ts"),
                "iso": d.get("fire_iso"),
                "fire_count": idx + 1,
                "summary": d_summary,
                "payload": sanitize(d),
            })

        prior = d

    # Sort chronologically descending, cap to the timeline limit.
    events.sort(key=lambda e: e.get("ts") or 0, reverse=True)
    return events[:EVENT_TIMELINE_LIMIT]


def compute_hold_summary(decisions: list[dict], reflections: list[dict]) -> dict:
    """Pulse counter. How much frozen-tape HOLD activity has Claude logged
    since the most recent framework reflection? Repeating HOLDs are not
    individually shown on the page; this summary represents them collectively."""
    if not decisions:
        return {"holds_since_framework": 0, "avg_chars": 0, "since_iso": None}

    latest_r_ts = (reflections[-1].get("ts") if reflections else 0) or 0
    since = [
        d for d in decisions
        if (d.get("fire_ts") or 0) >= latest_r_ts
        and (d.get("decision") or "").upper() == "HOLD"
    ]
    if not since:
        return {"holds_since_framework": 0, "avg_chars": 0, "since_iso": None}

    chars = [len(d.get("reasoning") or "") for d in since]
    return {
        "holds_since_framework": len(since),
        "avg_chars": sum(chars) // len(chars),
        "since_iso": (
            reflections[-1].get("iso") if reflections else since[0].get("fire_iso")
        ),
        "since_framework_version": (
            reflections[-1].get("version_tag") if reflections else None
        ),
        "latest_fire_iso": decisions[-1].get("fire_iso"),
    }


def load_framework_reflections(path: Path) -> list[dict]:
    """Each line is one reflection. Schema fields documented in SKILL.md
    § Framework reflection. We pass them through largely as-is — they are
    Claude's first-class artifact and the public page renders them prominently."""
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
                continue
    return out


def main() -> int:
    decisions = load_decisions(DECISIONS_FILE)
    reflections = load_framework_reflections(FRAMEWORK_FILE)

    base = {
        "public_schema_version": PUBLIC_SCHEMA_VERSION,
        "generated_at": int(time.time()),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "experiment": "iBitLabs claude-trader Phase 0",
        "mode": "DRY_RUN",
    }

    if not decisions:
        print(f"WARN: no decisions found at {DECISIONS_FILE}", file=sys.stderr)
        out = {
            **base,
            "summary": {"decisions_total": 0, "framework_reflections_total": len(reflections)},
            "latest": None,
            "events": [],
            "hold_summary": {"holds_since_framework": 0, "avg_chars": 0, "since_iso": None},
            "framework_latest": reflections[-1] if reflections else None,
            "framework_recent": list(reversed(reflections[-FRAMEWORK_HISTORY_LIMIT:])),
        }
    else:
        sanitized = [sanitize(d) for d in decisions]
        summary = compute_summary(sanitized)
        summary["framework_reflections_total"] = len(reflections)
        out = {
            **base,
            "summary": summary,
            "latest": sanitized[-1],
            "events": compute_events(sanitized, reflections),
            "hold_summary": compute_hold_summary(sanitized, reflections),
            "framework_latest": reflections[-1] if reflections else None,
            "framework_recent": list(reversed(reflections[-FRAMEWORK_HISTORY_LIMIT:])),
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
