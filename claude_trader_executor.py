#!/usr/bin/env python3
"""
claude_trader_executor.py — Phase 0 executor + risk_guards for claude-trader.

Reads ~/ibitlabs/logs/claude-trader/decisions.jsonl (produced by the
claude-trader skill), processes new decisions through risk_guards, and either:
  - DRY_RUN=1 (default): logs "would execute" to executions.jsonl
  - DRY_RUN=0:           executes via Coinbase API (Phase 0 Day 3+ flip)

Idempotent via a cursor file (~/ibitlabs/logs/claude-trader/.cursor) holding
the last-processed decision's `fire_ts`. Designed to be invoked from a cron
or launchd plist every 5 min; safe to invoke manually.

Schema-only validation (2026-05-25 founder call: hard constraints removed):
  - action in {ENTER, HOLD, EXIT}
  - ENTER has a valid direction (long/short)
  - EXIT requires position open

Sizing, leverage, balance floor, cohort blocks, position concurrency, symbol
scope — all moved to Claude's discretion. Executor validates schema only.

Run: python3 ~/ibitlabs/claude_trader_executor.py
Flip live: export CLAUDE_TRADER_DRY_RUN=0
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path.home() / "ibitlabs"
LOG_DIR = REPO / "logs" / "claude-trader"
DECISIONS_FILE = LOG_DIR / "decisions.jsonl"
EXECUTIONS_FILE = LOG_DIR / "executions.jsonl"
CURSOR_FILE = LOG_DIR / ".cursor"

LIVE_STATUS_URL = "https://www.ibitlabs.com/api/live-status"

# Default: dry run. Flip via env to enable real trades.
DRY_RUN = os.environ.get("CLAUDE_TRADER_DRY_RUN", "1") == "1"

# ntfy topic — same as v5.3 sniper's channel so Bonny watches one feed.
NTFY_TOPIC = os.environ.get("CLAUDE_TRADER_NTFY_TOPIC", "sol-sniper-bonny")
NTFY_ENABLED = os.environ.get("CLAUDE_TRADER_NTFY", "1") == "1"


def ntfy_push(title: str, body: str, priority: str = "default", tags: str = "") -> None:
    """
    Push to ntfy.sh. Silent failure — never breaks the executor.
    priority: 'min' / 'low' / 'default' / 'high' / 'urgent'
    tags: comma-sep emoji-mappable tags ('trade', 'warning', 'rotating_light' etc).
    """
    if not NTFY_ENABLED:
        return
    safe_title = (title or "claude-trader").replace("\n", " ").strip()[:150]
    headers = {
        "Title": safe_title,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = tags
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=(body or "").encode("utf-8"),
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        print(f"  ntfy push failed: {e}", file=sys.stderr)


# ── risk_guards ──────────────────────────────────────────────────────────────


def validate_decision(decision: dict, live_status: dict) -> tuple[bool, list[str]]:
    """Schema validation + fee-adjusted EV gate for ENTERs.

    Sizing / leverage / cohort / balance / symbol are all Claude's call. The
    only HARD constraint the executor enforces (besides schema) is the EV
    gate: at sub-$1000 balance, the experiment's structural fight is "edge >
    friction" and ENTERs whose expected gross PnL fails to beat ~1.8× the
    round-trip fee are systematic losers regardless of conviction. Per
    founder note 2026-05-25.
    """
    fails: list[str] = []

    action = decision.get("decision")
    if action not in ("ENTER", "HOLD", "EXIT"):
        fails.append(f"unknown decision action: {action!r}")
        return False, fails

    if action == "ENTER":
        direction = decision.get("direction")
        if direction not in ("long", "short"):
            fails.append(f"ENTER missing valid direction: {direction!r}")

        # Fee-adjusted EV gate. Claude is expected to compute the check
        # itself and include `fee_adjusted_ev_check.passed` in the decision.
        # We re-verify here as belt-and-suspenders.
        ev = decision.get("fee_adjusted_ev_check") or {}
        if not ev:
            fails.append(
                "ENTER missing required `fee_adjusted_ev_check` "
                "(see SKILL § Fee-adjusted EV gate)"
            )
        else:
            ratio = ev.get("ratio")
            passed = ev.get("passed")
            if not isinstance(ratio, (int, float)):
                fails.append(f"fee_adjusted_ev_check.ratio not numeric: {ratio!r}")
            elif ratio < 1.8:
                fails.append(
                    f"fee_adjusted_ev_check ratio {ratio:.2f} < 1.8 — "
                    f"expected gross does not beat 1.8× round-trip fee. "
                    f"This is the HARD EV gate in 扭亏 phase."
                )
            elif passed is False:
                fails.append(
                    f"fee_adjusted_ev_check.passed=False (Claude self-flagged), "
                    f"ratio={ratio}"
                )

    if action == "EXIT":
        pos = live_status.get("position")
        if pos is None:
            fails.append("EXIT but no position open")

    return (len(fails) == 0), fails


# ── data loaders ─────────────────────────────────────────────────────────────


def fetch_live_status(timeout: float = 5.0) -> dict:
    """Pull current /api/live-status. Returns minimal dict if endpoint fails."""
    try:
        req = urllib.request.Request(
            LIVE_STATUS_URL,
            headers={"User-Agent": "claude-trader-executor/0.1 (+ibitlabs.com)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception as e:
        return {"_error": repr(e), "balance": 0, "position": None}


def read_cursor() -> float:
    """Return last-processed fire_ts (epoch). 0 if cursor missing."""
    if not CURSOR_FILE.exists():
        return 0.0
    try:
        return float(CURSOR_FILE.read_text().strip())
    except (ValueError, OSError):
        return 0.0


def write_cursor(fire_ts: float) -> None:
    CURSOR_FILE.write_text(f"{fire_ts:.6f}\n")


def read_new_decisions(after_ts: float) -> list[dict]:
    """Read decisions.jsonl, return decisions strictly newer than after_ts."""
    if not DECISIONS_FILE.exists():
        return []
    out: list[dict] = []
    with open(DECISIONS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            fts = float(d.get("fire_ts", 0))
            if fts > after_ts:
                out.append(d)
    return out


# ── executor ─────────────────────────────────────────────────────────────────


def log_execution(record: dict) -> None:
    """Append one record to executions.jsonl."""
    with open(EXECUTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def execute_or_log(decision: dict, live_status: dict, ok: bool, fails: list[str]) -> dict:
    """
    Phase 0: always log, only actually trade if DRY_RUN=0 AND ok=True AND
    decision is ENTER or EXIT. Returns execution record.
    """
    action = decision.get("decision")
    record: dict[str, Any] = {
        "schema_version": 1,
        "execution_ts": time.time(),
        "decision_fire_ts": decision.get("fire_ts"),
        "decision_fire_iso": decision.get("fire_iso"),
        "decision_action": action,
        "decision_direction": decision.get("direction"),
        "live_status_balance": float(live_status.get("balance", 0)),
        "live_status_position": live_status.get("position"),
        "live_status_price": live_status.get("current_price")
            or live_status.get("indicators", {}).get("price"),
        "guards_passed": ok,
        "guards_fails": fails,
        "dry_run": DRY_RUN,
        "outcome": None,
    }

    if action == "HOLD":
        record["outcome"] = "noop_hold"
        log_execution(record)
        # silent — too noisy to push every HOLD
        return record

    if not ok:
        record["outcome"] = "rejected_by_guards"
        log_execution(record)
        ntfy_push(
            title=f"[claude-trader] GUARD REJECT {action} {decision.get('direction','?')}",
            body=(
                f"Claude proposed {action} {decision.get('direction','?')} "
                f"qty={decision.get('quantity','?')} lev={decision.get('leverage','?')} "
                f"but failed risk_guards:\n  - " + "\n  - ".join(fails) +
                f"\n\nreasoning: {decision.get('reasoning','')[:300]}"
            ),
            priority="high",
            tags="warning",
        )
        return record

    if DRY_RUN:
        record["outcome"] = (
            f"dry_run_would_{action.lower()}_"
            f"{decision.get('direction','')}_qty{decision.get('quantity','?')}"
            f"_lev{decision.get('leverage','?')}"
        )
        log_execution(record)
        ntfy_push(
            title=f"[claude-trader DRY_RUN] would {action} {decision.get('direction','?')}",
            body=(
                f"Claude proposed {action} {decision.get('direction','?')} "
                f"qty={decision.get('quantity','?')} lev={decision.get('leverage','?')} "
                f"@ price ${record.get('live_status_price','?')}\n"
                f"balance=${record.get('live_status_balance','?'):.2f} regime={decision.get('regime','?')}\n"
                f"confidence={decision.get('confidence','?')}\n\n"
                f"reasoning: {decision.get('reasoning','')[:400]}\n\n"
                f"→ Review decisions.jsonl + flip DRY_RUN=0 if this looks sound."
            ),
            priority="high",
            tags="trade",
        )
        return record

    # ── Live execution path (Phase 0 Day 3+) ─────────────────────────────────
    # Intentionally not yet wired. Day 3+: import sol_sniper_executor +
    # CoinbaseExchange, instantiate minimal SniperExecutor, call open_position
    # with size override. For now, raise to force operator awareness.
    record["outcome"] = "live_path_not_wired_yet"
    record["error"] = (
        "claude_trader_executor live path is intentionally unwired. "
        "Flip DRY_RUN=0 only after wiring Phase 0 Day 3 plan."
    )
    log_execution(record)
    ntfy_push(
        title=f"[claude-trader] LIVE PATH NOT WIRED — {action} blocked",
        body=(
            f"DRY_RUN=0 is set but Phase 0 Day 3 live wiring is not done.\n"
            f"Decision was {action} {decision.get('direction','?')} "
            f"qty={decision.get('quantity','?')} lev={decision.get('leverage','?')}.\n"
            f"Either flip DRY_RUN=1 or finish wiring sol_sniper_executor integration."
        ),
        priority="urgent",
        tags="rotating_light",
    )
    return record


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    if not LOG_DIR.exists():
        print(f"FATAL: log dir missing: {LOG_DIR}", file=sys.stderr)
        return 2

    cursor = read_cursor()
    new_decisions = read_new_decisions(cursor)
    if not new_decisions:
        print(f"[claude-trader-executor] no new decisions since fire_ts {cursor:.0f}")
        return 0

    live_status = fetch_live_status()
    if "_error" in live_status:
        print(f"[claude-trader-executor] WARN: live-status fetch failed: {live_status['_error']}")
        # Continue anyway — we'll log validation failures but not trade

    print(f"[claude-trader-executor] processing {len(new_decisions)} new decision(s) "
          f"(DRY_RUN={int(DRY_RUN)})")

    latest_ts = cursor
    for d in new_decisions:
        ok, fails = validate_decision(d, live_status)
        rec = execute_or_log(d, live_status, ok, fails)
        print(f"  fire_ts={d.get('fire_ts'):.0f} action={d.get('decision')} "
              f"direction={d.get('direction')} ok={ok} outcome={rec.get('outcome')}")
        if fails:
            for f in fails:
                print(f"    fail: {f}")
        latest_ts = max(latest_ts, float(d.get("fire_ts", 0)))

    write_cursor(latest_ts)
    return 0


if __name__ == "__main__":
    # Wrap main() so any unhandled exception fires an urgent ntfy before
    # we propagate exit != 0. Without this, Python tracebacks land in
    # stderr.log and stay invisible until someone tails the file.
    import traceback
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        tb = traceback.format_exc()
        # Keep ntfy body manageable; truncate huge tracebacks.
        body = (
            f"Unhandled {type(exc).__name__} in claude_trader_executor.\n\n"
            f"{tb[-800:]}\n\n"
            f"Check ~/ibitlabs/logs/claude-trader/executor.stderr.log for full trace. "
            f"Next 5min cron will retry."
        )
        ntfy_push(
            title=f"[claude-trader-executor] CRASH — {type(exc).__name__}",
            body=body,
            priority="urgent",
            tags="rotating_light",
        )
        raise
