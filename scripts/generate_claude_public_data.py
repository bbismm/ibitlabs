#!/usr/bin/env python3
"""
Generate the public-facing JSON for /lab/claude.

Reads ~/ibitlabs/logs/claude-trader/decisions.jsonl and produces a curated,
public-safe snapshot at ~/ibitlabs/web/public/data/claude_trader.json with the
latest decision + last 20 decisions + summary stats.

Called by run_claude_trader.sh after each fire. Idempotent on the input file —
no state, no side effects beyond the output JSON.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from collections import Counter

HOME = Path.home()
DECISIONS_FILE = HOME / "ibitlabs/logs/claude-trader/decisions.jsonl"
FRAMEWORK_FILE = HOME / "ibitlabs/logs/claude-trader/framework_log.jsonl"
FOUNDER_NOTES_FILE = HOME / "ibitlabs/logs/claude-trader/founder_notes.jsonl"
MISSED_SETUPS_FILE = HOME / "ibitlabs/logs/claude-trader/missed_setups.jsonl"
STATE_FILE = HOME / "ibitlabs/state/claude_trader_state.json"
BUDGET_STATE_FILE = HOME / "ibitlabs/state/claude_trader_uncertainty_budget.json"
PAPER_STATE_PATH = HOME / "ibitlabs/state/claude_trader_paper_state.json"
PAPER_TRADES_PATH = HOME / "ibitlabs/logs/claude-trader/paper_trades.jsonl"
EXECUTIONS_PATH = HOME / "ibitlabs/logs/claude-trader/executions.jsonl"
OUTPUT_FILE = HOME / "ibitlabs/web/public/data/claude_trader.json"

# How many framework reflections to include in the public history.
FRAMEWORK_HISTORY_LIMIT = 10

# How many events to include in the public timeline (most recent first).
EVENT_TIMELINE_LIMIT = 30

# How many founder notes / missed setups to surface in the public JSON.
FOUNDER_NOTES_LIMIT = 10
MISSED_SETUPS_LIMIT = 10

# How many paper trades (most recent) to include in the public JSON.
PAPER_TRADES_LIMIT = 20

# Reasoning text in paper position/trade records is trimmed before going
# public — full text already lives in decisions.jsonl on disk.
PAPER_REASONING_PUBLIC_CHARS = 600

# Schema version of the OUTPUT artifact (separate from per-decision schema_version).
# v3: dropped verbose `recent` stream; added `events` timeline + `hold_summary`.
# v4: added `founder_notes` channel, `state_snapshot`, `missed_setups`.
# v5: epistemic upgrade — founder notes carry type/confidence/claims[].
# v6: cognition_mode protocol (Phase B.1) — adds `cognition` rollup in summary,
#     surfaces cognition_mode + rationale + cadence_hint + skipped_fires_in_mode
#     for the always-visible mode strip. Wrapper gate may now skip fires when
#     mode permits, so `latest.fire_iso` is no longer a guaranteed 5min cadence.
# v7: tiered grading + uncertainty budget (founder design 2026-05-26) —
#     adds `summary.grades` (S/A/B/C distribution) + top-level
#     `uncertainty_budget` snapshot. Filters _test_synthetic (since v6.1).
#     Surfaces the "exploration authorization" layer to the public page.
# v8: paper trading layer (2026-05-27) — adds top-level `paper` block with
#     state snapshot + summary (WR/PF/avg hold) + last-N closed trades.
#     `mode` field now reflects actual executor mode from executions.jsonl
#     instead of hardcoded "DRY_RUN" — flips to "PAPER" when CLAUDE_TRADER_PAPER=1.
PUBLIC_SCHEMA_VERSION = 8


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
                d = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines; never break public output on parse error.
                continue
            # Filter operator-injected synthetic test entries (e.g. Phase 0
            # LIVE-gate wiring validation, 2026-05-26). They remain in the
            # jsonl for audit trail but must never count toward public
            # decisions_total / actions / events / hold_summary, because
            # they did not originate from Claude's cognition layer.
            if d.get("_test_synthetic"):
                continue
            out.append(d)
    return out


def sanitize(d: dict) -> dict:
    """Return a public-safe view of a decision. Today the input is already
    public-safe (no secrets, no operational data beyond balance), but keep this
    boundary so future schema additions are intentional, not accidental.

    Schema additions 2026-05-26: grade / size_multiplier / setup_type / sl_pct /
    hypothetical_entry_record / no_plausible_counterfactual (tiered grading +
    counterfactual shadow on HOLD).
    """
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
        "grade": d.get("grade"),
        "size_multiplier": d.get("size_multiplier"),
        "setup_type": d.get("setup_type"),
        "direction": d.get("direction"),
        "symbol": d.get("symbol"),
        "quantity": d.get("quantity"),
        "leverage": d.get("leverage"),
        "sl_pct": d.get("sl_pct"),
        "confidence": d.get("confidence"),
        "reasoning": d.get("reasoning"),
        "expected_holding_hours": d.get("expected_holding_hours"),
        "expected_pnl_pct_target": d.get("expected_pnl_pct_target"),
        "abort_conditions": d.get("abort_conditions"),
        "hypothetical_entry_record": d.get("hypothetical_entry_record"),
        "no_plausible_counterfactual": d.get("no_plausible_counterfactual"),
        "exploration_attribution": d.get("exploration_attribution"),
        "information_roi_record": d.get("information_roi_record"),
    }


def compute_grade_distribution(decisions: list[dict]) -> dict:
    """Tiered S/A/B/C grade counter (founder design 2026-05-26). Counts each
    decision by its (action, grade) combination + flags HOLDs that include a
    hypothetical_entry_record (counterfactual shadow) vs raw HOLDs.

    Pre-2026-05-27 decisions have no `grade` field — bucketed as
    `ENTER_no_grade` / `HOLD` to preserve historical visibility.
    """
    out = Counter()
    for d in decisions:
        action = (d.get("decision") or "").upper()
        grade = d.get("grade")
        if action == "ENTER":
            key = f"ENTER_{grade}" if grade in ("S", "A", "B", "C") else "ENTER_no_grade"
        elif action == "HOLD":
            if d.get("hypothetical_entry_record"):
                key = "HOLD_with_counterfactual"
            elif d.get("no_plausible_counterfactual"):
                key = "HOLD_no_plausible"
            else:
                key = "HOLD"
        elif action == "EXIT":
            key = "EXIT"
        else:
            key = action or "UNKNOWN"
        out[key] += 1
    return dict(out)


def load_budget_state(path: Path):
    """Read the daily uncertainty budget snapshot. Returns dict or None."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


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
        "grades": compute_grade_distribution(decisions),
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


def load_jsonl(path: Path) -> list[dict]:
    """Generic JSONL loader. Skips malformed lines silently — never breaks
    public output on parse error."""
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


def load_state_snapshot(path: Path):
    """Read the persistent state file. Returns dict or None on missing/invalid."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def annotate_founder_notes(notes: list[dict], reflections: list[dict]) -> list[dict]:
    """For each note, attach per-claim addressing status.

    A claim is identified by (note_ts, claim_id). For each claim we attach
    the matching reflection response (response_type / how / planned_change /
    reflection_version / reflection_iso), or None if pending. Note-level
    `claims_addressed_count` and `claims_pending_count` are computed for
    quick page rendering.
    """
    # Build (note_ts, claim_id) → response map across all reflections.
    response_map: dict[tuple, dict] = {}
    for r in reflections:
        addressed = r.get("founder_notes_addressed") or []
        for entry in addressed:
            note_ts = entry.get("note_ts")
            claim_id = entry.get("claim_id")
            if note_ts is None:
                continue
            key = (float(note_ts), claim_id)
            response_map[key] = {
                "reflection_version": r.get("version_tag"),
                "reflection_iso": r.get("iso"),
                "response_type": entry.get("response_type"),
                "how": entry.get("how"),
                "planned_change": entry.get("planned_change"),
            }

    out = []
    for n in notes:
        nn = dict(n)
        nts = float(n.get("ts") or 0)
        claims = list(n.get("claims") or [])
        annotated_claims = []
        addressed_count = 0
        for c in claims:
            claim_id = c.get("claim_id")
            response = response_map.get((nts, claim_id))
            cc = dict(c)
            cc["addressed_in"] = response  # None if still pending
            if response is not None:
                addressed_count += 1
            annotated_claims.append(cc)

        nn["claims"] = annotated_claims
        nn["claims_total"] = len(claims)
        nn["claims_addressed_count"] = addressed_count
        nn["claims_pending_count"] = len(claims) - addressed_count

        # Back-compat: still expose a note-level "addressed_in" — set to the
        # most-recent claim-level response if every claim is addressed,
        # else None. UI fallback when v1-style notes appear.
        if claims and addressed_count == len(claims):
            # pick the most-recent reflection that touched any claim of this note
            touched = [
                response_map[(nts, c.get("claim_id"))]
                for c in claims
                if (nts, c.get("claim_id")) in response_map
            ]
            nn["addressed_in"] = touched[0] if touched else None
        elif not claims:
            # legacy v1 note (no claims[] array): fall back to note-level match
            nn["addressed_in"] = response_map.get((nts, None))
        else:
            nn["addressed_in"] = None

        out.append(nn)
    return out


def compute_lineage_stats(notes: list[dict]) -> dict:
    """Roll up across all (annotated) notes: how many claims by type, how
    accept-rate splits by type / confidence. Designed to be queried over
    long history; today it's tiny but will grow."""
    by_type: dict[str, dict] = {}
    by_confidence: dict[str, dict] = {}
    response_counts = {"accepted": 0, "rejected": 0, "refined": 0, "pending": 0}

    def _bucket(d: dict, key: str) -> dict:
        if key not in d:
            d[key] = {"total": 0, "accepted": 0, "rejected": 0, "refined": 0, "pending": 0}
        return d[key]

    total_claims = 0
    for n in notes:
        claims = n.get("claims") or []
        for c in claims:
            total_claims += 1
            ctype = c.get("type") or "unknown"
            cconf = c.get("confidence") or "unknown"
            response = c.get("addressed_in")
            rtype = (response or {}).get("response_type")
            slot = "pending"
            if rtype in ("accepted", "rejected", "refined"):
                slot = rtype
            response_counts[slot] += 1
            _bucket(by_type, ctype)["total"] += 1
            _bucket(by_type, ctype)[slot] += 1
            _bucket(by_confidence, cconf)["total"] += 1
            _bucket(by_confidence, cconf)[slot] += 1

    return {
        "claims_total": total_claims,
        "response_mix": response_counts,
        "by_type": by_type,
        "by_confidence": by_confidence,
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


def detect_executor_mode(path: Path) -> str:
    """Read the tail of executions.jsonl to find the actual mode the
    executor is running in. Falls back to DRY_RUN if file missing or empty.

    Why tail-based: the plist env vars are the source of truth for the
    cron's environment, but reading them from the public-page generator is
    awkward. The executor stamps `mode` into every execution record, so the
    last record is the authoritative recent reading.
    """
    if not path.exists():
        return "DRY_RUN"
    last_mode = None
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                m = rec.get("mode")
                if m:
                    last_mode = m
    except OSError:
        return "DRY_RUN"
    if not last_mode:
        return "DRY_RUN"
    return str(last_mode).upper()  # paper → PAPER


def _sanitize_paper_position(pos: dict | None) -> dict | None:
    """Return a public-safe view of the current open paper position.
    Trims reasoning to PAPER_REASONING_PUBLIC_CHARS."""
    if not pos:
        return None
    reasoning = pos.get("entry_reasoning") or ""
    if len(reasoning) > PAPER_REASONING_PUBLIC_CHARS:
        reasoning = reasoning[:PAPER_REASONING_PUBLIC_CHARS] + "…"
    return {
        "symbol": pos.get("symbol"),
        "symbol_base": pos.get("symbol_base"),
        "direction": pos.get("direction"),
        "qty": pos.get("qty"),
        "leverage": pos.get("leverage"),
        "contract_size": pos.get("contract_size"),
        "entry_price": pos.get("entry_price"),
        "entry_ts": pos.get("entry_ts"),
        "entry_iso": pos.get("entry_iso"),
        "entry_fire_ts": pos.get("entry_fire_ts"),
        "entry_fire_iso": pos.get("entry_fire_iso"),
        "entry_notional": pos.get("entry_notional"),
        "entry_fee": pos.get("entry_fee"),
        "entry_regime": pos.get("entry_regime"),
        "entry_confidence": pos.get("entry_confidence"),
        "entry_reasoning": reasoning,
    }


def _sanitize_paper_trade(t: dict) -> dict:
    """Return a public-safe view of a closed paper trade. Trims reasonings."""
    def _trim(s):
        if not s:
            return None
        return s if len(s) <= PAPER_REASONING_PUBLIC_CHARS else s[:PAPER_REASONING_PUBLIC_CHARS] + "…"
    return {
        "entry_fire_ts": t.get("entry_fire_ts"),
        "entry_fire_iso": t.get("entry_fire_iso"),
        "exit_fire_ts": t.get("exit_fire_ts"),
        "exit_fire_iso": t.get("exit_fire_iso"),
        "closed_iso": t.get("closed_iso"),
        "symbol": t.get("symbol"),
        "direction": t.get("direction"),
        "qty": t.get("qty"),
        "leverage": t.get("leverage"),
        "entry_price": t.get("entry_price"),
        "exit_price": t.get("exit_price"),
        "hold_seconds": t.get("hold_seconds"),
        "gross_pnl": t.get("gross_pnl"),
        "total_fees": t.get("total_fees"),
        "net_pnl": t.get("net_pnl"),
        "entry_regime": t.get("entry_regime"),
        "exit_regime": t.get("exit_regime"),
        "entry_confidence": t.get("entry_confidence"),
        "exit_confidence": t.get("exit_confidence"),
        "entry_reasoning": _trim(t.get("entry_reasoning")),
        "exit_reasoning": _trim(t.get("exit_reasoning")),
    }


def compute_paper_summary(state: dict | None, trades: list[dict]) -> dict:
    """Profit factor, win rate, avg hold, etc. Returns an empty-but-typed
    dict when there are no closed trades — keeps the page render
    consistent with later data."""
    summary = {
        "trades_total": 0,
        "wins": 0,
        "losses": 0,
        "scratches": 0,  # net_pnl == 0 to the cent
        "win_rate_pct": None,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "profit_factor": None,
        "avg_win": None,
        "avg_loss": None,
        "avg_hold_minutes": None,
        "max_win": None,
        "max_loss": None,
        "long_wins": 0, "long_losses": 0,
        "short_wins": 0, "short_losses": 0,
    }
    if not trades:
        return summary

    wins = [t for t in trades if (t.get("net_pnl") or 0) > 0]
    losses = [t for t in trades if (t.get("net_pnl") or 0) < 0]
    scratches = [t for t in trades if (t.get("net_pnl") or 0) == 0]

    gross_profit = sum(t.get("net_pnl") or 0 for t in wins)
    gross_loss_abs = abs(sum(t.get("net_pnl") or 0 for t in losses))
    hold_seconds = [t.get("hold_seconds") or 0 for t in trades]

    summary["trades_total"] = len(trades)
    summary["wins"] = len(wins)
    summary["losses"] = len(losses)
    summary["scratches"] = len(scratches)
    summary["win_rate_pct"] = (
        round(100.0 * len(wins) / len(trades), 1) if trades else None
    )
    summary["gross_profit"] = round(gross_profit, 4)
    summary["gross_loss"] = round(gross_loss_abs, 4)
    summary["profit_factor"] = (
        round(gross_profit / gross_loss_abs, 3)
        if gross_loss_abs > 0
        else (None if not wins else float("inf"))
    )
    summary["avg_win"] = round(gross_profit / len(wins), 4) if wins else None
    summary["avg_loss"] = round(-gross_loss_abs / len(losses), 4) if losses else None
    summary["avg_hold_minutes"] = (
        round(sum(hold_seconds) / len(hold_seconds) / 60.0, 2) if hold_seconds else None
    )
    summary["max_win"] = round(max((t.get("net_pnl") or 0) for t in trades), 4)
    summary["max_loss"] = round(min((t.get("net_pnl") or 0) for t in trades), 4)

    for t in trades:
        d = t.get("direction")
        pnl = t.get("net_pnl") or 0
        if d == "long":
            if pnl > 0:
                summary["long_wins"] += 1
            elif pnl < 0:
                summary["long_losses"] += 1
        elif d == "short":
            if pnl > 0:
                summary["short_wins"] += 1
            elif pnl < 0:
                summary["short_losses"] += 1

    # Infinite profit_factor isn't JSON-friendly; mark it explicitly.
    if summary["profit_factor"] == float("inf"):
        summary["profit_factor"] = None
        summary["profit_factor_inf"] = True

    return summary


def build_paper_block(
    state_path: Path,
    trades_path: Path,
) -> dict | None:
    """Read paper state + trades + assemble the public-facing paper block.
    Returns None if no paper state exists yet (paper mode never ran)."""
    state = load_state_snapshot(state_path)
    if state is None:
        return None
    trades = load_jsonl(trades_path)
    summary = compute_paper_summary(state, trades)
    sanitized_trades = [_sanitize_paper_trade(t) for t in trades]
    # Most-recent first; cap to limit.
    sanitized_trades.sort(key=lambda t: t.get("closed_iso") or "", reverse=True)
    sanitized_trades = sanitized_trades[:PAPER_TRADES_LIMIT]

    return {
        "starting_cash": state.get("starting_cash"),
        "cash": state.get("cash"),
        "cumulative_net_pnl": state.get("cumulative_net_pnl"),
        "cumulative_gross_pnl": state.get("cumulative_gross_pnl"),
        "cumulative_fees": state.get("cumulative_fees"),
        "opened_count": state.get("opened_count"),
        "closed_count": state.get("closed_count"),
        "position": _sanitize_paper_position(state.get("position")),
        "trades_recent": sanitized_trades,
        "summary": summary,
        "started_iso": state.get("started_iso"),
        "updated_iso": state.get("updated_iso"),
    }


def main() -> int:
    decisions = load_decisions(DECISIONS_FILE)
    reflections = load_framework_reflections(FRAMEWORK_FILE)
    founder_notes_raw = load_jsonl(FOUNDER_NOTES_FILE)
    missed_setups = load_jsonl(MISSED_SETUPS_FILE)
    state_snapshot = load_state_snapshot(STATE_FILE)

    founder_notes = annotate_founder_notes(founder_notes_raw, reflections)
    # "Pending" now means: at least one claim within the note is unaddressed.
    pending_count = sum(1 for n in founder_notes if (n.get("claims_pending_count") or 0) > 0)
    lineage_stats = compute_lineage_stats(founder_notes)

    base = {
        "public_schema_version": PUBLIC_SCHEMA_VERSION,
        "generated_at": int(time.time()),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "experiment": "iBitLabs claude-trader Phase 0",
        "mode": detect_executor_mode(EXECUTIONS_PATH),
    }

    paper_block = build_paper_block(PAPER_STATE_PATH, PAPER_TRADES_PATH)

    # Cognition rollup — convenience extraction of cognition_mode fields from
    # the state snapshot, so the page doesn't have to dig into state_snapshot.
    cognition = None
    if state_snapshot:
        cognition = {
            "mode": state_snapshot.get("cognition_mode"),
            "since_iso": state_snapshot.get("cognition_mode_since_iso"),
            "rationale": state_snapshot.get("cognition_mode_rationale"),
            "cadence_hint": state_snapshot.get("cognition_mode_cadence_hint"),
            "skipped_fires_in_mode": state_snapshot.get("skipped_fires_in_mode") or 0,
            "last_mode_transition_iso": state_snapshot.get("last_mode_transition_iso"),
            "last_gate_check_iso": state_snapshot.get("last_gate_check_iso"),
        }

    # Origin reflections — any framework_log entry whose trigger starts with
    # "bootstrap:" is an archive-level artifact: the first self-declaration of
    # an ontology layer. We surface them separately so the page can render an
    # ORIGIN badge even after later reflections push the bootstrap out of the
    # "latest" slot. There may be multiple origins over time as new ontology
    # layers ship (e.g. cognition_mode bootstrap, future market_phenomenology
    # bootstrap, etc.) — keep the full list, chronological.
    origin_reflections = [
        r for r in reflections
        if str(r.get("trigger") or "").startswith("bootstrap:")
    ]

    # Uncertainty budget snapshot (founder design 2026-05-26) — gives the
    # public page direct visibility into the exploration authorization layer:
    # daily $-budget, spent_today, forced_exploration_due, holds_in_a_row,
    # threshold_state. Surfaces the "why HOLD streak is now a failure mode,
    # not a virtue" reframing.
    budget_state = load_budget_state(BUDGET_STATE_FILE)

    common_extras = {
        "founder_notes_recent": list(reversed(founder_notes[-FOUNDER_NOTES_LIMIT:])),
        "founder_notes_total": len(founder_notes),
        "founder_notes_pending": pending_count,
        "lineage_stats": lineage_stats,
        "missed_setups_recent": list(reversed(missed_setups[-MISSED_SETUPS_LIMIT:])),
        "missed_setups_total": len(missed_setups),
        "state_snapshot": state_snapshot,
        "cognition": cognition,
        "framework_origins": origin_reflections,  # full list, chronological
        "uncertainty_budget": budget_state,
        "paper": paper_block,
    }

    if not decisions:
        print(f"WARN: no decisions found at {DECISIONS_FILE}", file=sys.stderr)
        out = {
            **base,
            "summary": {
                "decisions_total": 0,
                "framework_reflections_total": len(reflections),
                "founder_notes_total": len(founder_notes),
                "founder_notes_pending": pending_count,
                "missed_setups_total": len(missed_setups),
            },
            "latest": None,
            "events": [],
            "hold_summary": {"holds_since_framework": 0, "avg_chars": 0, "since_iso": None},
            "framework_latest": reflections[-1] if reflections else None,
            "framework_recent": list(reversed(reflections[-FRAMEWORK_HISTORY_LIMIT:])),
            **common_extras,
        }
    else:
        sanitized = [sanitize(d) for d in decisions]
        summary = compute_summary(sanitized)
        summary["framework_reflections_total"] = len(reflections)
        summary["founder_notes_total"] = len(founder_notes)
        summary["founder_notes_pending"] = pending_count
        summary["missed_setups_total"] = len(missed_setups)
        out = {
            **base,
            "summary": summary,
            "latest": sanitized[-1],
            "events": compute_events(sanitized, reflections),
            "hold_summary": compute_hold_summary(sanitized, reflections),
            "framework_latest": reflections[-1] if reflections else None,
            "framework_recent": list(reversed(reflections[-FRAMEWORK_HISTORY_LIMIT:])),
            **common_extras,
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
