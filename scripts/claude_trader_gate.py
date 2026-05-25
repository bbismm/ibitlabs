#!/usr/bin/env python3
"""
claude_trader_gate.py — Phase B.1 cadence gate.

Decides whether the next claude-trader fire should spawn a Claude CLI
session, or skip and just increment the in-mode skip counter.

Print one line to stdout:
  FIRE:<reason>        — wrapper invokes Claude as normal
  SKIP:<reason>        — wrapper exits 0, increments skipped_fires_in_mode

Architectural separation (per design doc Section 9):
  - Invariant transition detection (position change / regime flip / range
    break / displacement) is procedural and lives HERE. Always overrides
    mode-based cadence — Claude can never accidentally suppress its own
    cognition during a real market event.
  - Semantic mode cadence (Compression → 1h heartbeat; Regime Uncertain →
    15min; Expansion / Inventory Discovery → 5min) reads `cognition_mode`
    from state.json.

Failure mode bias: ALL failures → FIRE. Safer to spawn Claude unnecessarily
than to silently skip during a real event.
"""

from __future__ import annotations
import datetime
import json
import os
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
STATE_FILE = HOME / "ibitlabs/state/claude_trader_state.json"
DECISIONS_FILE = HOME / "ibitlabs/logs/claude-trader/decisions.jsonl"
FRAMEWORK_FILE = HOME / "ibitlabs/logs/claude-trader/framework_log.jsonl"
LIVE_STATUS_URL = "https://www.ibitlabs.com/api/live-status"

# Mode → max-quiet-time before forcing a heartbeat fire.
# Conservative defaults. Claude can override per-fire by writing a different
# `cognition_mode_cadence_hint` in state.json.
MODE_HEARTBEAT_SECS = {
    "Expansion": 5 * 60,
    "Inventory Discovery": 5 * 60,
    "Regime Uncertain": 15 * 60,
    "Compression": 60 * 60,
}
DEFAULT_HEARTBEAT_SECS = 60 * 60  # unknown mode → conservative 1h

# Framework reflection clock — pure time-based (Phase B.1 founder Q3).
REFLECTION_HEARTBEAT_SECS = 4 * 3600


def parse_iso(s: str | None):
    if not s:
        return None
    try:
        # Normalize trailing 'Z' to '+00:00' for stdlib ISO parser.
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def last_record(path: Path):
    """Return the last JSON line of a jsonl file, or None."""
    if not path.exists():
        return None
    last = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                continue
    return last


def fetch_live_status(timeout: float = 5.0):
    try:
        req = urllib.request.Request(
            LIVE_STATUS_URL,
            headers={"User-Agent": "claude-trader-gate/0.1 (+ibitlabs.com)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None  # signal: fail open


def decide() -> str:
    # 1. Load state. If missing/corrupt → FIRE (safe fallback).
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return "FIRE:state-file-unreadable"

    # 2. Bootstrap check — if cognition_mode is null, the next fire writes it.
    cognition_mode = state.get("cognition_mode")
    if not cognition_mode:
        return "FIRE:cognition-mode-bootstrap"

    # 3. Fetch live-status. If unreachable → FIRE.
    live = fetch_live_status()
    if live is None:
        return "FIRE:live-status-fetch-failed"

    # 4. Invariant transition detection — bypass mode logic.
    if live.get("position") is not None:
        return "FIRE:position-open"

    live_regime = live.get("regime")
    state_regime = state.get("regime")
    if live_regime and state_regime and live_regime != state_regime:
        return f"FIRE:regime-flip-{state_regime}-to-{live_regime}"

    # Range break — only check if state has a maintained range.
    price = live.get("current_price")
    lo = state.get("range_low_usd")
    hi = state.get("range_high_usd")
    if all(isinstance(x, (int, float)) for x in (price, lo, hi)) and lo > 0 and hi > 0:
        if price < lo or price > hi:
            return f"FIRE:range-break-price={price}"

    # 5. Framework reflection clock — 4h time-based.
    last_refl = last_record(FRAMEWORK_FILE)
    last_refl_iso = (last_refl or {}).get("iso")
    last_refl_dt = parse_iso(last_refl_iso)
    if last_refl_dt is not None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        try:
            elapsed = (now_utc - last_refl_dt.astimezone(datetime.timezone.utc)).total_seconds()
        except Exception:
            elapsed = 0
        if elapsed > REFLECTION_HEARTBEAT_SECS:
            return f"FIRE:reflection-heartbeat-{int(elapsed)}s"

    # 6. Mode-based decision heartbeat.
    last_dec = last_record(DECISIONS_FILE)
    last_dec_iso = (last_dec or {}).get("fire_iso")
    last_dec_dt = parse_iso(last_dec_iso)

    heartbeat_secs = MODE_HEARTBEAT_SECS.get(cognition_mode, DEFAULT_HEARTBEAT_SECS)
    if last_dec_dt is None:
        return f"FIRE:no-prior-decision-in-mode-{cognition_mode}"

    try:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        elapsed_dec = (now_utc - last_dec_dt.astimezone(datetime.timezone.utc)).total_seconds()
    except Exception:
        return "FIRE:dt-arithmetic-failed"

    if elapsed_dec > heartbeat_secs:
        return f"FIRE:heartbeat-{cognition_mode}-{int(elapsed_dec)}s"

    # 7. Otherwise — SKIP.
    return f"SKIP:mode={cognition_mode}-elapsed={int(elapsed_dec)}s-threshold={heartbeat_secs}s"


def increment_skip_counter() -> None:
    """Bump skipped_fires_in_mode in state.json. Best-effort; failure is logged
    but doesn't change the SKIP outcome."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state["skipped_fires_in_mode"] = int(state.get("skipped_fires_in_mode") or 0) + 1
        state["last_gate_check_iso"] = (
            datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"  (skip-counter update failed: {e})", file=sys.stderr)


def main() -> int:
    verdict = decide()
    print(verdict)
    if verdict.startswith("SKIP:"):
        increment_skip_counter()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
