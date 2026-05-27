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

# Three execution modes, resolved at module load:
#   PAPER    — simulate fills against /api/live-status price; materialize PnL
#   DRY_RUN  — log "would execute" only (Phase 0 default before paper landed)
#   LIVE     — real Coinbase orders (Phase 0 Day 3+, NOT YET WIRED)
# Mode priority: PAPER > LIVE > DRY_RUN. PAPER overrides DRY_RUN — if Bonny
# wants observable simulation, dry logs would be dead weight.
DRY_RUN = os.environ.get("CLAUDE_TRADER_DRY_RUN", "1") == "1"
PAPER_RUN = os.environ.get("CLAUDE_TRADER_PAPER", "0") == "1"

# Paper-mode artifacts. State is a single JSON object (one position max,
# matches Claude's current mental model). Trade ledger is jsonl, append-only,
# one line per closed trade.
PAPER_STATE_FILE = REPO / "state" / "claude_trader_paper_state.json"
PAPER_TRADES_FILE = LOG_DIR / "paper_trades.jsonl"
PAPER_DEFAULT_SYMBOL = os.environ.get("CLAUDE_TRADER_PAPER_SYMBOL", "SOL").upper()
PAPER_STARTING_CASH = float(os.environ.get("CLAUDE_TRADER_PAPER_CASH", "1000.0"))
# Coinbase INTX perp tier-1 taker ≈ 0.06%. Conservative: charge taker both sides.
PAPER_FEE_RATE_PER_SIDE = float(os.environ.get("CLAUDE_TRADER_PAPER_FEE_RATE", "0.0006"))
# Contract sizes per symbol (Coinbase perp conventions; extend as Claude
# proposes other symbols). SOL=5 means qty=1 → notional = 5 × price.
# Claude has emitted variants like "SOL-PERP", "ETH-PERP-INTX", "BTC/USD",
# so we normalize the symbol to its base ticker before lookup.
CONTRACT_SIZE = {"SOL": 5.0, "ETH": 0.01, "BTC": 0.001}


def base_symbol(symbol: str) -> str:
    """Normalize a Claude-emitted symbol to its base ticker (SOL, ETH, BTC, ...).

    Strips common perpetual / settlement suffixes by looping until stable, so
    compound forms like BTC-USDC-PERP → BTC-USDC → BTC reduce all the way.
    """
    if not symbol:
        return ""
    s = symbol.upper().replace("/", "-").replace("_", "-")
    suffixes = ("-PERP", "-INTX", "-USDC", "-USDT", "-USD", "-BUSD")
    changed = True
    while changed:
        changed = False
        for suf in suffixes:
            if s.endswith(suf) and len(s) > len(suf):
                s = s[: -len(suf)]
                changed = True
                break
    return s

# ntfy topic — same as v5.3 sniper's channel so Bonny watches one feed.
NTFY_TOPIC = os.environ.get("CLAUDE_TRADER_NTFY_TOPIC", "sol-sniper-bonny")
NTFY_ENABLED = os.environ.get("CLAUDE_TRADER_NTFY", "1") == "1"


def execution_mode() -> str:
    if PAPER_RUN:
        return "paper"
    if DRY_RUN:
        return "dry_run"
    return "live"


MODE = execution_mode()


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
    """Schema-only validation for claude-trader decisions.

    Per founder call 2026-05-25 + framework v0.9 (fire 127, 2026-05-26):
    the prior 1.8× fee-adjusted EV gate is retracted. Two reasons:
      1. The arithmetic was wrong. SOL perp `contract_size=5` means qty=2 at
         $85 is ~$850 notional, not ~$170. The "1.8× → ~1.1% target" framing
         was actually ~0.22% — zero discriminatory power on the 33-trade
         ledger (any T ∈ [1.0, 3.0] keeps the same 23 winners and blocks the
         same 10 losers).
      2. Fee drag is real but n=1 (#373) on the ledger, not the binding
         bleeding mechanism. The 9 SL-cluster trades are the real PnL killer.

    Binding criterion now lives at the cognition layer (cohort × asymmetry
    × structural trigger — see SKILL § Build your framework). Executor
    enforces SCHEMA only.

    Required schema:
      - decision in {ENTER, HOLD, EXIT}
      - ENTER: valid direction (long | short)
      - EXIT: live_status.position must not be None

    Sizing / leverage / cohort / balance / symbol / fee-friction trade-offs
    are all Claude's call.
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

    if action == "EXIT":
        # In paper mode, "position open" means the paper book, not live.
        # During the DRY_RUN→PAPER transition Claude may still be "managing"
        # an internal hypothetical position from earlier fires. EXIT without
        # a paper position is logged as a soft reject (handled downstream as
        # `rejected_by_guards`) — not a crash, just a no-op until Claude
        # opens a real paper position.
        if PAPER_RUN:
            ps = load_paper_state()
            if ps.get("position") is None:
                fails.append("EXIT but no paper position open")
        else:
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


# ── paper engine ─────────────────────────────────────────────────────────────


def load_paper_state() -> dict:
    """Read paper state from disk. If missing, return fresh starting state."""
    if not PAPER_STATE_FILE.exists():
        now = time.time()
        return {
            "position": None,
            "cash": PAPER_STARTING_CASH,
            "starting_cash": PAPER_STARTING_CASH,
            "opened_count": 0,
            "closed_count": 0,
            "cumulative_gross_pnl": 0.0,
            "cumulative_fees": 0.0,
            "cumulative_net_pnl": 0.0,
            "started_at": now,
            "started_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        }
    with open(PAPER_STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_paper_state(state: dict) -> None:
    """Persist paper state atomically (write-then-rename)."""
    PAPER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = time.time()
    state["updated_iso"] = time.strftime(
        "%Y-%m-%dT%H:%M:%S%z", time.localtime(state["updated_at"])
    )
    tmp = PAPER_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    tmp.replace(PAPER_STATE_FILE)


def paper_open(decision: dict, current_price: float) -> tuple[bool, str, dict]:
    """Open a paper position. Returns (ok, message, paper_state_after)."""
    state = load_paper_state()
    if state.get("position") is not None:
        pos = state["position"]
        return (
            False,
            f"paper position already open ({pos['direction']} {pos['symbol']} qty={pos['qty']})",
            state,
        )
    if not current_price or current_price <= 0:
        return False, "no current_price available; cannot mark entry", state

    raw_symbol = (decision.get("symbol") or PAPER_DEFAULT_SYMBOL).upper()
    symbol_base = base_symbol(raw_symbol)
    direction = decision.get("direction")
    qty = float(decision.get("quantity") or 0)
    lev = float(decision.get("leverage") or 1.0)
    contract_size = CONTRACT_SIZE.get(symbol_base, 1.0)

    if direction not in ("long", "short"):
        return False, f"invalid direction {direction!r}", state
    if qty <= 0:
        return False, f"invalid qty {qty}", state

    notional = qty * contract_size * current_price
    entry_fee = notional * PAPER_FEE_RATE_PER_SIDE

    state["position"] = {
        "symbol": raw_symbol,
        "symbol_base": symbol_base,
        "direction": direction,
        "qty": qty,
        "leverage": lev,
        "contract_size": contract_size,
        "entry_price": current_price,
        "entry_ts": time.time(),
        "entry_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "entry_fire_ts": decision.get("fire_ts"),
        "entry_fire_iso": decision.get("fire_iso"),
        "entry_notional": notional,
        "entry_fee": entry_fee,
        "entry_regime": decision.get("regime"),
        "entry_confidence": decision.get("confidence"),
        "entry_reasoning": (decision.get("reasoning") or "")[:1500],
    }
    state["cash"] -= entry_fee
    state["cumulative_fees"] += entry_fee
    state["opened_count"] += 1
    save_paper_state(state)
    return (
        True,
        (
            f"paper_opened_{direction}_{raw_symbol}_qty{qty:g}_lev{lev:g}"
            f"_@{current_price:.4f}_notional${notional:.2f}_fee${entry_fee:.2f}"
        ),
        state,
    )


def paper_close(decision: dict, current_price: float) -> tuple[bool, str, dict, dict | None]:
    """Close paper position. Returns (ok, message, paper_state_after, trade_record_or_None)."""
    state = load_paper_state()
    pos = state.get("position")
    if pos is None:
        return False, "no paper position to close (EXIT ignored)", state, None
    if not current_price or current_price <= 0:
        return False, "no current_price available; cannot mark exit", state, None

    qty = pos["qty"]
    contract_size = pos["contract_size"]
    exit_notional = qty * contract_size * current_price
    exit_fee = exit_notional * PAPER_FEE_RATE_PER_SIDE

    if pos["direction"] == "long":
        gross_pnl = (current_price - pos["entry_price"]) * qty * contract_size
    else:  # short
        gross_pnl = (pos["entry_price"] - current_price) * qty * contract_size

    total_fees = pos["entry_fee"] + exit_fee
    net_pnl = gross_pnl - total_fees
    now = time.time()
    hold_seconds = now - pos["entry_ts"]

    trade = {
        "schema_version": 1,
        "entry_fire_ts": pos["entry_fire_ts"],
        "entry_fire_iso": pos["entry_fire_iso"],
        "exit_fire_ts": decision.get("fire_ts"),
        "exit_fire_iso": decision.get("fire_iso"),
        "closed_ts": now,
        "closed_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        "symbol": pos["symbol"],
        "direction": pos["direction"],
        "qty": qty,
        "leverage": pos["leverage"],
        "contract_size": contract_size,
        "entry_price": pos["entry_price"],
        "exit_price": current_price,
        "hold_seconds": hold_seconds,
        "entry_notional": pos["entry_notional"],
        "exit_notional": exit_notional,
        "gross_pnl": gross_pnl,
        "entry_fee": pos["entry_fee"],
        "exit_fee": exit_fee,
        "total_fees": total_fees,
        "net_pnl": net_pnl,
        "entry_regime": pos.get("entry_regime"),
        "exit_regime": decision.get("regime"),
        "entry_confidence": pos.get("entry_confidence"),
        "exit_confidence": decision.get("confidence"),
        "entry_reasoning": pos.get("entry_reasoning"),
        "exit_reasoning": (decision.get("reasoning") or "")[:1500],
    }
    with open(PAPER_TRADES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(trade, ensure_ascii=False) + "\n")

    # entry_fee was already deducted at open; here we settle gross_pnl - exit_fee.
    state["cash"] += gross_pnl - exit_fee
    state["cumulative_fees"] += exit_fee
    state["cumulative_gross_pnl"] += gross_pnl
    state["cumulative_net_pnl"] += net_pnl
    state["closed_count"] += 1
    state["position"] = None
    save_paper_state(state)
    return (
        True,
        (
            f"paper_closed_{pos['direction']}_{pos['symbol']}_qty{qty:g}"
            f"_@{current_price:.4f}_pnl${net_pnl:+.2f}_held{int(hold_seconds)}s"
        ),
        state,
        trade,
    )


# ── executor ─────────────────────────────────────────────────────────────────


def log_execution(record: dict) -> None:
    """Append one record to executions.jsonl."""
    with open(EXECUTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def execute_or_log(decision: dict, live_status: dict, ok: bool, fails: list[str]) -> dict:
    """
    Process one decision under the active mode (paper / dry_run / live).
    HOLD short-circuits before mode branching; guard-rejects too.
    Returns execution record (also appended to executions.jsonl).
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
        "mode": MODE,
        "dry_run": DRY_RUN,  # kept for backward-compat with existing tooling
        "paper_run": PAPER_RUN,
        "outcome": None,
    }
    # Forward synthetic-test markers so the audit trail stays honest when an
    # operator injects a wiring-validation entry.
    if decision.get("_test_synthetic"):
        record["_test_synthetic"] = True
        if decision.get("_test_purpose"):
            record["_test_purpose"] = decision["_test_purpose"]

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

    # ── PAPER mode ───────────────────────────────────────────────────────
    if MODE == "paper":
        # Prefer Claude's OHLCV-derived current_price from the decision over
        # the live-status pipe price. As of 2026-05-27 the v5.3 indicators
        # pipeline has been stale 47h+ — paper fills against that price are
        # meaningless. Claude derives current_price from fresh OHLCV in its
        # data sources, so `decision.current_price` is the right fill source.
        # Fall back to live-status only if decision lacks it.
        current_price = float(
            decision.get("current_price")
            or record.get("live_status_price")
            or 0
        )
        record["paper_fill_price"] = current_price
        record["paper_fill_price_source"] = (
            "decision.current_price"
            if decision.get("current_price")
            else "live_status.current_price"
        )
        if action == "ENTER":
            success, msg, new_state = paper_open(decision, current_price)
            record["outcome"] = msg if success else f"paper_enter_failed: {msg}"
            record["paper_state"] = {
                "position": new_state.get("position"),
                "cash": new_state.get("cash"),
                "cumulative_net_pnl": new_state.get("cumulative_net_pnl"),
                "opened_count": new_state.get("opened_count"),
                "closed_count": new_state.get("closed_count"),
            }
            log_execution(record)
            ntfy_push(
                title=(
                    f"[claude-trader PAPER] OPEN {decision.get('direction','?')} "
                    f"qty={decision.get('quantity','?')}"
                    if success
                    else f"[claude-trader PAPER] ENTER REJECTED"
                ),
                body=(
                    f"{msg}\n\n"
                    f"balance=${new_state.get('cash', 0):.2f}  "
                    f"cum_net_pnl=${new_state.get('cumulative_net_pnl', 0):+.2f}\n"
                    f"opened={new_state.get('opened_count', 0)}  "
                    f"closed={new_state.get('closed_count', 0)}\n\n"
                    f"reasoning: {(decision.get('reasoning') or '')[:400]}"
                ),
                priority="high" if success else "default",
                tags="trade" if success else "warning",
            )
            return record

        if action == "EXIT":
            success, msg, new_state, trade = paper_close(decision, current_price)
            record["outcome"] = msg if success else f"paper_exit_failed: {msg}"
            record["paper_state"] = {
                "position": new_state.get("position"),
                "cash": new_state.get("cash"),
                "cumulative_net_pnl": new_state.get("cumulative_net_pnl"),
                "opened_count": new_state.get("opened_count"),
                "closed_count": new_state.get("closed_count"),
            }
            if trade is not None:
                record["paper_trade"] = trade
            log_execution(record)
            if success and trade is not None:
                pnl = trade["net_pnl"]
                hold_min = trade["hold_seconds"] / 60.0
                ntfy_push(
                    title=f"[claude-trader PAPER] CLOSE pnl ${pnl:+.2f}",
                    body=(
                        f"{msg}\n\n"
                        f"hold={hold_min:.1f}min  "
                        f"entry@${trade['entry_price']:.4f} → exit@${trade['exit_price']:.4f}\n"
                        f"balance=${new_state.get('cash', 0):.2f}  "
                        f"cum_net_pnl=${new_state.get('cumulative_net_pnl', 0):+.2f}\n"
                        f"closed={new_state.get('closed_count', 0)}\n\n"
                        f"exit reasoning: {(decision.get('reasoning') or '')[:400]}"
                    ),
                    priority="high",
                    tags="chart_with_upwards_trend" if pnl >= 0 else "chart_with_downwards_trend",
                )
            else:
                ntfy_push(
                    title=f"[claude-trader PAPER] EXIT REJECTED",
                    body=(
                        f"{msg}\n\n"
                        f"reasoning: {(decision.get('reasoning') or '')[:400]}"
                    ),
                    priority="default",
                    tags="warning",
                )
            return record

    # ── DRY_RUN mode ─────────────────────────────────────────────────────
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
          f"(mode={MODE})")

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
