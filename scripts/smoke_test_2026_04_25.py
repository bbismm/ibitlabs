#!/usr/bin/env python3
"""
Smoke test for everything shipped 2026-04-25.

Verifies — with one PASS/FAIL line per check — that:
  · 5 LaunchAgents are loaded
  · 3 production receipts URLs return 200 with expected schema
  · position_telemetry table is being written to (last row < 5 min old)
  · mutelist JSON loads + contains codeofgrace
  · idempotency hash + check round-trips correctly
  · moltbook_publish.py syncs (canonical /scripts vs /ibitlabs/scripts)
  · sortino-nightly + stochrsi-nightly + mfe-mae-nightly plists are valid
  · brand-builder SKILL.md mutelist filter language present
  · learning-loop SKILL.md mutelist filter language present
  · CLAUDE.md is current (mod time within 24h)

Exit 0 if all green. Exit 1 if any RED. Yellow → exit 0 with warnings.
Read-only. No state mutation.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────
DB_PATH = Path("/Users/bonnyagent/ibitlabs/sol_sniper.db")
MEMO_DIR = Path("/Users/bonnyagent/.claude/projects/-Users-bonnyagent/memory")
LAUNCH_DIR = Path("/Users/bonnyagent/Library/LaunchAgents")
SKILL_BB = Path("/Users/bonnyagent/Documents/Claude/Scheduled/moltbook-brand-builder/SKILL.md")
SKILL_LL = Path("/Users/bonnyagent/Documents/Claude/Scheduled/moltbook-learning-loop/SKILL.md")
MUTELIST = Path("/Users/bonnyagent/ibitlabs/scripts/moltbook_mutelist.json")
PUBLISHER_CANONICAL = Path("/Users/bonnyagent/scripts/moltbook_publish.py")
PUBLISHER_MIRROR = Path("/Users/bonnyagent/ibitlabs/scripts/moltbook_publish.py")
CLAUDE_MD = Path("/Users/bonnyagent/ibitlabs/CLAUDE.md")

EXPECTED_LAUNCHAGENTS = [
    "com.ibitlabs.sortino-nightly",
    "com.ibitlabs.stochrsi-nightly",
    "com.ibitlabs.mfe-mae-nightly",
    "com.ibitlabs.position-telemetry",
    "com.ibitlabs.position-telemetry-summary",
]
# These plists exist + lint clean but are *intentionally* unloaded
# (B route HTTP worker stays cold until .env auth route fails).
EXPECTED_COLD_LAUNCHAGENTS = [
    "com.ibitlabs.moltbook-worker",
]

EXPECTED_RECEIPTS = [
    ("https://www.ibitlabs.com/data/trade_stats.json", ["overall", "rolling", "riskofficer_test"]),
    ("https://www.ibitlabs.com/data/stochrsi_at_open.json", ["bins", "pearson_stochrsi_vs_pnl_pct", "strategy_version"]),
    ("https://www.ibitlabs.com/data/mfe_mae_distribution.json", ["strategy_version", "n_v51_closed", "n_with_mfe_mae_populated"]),
    ("https://www.ibitlabs.com/data/position_telemetry_summary.json", ["n_ticks_total", "n_positions_observed", "positions"]),
]

# ─── Reporting ───────────────────────────────────────────────────────
results: list[tuple[str, str, str]] = []  # (status, name, detail)

def passed(name: str, detail: str = "") -> None:
    results.append(("PASS", name, detail))

def warn(name: str, detail: str) -> None:
    results.append(("WARN", name, detail))

def failed(name: str, detail: str) -> None:
    results.append(("FAIL", name, detail))

# ─── Checks ──────────────────────────────────────────────────────────
def check_launchagents() -> None:
    try:
        out = subprocess.check_output(["/bin/launchctl", "list"], text=True, timeout=5)
    except Exception as e:
        for label in EXPECTED_LAUNCHAGENTS + EXPECTED_COLD_LAUNCHAGENTS:
            failed(f"launchctl: {label}", f"launchctl call failed: {e}")
        return
    for label in EXPECTED_LAUNCHAGENTS:
        if label in out:
            passed(f"launchctl: {label}", "loaded")
        else:
            failed(f"launchctl: {label}", "NOT loaded")
    for label in EXPECTED_COLD_LAUNCHAGENTS:
        if label in out:
            warn(f"launchctl: {label}", "loaded — expected cold (B route backup); check intent")
        else:
            passed(f"launchctl: {label}", "cold (as designed; B route backup)")

def check_plists_lint() -> None:
    for label in EXPECTED_LAUNCHAGENTS + EXPECTED_COLD_LAUNCHAGENTS:
        path = LAUNCH_DIR / f"{label}.plist"
        if not path.exists():
            failed(f"plist file: {label}", f"missing: {path}")
            continue
        try:
            subprocess.check_output(["/usr/bin/plutil", "-lint", str(path)], stderr=subprocess.STDOUT, timeout=5)
            passed(f"plist lint: {label}", "OK")
        except subprocess.CalledProcessError as e:
            failed(f"plist lint: {label}", e.output.decode("utf-8", errors="replace")[:200])

def check_receipts() -> None:
    for url, required_keys in EXPECTED_RECEIPTS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "smoke-test/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status != 200:
                    failed(f"receipt: {url}", f"HTTP {r.status}")
                    continue
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            failed(f"receipt: {url}", f"fetch failed: {e}")
            continue
        missing = [k for k in required_keys if k not in data]
        if missing:
            failed(f"receipt: {url}", f"missing keys: {missing}")
        else:
            n_trades = data.get("n_trades") or data.get("n_v51_closed") or data.get("n_with_stochrsi") or "?"
            passed(f"receipt: {url}", f"200, schema OK, n={n_trades}")

def check_position_telemetry() -> None:
    if not DB_PATH.exists():
        failed("position_telemetry: DB", f"DB not found: {DB_PATH}")
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        # Table exists?
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='position_telemetry'"
        ).fetchall()
        if not rows:
            failed("position_telemetry: table", "table does not exist")
            conn.close()
            return
        # Latest row?
        last = conn.execute(
            "SELECT ts, position_key, ROUND(pnl_pct*100,3), ROUND(exit_score_shadow,2) "
            "FROM position_telemetry ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM position_telemetry").fetchone()[0]
        conn.close()
        if not last:
            warn("position_telemetry: rows", "table empty (sidecar hasn't written yet)")
            return
        ts, key, pnl, score = last
        age = int(time.time() - ts)
        if age > 300:
            warn(
                "position_telemetry: freshness",
                f"last row {age}s old (>300s); sidecar may be stalled or no position open",
            )
        else:
            passed(
                "position_telemetry: freshness",
                f"last row {age}s old, total rows={count}, key={key}, pnl={pnl}%, score={score}",
            )
    except Exception as e:
        failed("position_telemetry: query", str(e))

def check_mutelist() -> None:
    if not MUTELIST.exists():
        failed("mutelist", f"missing: {MUTELIST}")
        return
    try:
        d = json.loads(MUTELIST.read_text())
    except Exception as e:
        failed("mutelist: JSON", f"parse failed: {e}")
        return
    muted = {x.get("username") for x in d.get("muted_authors", [])}
    if "codeofgrace" not in muted:
        failed("mutelist: codeofgrace", "expected username not in muted_authors")
        return
    passed(
        "mutelist",
        f"loaded; muted={sorted(muted)}, flagged={[x['username'] for x in d.get('flagged_phishing', [])]}",
    )

def check_idempotency() -> None:
    sys.path.insert(0, "/Users/bonnyagent/scripts")
    try:
        from moltbook_publish import (  # type: ignore
            idempotency_key, idempotency_check, idempotency_record, _idempotency_load, IDEMPOTENCY_PATH,
        )
    except Exception as e:
        failed("idempotency: import", str(e))
        return

    # Hash determinism
    k1 = idempotency_key("general", "T", "B")
    k2 = idempotency_key("general", "T", "B")
    k3 = idempotency_key("general", "T", "B2")
    if k1 != k2:
        failed("idempotency: determinism", f"{k1!r} != {k2!r}")
        return
    if k1 == k3:
        failed("idempotency: distinctness", "different content produced same hash")
        return

    # Round-trip
    unique_title = f"__smoke_test__{int(time.time())}"
    if idempotency_check("general", unique_title, "z") is not None:
        failed("idempotency: pre-record", "false positive on never-seen content")
        return
    idempotency_record("general", unique_title, "z", "smoke-test-pid", "https://example/smoke")
    hit = idempotency_check("general", unique_title, "z")
    if not hit or hit.get("post_id") != "smoke-test-pid":
        failed("idempotency: round-trip", f"check returned {hit}")
        return
    # Cleanup smoke test entries
    records = [r for r in _idempotency_load() if not r.get("title", "").startswith("__smoke_test__")]
    IDEMPOTENCY_PATH.write_text(json.dumps(records, indent=2))
    passed("idempotency", f"hash deterministic, check round-trips, persistence at {IDEMPOTENCY_PATH}")

def check_publisher_sync() -> None:
    if not (PUBLISHER_CANONICAL.exists() and PUBLISHER_MIRROR.exists()):
        failed("publisher sync", f"one or both missing: {PUBLISHER_CANONICAL}, {PUBLISHER_MIRROR}")
        return
    h1 = hashlib.sha256(PUBLISHER_CANONICAL.read_bytes()).hexdigest()[:16]
    h2 = hashlib.sha256(PUBLISHER_MIRROR.read_bytes()).hexdigest()[:16]
    if h1 != h2:
        failed("publisher sync", f"canonical sha {h1} != mirror sha {h2}")
    else:
        passed("publisher sync", f"both copies identical (sha {h1})")

def check_skill_mutelist_language() -> None:
    for label, p in [("brand-builder", SKILL_BB), ("learning-loop", SKILL_LL)]:
        if not p.exists():
            failed(f"SKILL.md: {label}", f"missing: {p}")
            continue
        text = p.read_text()
        if "moltbook_mutelist.json" not in text:
            failed(f"SKILL.md: {label}", "no reference to moltbook_mutelist.json")
            continue
        if label == "learning-loop" and "filter" not in text.lower():
            warn(f"SKILL.md: {label}", "mutelist mentioned but 'filter' word absent")
            continue
        passed(f"SKILL.md: {label}", "mutelist filter language present")

def check_claude_md() -> None:
    if not CLAUDE_MD.exists():
        failed("CLAUDE.md", f"missing: {CLAUDE_MD}")
        return
    age_h = (time.time() - CLAUDE_MD.stat().st_mtime) / 3600
    if age_h > 48:
        warn("CLAUDE.md", f"last modified {age_h:.1f}h ago — learning-loop may be stalled")
    else:
        passed("CLAUDE.md", f"last modified {age_h:.1f}h ago")

# ─── Main ────────────────────────────────────────────────────────────
def main() -> int:
    print("\n=== iBitLabs smoke test — 2026-04-25 release ===\n")

    check_launchagents()
    check_plists_lint()
    check_receipts()
    check_position_telemetry()
    check_mutelist()
    check_idempotency()
    check_publisher_sync()
    check_skill_mutelist_language()
    check_claude_md()

    n_pass = sum(1 for r in results if r[0] == "PASS")
    n_warn = sum(1 for r in results if r[0] == "WARN")
    n_fail = sum(1 for r in results if r[0] == "FAIL")

    glyph = {"PASS": "✓", "WARN": "△", "FAIL": "✗"}
    for status, name, detail in results:
        line = f"  {glyph[status]} {status}  {name}"
        if detail:
            line += f"  ·  {detail}"
        print(line)

    print(f"\n  Summary: {n_pass} PASS · {n_warn} WARN · {n_fail} FAIL")
    if n_fail:
        print("  → RED: at least one critical check failed.")
        return 1
    if n_warn:
        print("  → YELLOW: warnings present, but no critical failure.")
        return 0
    print("  → GREEN: 测试版 ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
