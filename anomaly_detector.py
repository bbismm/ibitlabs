"""
Anomaly Detector — state-layer watchdog for the SOL sniper.

Premise (from "The place AI-written code silently lies is not the logic — it's
the state layer"): code can keep running while the *facts it stores* drift
away from reality. Strategy intent says "trailing locks profits", but the trade
log fills with timeouts. Strategy intent says "long+short balanced", but every
trade for two days is short. Logs look healthy. Config looks correct. Only the
state layer betrays the lie.

This watchdog reads sol_sniper.db every 15 minutes, evaluates a fixed set of
invariants over the last 24-48h of trades, and pushes a notification when any
invariant fails. It does *not* try to fix anything — it just makes the state
layer audible.

Invariants checked:
  1. DB freshness          — at least one row written in the last 24h
  2. Sniper heartbeat      — sniper.log has been written to in last 30 min
  3. Open-position runaway — no closed position open longer than max_hold + 2h
  4. Exit-reason monoculture — last 12 closes can't all be one of {timeout, sl,
     breakeven}; that means trailing/TP never fires (state-layer drift)
  5. Tag drift             — `exit_reason='tp'` rows must have pnl > 0 and
                              `exit_reason='sl'` rows must have pnl < 0
  6. Direction skew        — last 24h of new positions can't be 100% one side
                              if at least 4 positions were opened
  7. Daily drawdown        — sum(pnl) over last 24h above a sane floor
  8. Strategy-version drift — recent rows must carry the version we expect

Usage:
  python3 anomaly_detector.py [--db sol_sniper.db] [--quiet]

Exit codes:
  0  all invariants passed
  1  one or more invariants failed (notification was pushed)
  2  detector itself errored (DB unreadable, etc.)
"""

import argparse
import logging
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger("anomaly_detector")

# ── Config ───────────────────────────────────────────────────────────────────
DEFAULT_DB = "/Users/bonnyagent/ibitlabs/sol_sniper.db"
# The sniper's Python logging goes to stderr; the LaunchAgent routes stderr to
# sniper_launchd_err.log. sniper.log is a legacy file that nothing currently
# writes to — checking only it produced a false positive on first run. Take the
# freshest mtime across both candidates and a couple of other live signals.
SNIPER_HEARTBEAT_PATHS = [
    "/Users/bonnyagent/ibitlabs/logs/sniper_launchd_err.log",
    "/Users/bonnyagent/ibitlabs/logs/sniper_launchd.log",
    "/Users/bonnyagent/ibitlabs/logs/sniper.log",
    "/Users/bonnyagent/ibitlabs/sol_sniper_state.json",
]
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "sol-sniper-bonny")
EXPECTED_VERSION = os.environ.get("SNIPER_EXPECTED_VERSION", "breakout_v3.4")
EXPECTED_GRID_VERSION = os.environ.get("GRID_EXPECTED_VERSION", "grid_v1")
DAILY_DRAWDOWN_FLOOR = float(os.environ.get("DAILY_DRAWDOWN_FLOOR_USD", "-150"))
MAX_HOLD_HOURS = float(os.environ.get("SNIPER_MAX_HOLD_HOURS", "8"))

# Strategy intent tags — used to split invariants per-strategy so the grid
# doesn't trip checks designed for the sniper (and vice versa). The grid keeps
# multiple positions open for legitimate reasons; the sniper does not. The grid
# in trending markets fills one side far more than the other; the sniper
# shouldn't. Etc.
SNIPER_INTENT = "momentum_breakout"
GRID_INTENT = "grid_mean_reversion"


def _is_grid(row: dict) -> bool:
    """True if the row was written by the grid (sol_micro_grid)."""
    intent = row.get("strategy_intent")
    if intent:
        return intent == GRID_INTENT
    # Backward compat for legacy rows written before strategy_intent existed:
    side = (row.get("side") or "").upper()
    return side.startswith("GRID_")


def _is_sniper(row: dict) -> bool:
    """True if the row was written by the sniper executor."""
    intent = row.get("strategy_intent")
    if intent:
        return intent == SNIPER_INTENT
    side = (row.get("side") or "").upper()
    # Legacy sniper rows have side='BUY' or 'SELL' (no GRID_ prefix)
    return side in ("BUY", "SELL")


# ── Notification ─────────────────────────────────────────────────────────────

def push(title: str, body: str):
    """ntfy.sh push + local log line. Best-effort, never raises."""
    try:
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        req = urllib.request.Request(
            url, data=body.encode("utf-8"), method="POST"
        )
        req.add_header("Title", title)
        req.add_header("Priority", "urgent")
        req.add_header("Tags", "warning,rotating_light")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning(f"[push] failed: {e}")
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open("/Users/bonnyagent/ibitlabs/logs/anomaly.log", "a") as f:
            f.write(f"[{ts}] [{title}] {body}\n")
    except Exception:
        pass


# ── DB helpers ───────────────────────────────────────────────────────────────

def open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def recent_closes(conn, hours: int) -> list:
    """Closes only — i.e. trade_log rows with non-null exit_reason or pnl != 0."""
    cutoff = time.time() - hours * 3600
    rows = conn.execute(
        """SELECT * FROM trade_log
           WHERE timestamp >= ? AND pnl IS NOT NULL AND pnl != 0
           ORDER BY timestamp DESC""",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def recent_opens(conn, hours: int) -> list:
    """Opens — pnl == 0 (or NULL) rows."""
    cutoff = time.time() - hours * 3600
    rows = conn.execute(
        """SELECT * FROM trade_log
           WHERE timestamp >= ? AND (pnl IS NULL OR pnl = 0)
           ORDER BY timestamp DESC""",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Invariants ───────────────────────────────────────────────────────────────
# Each returns (ok: bool, message: str). Message is only used on failure.

def check_db_freshness(conn) -> tuple:
    """Bot liveness check — verify the bot process is actively writing logs.
    MR strategy can hold a single position for 24h+ without any new trade_log
    rows, so checking DB freshness causes false positives. Instead, check that
    the bot's log files are being written to (same logic as check_heartbeat
    but with a tighter threshold)."""
    fresh_age_min = None
    for path in SNIPER_HEARTBEAT_PATHS:
        if not os.path.exists(path):
            continue
        age_min = (time.time() - os.path.getmtime(path)) / 60
        if fresh_age_min is None or age_min < fresh_age_min:
            fresh_age_min = age_min
    if fresh_age_min is None:
        return False, "no bot log files found — process likely not running"
    if fresh_age_min > 5:
        return False, f"bot logs not updated in {fresh_age_min:.1f} min — process may be dead"
    return True, ""


def check_heartbeat() -> tuple:
    """
    Heartbeat = freshest mtime across all candidate sniper signal files.
    Picking just one was the v1 bug — Python logging defaults to stderr, the
    plist routes stderr to sniper_launchd_err.log, and sniper.log is legacy.
    The state file also gets touched on every check_position tick.
    """
    fresh_age_min = None
    fresh_path = None
    for path in SNIPER_HEARTBEAT_PATHS:
        if not os.path.exists(path):
            continue
        age_min = (time.time() - os.path.getmtime(path)) / 60
        if fresh_age_min is None or age_min < fresh_age_min:
            fresh_age_min = age_min
            fresh_path = path
    if fresh_age_min is None:
        return False, f"no sniper heartbeat file exists in {SNIPER_HEARTBEAT_PATHS}"
    if fresh_age_min > 30:
        return False, (
            f"freshest sniper signal is {fresh_path} at {fresh_age_min:.1f} min old "
            f"(process likely dead)"
        )
    return True, ""


def check_open_runaway(conn) -> tuple:
    """
    Sniper executor stuck = the most recent *sniper* open is older than
    max_hold + 2h with no sniper close after it.

    The grid is excluded entirely. The grid keeps multiple filled levels open
    by design — they sit there until price reaches their TP, which can take
    many hours in a tight range. That is not a runaway; that is the strategy.
    Only the sniper has a "max hold" semantic worth alarming on.
    """
    rows = conn.execute(
        """SELECT timestamp, symbol, side, pnl, strategy_intent FROM trade_log
           ORDER BY timestamp DESC LIMIT 50"""
    ).fetchall()
    sniper_rows = [dict(r) for r in rows if _is_sniper(dict(r))]
    if not sniper_rows:
        return True, ""
    latest = sniper_rows[0]
    pnl = latest["pnl"]
    if pnl is not None and float(pnl) != 0:
        return True, ""  # latest sniper row is a close — nothing open
    age_h = (time.time() - float(latest["timestamp"])) / 3600
    if age_h > MAX_HOLD_HOURS + 2:
        return False, (
            f"latest sniper row is an open from {age_h:.1f}h ago "
            f"({latest['side']} {latest['symbol']}) with no close after it — "
            f"executor stuck or close-write dropped"
        )
    return True, ""


def check_exit_reason_monoculture(conn) -> tuple:
    """
    Sniper-only check. Looks at the last 12 *sniper* closes — if every one of
    them is in {timeout, sl, breakeven, force_close} then trailing/TP never
    fired and the trailing-stop logic is silently broken. Grid closes are
    excluded because they have their own exit vocabulary (grid_tp, grid_drift,
    etc.) and a healthy grid run is dominated by grid_tp, which would otherwise
    mask a broken sniper.
    """
    closes = recent_closes(conn, hours=72)
    sniper_closes = [c for c in closes if _is_sniper(c) and c.get("exit_reason")]
    sniper_closes = sniper_closes[:12]
    if len(sniper_closes) < 6:
        return True, ""  # not enough data yet
    reasons = [c["exit_reason"] for c in sniper_closes]
    bad_set = {"timeout", "sl", "breakeven", "force_close"}
    if all(r in bad_set for r in reasons):
        from collections import Counter
        breakdown = ", ".join(f"{k}={v}" for k, v in Counter(reasons).items())
        return False, (
            f"last {len(sniper_closes)} sniper closes never hit tp/trailing — "
            f"breakdown: {breakdown}. Trailing-stop logic may be broken."
        )
    return True, ""


def check_tag_drift(conn) -> tuple:
    """
    Each exit_reason has a definitional PnL sign. If the row violates it, the
    tag is lying.
      sniper:  tp > 0,  sl < 0
      grid:    grid_tp > 0  (grid takes profit at a fixed level — must win)
    Other tags (trailing, breakeven, timeout, grid_drift, grid_handoff,
    grid_deactivate) have no fixed sign and are excluded.
    """
    closes = recent_closes(conn, hours=72)
    bad = []
    for c in closes:
        reason = c.get("exit_reason")
        pnl = float(c.get("pnl") or 0)
        if reason == "tp" and pnl <= 0:
            bad.append(f"tp@{pnl:+.2f}")
        elif reason == "sl" and pnl >= 0:
            bad.append(f"sl@{pnl:+.2f}")
        elif reason == "grid_tp" and pnl <= 0:
            bad.append(f"grid_tp@{pnl:+.2f}")
    if bad:
        sample = ", ".join(bad[:5])
        return False, (
            f"{len(bad)} trades have exit_reason inconsistent with sign(pnl): {sample}"
        )
    return True, ""


def check_direction_skew(conn) -> tuple:
    """
    Sniper-only check. The sniper is supposed to take both longs and shorts;
    if 24h of sniper opens are all one side, the regime/trend gate is stuck.
    The grid is excluded — in a strong trend the grid will fill one side far
    more than the other, and that's the strategy working as intended.
    """
    opens = recent_opens(conn, hours=24)
    sniper_opens = [o for o in opens if _is_sniper(o)]
    dirs = []
    for o in sniper_opens:
        d = o.get("direction")
        if not d:
            side = (o.get("side") or "").upper()
            d = "long" if side == "BUY" else "short" if side == "SELL" else None
        if d:
            dirs.append(d)
    if len(dirs) < 4:
        return True, ""
    longs = sum(1 for d in dirs if d == "long")
    shorts = sum(1 for d in dirs if d == "short")
    if longs == 0 or shorts == 0:
        only = "long" if shorts == 0 else "short"
        return False, (
            f"last 24h opened {len(dirs)} sniper positions, all {only} — "
            f"direction filter likely broken (regime/trend gate stuck)"
        )
    return True, ""


def check_daily_drawdown(conn) -> tuple:
    closes = recent_closes(conn, hours=24)
    total = sum(float(c.get("pnl") or 0) for c in closes)
    if total < DAILY_DRAWDOWN_FLOOR:
        return False, (
            f"24h PnL ${total:+.2f} below floor ${DAILY_DRAWDOWN_FLOOR:+.2f} "
            f"({len(closes)} closes)"
        )
    return True, ""


def check_version_drift(conn) -> tuple:
    """
    Each strategy has its own expected version. A sniper close tagged with
    something other than EXPECTED_VERSION (or a grid close tagged with
    something other than EXPECTED_GRID_VERSION) means a stale process is still
    writing into the DB — that's exactly the kind of state-layer lie this
    detector exists to catch.
    """
    closes = recent_closes(conn, hours=24)
    closes = [c for c in closes if c.get("strategy_version")]
    if not closes:
        # Acceptable for the first 24h after schema migration
        return True, ""
    bad = []
    for c in closes:
        v = c["strategy_version"]
        if _is_grid(c):
            if v != EXPECTED_GRID_VERSION:
                bad.append(f"grid:{v}")
        elif _is_sniper(c):
            if v != EXPECTED_VERSION:
                bad.append(f"sniper:{v}")
        # Unknown intent: silently skip
    if bad:
        return False, (
            f"{len(bad)}/{len(closes)} closes carry unexpected strategy_version "
            f"(sniper expects {EXPECTED_VERSION}, grid expects "
            f"{EXPECTED_GRID_VERSION}, saw {set(bad)})"
        )
    return True, ""


# ── Driver ───────────────────────────────────────────────────────────────────

INVARIANTS = [
    ("db_freshness", check_db_freshness, True),
    ("heartbeat", check_heartbeat, False),  # doesn't take conn
    ("open_runaway", check_open_runaway, True),
    ("exit_reason_monoculture", check_exit_reason_monoculture, True),
    ("tag_drift", check_tag_drift, True),
    ("direction_skew", check_direction_skew, True),
    ("daily_drawdown", check_daily_drawdown, True),
    ("version_drift", check_version_drift, True),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--quiet", action="store_true",
                        help="suppress push on success (still pushes on failure)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not Path(args.db).exists():
        push("ANOMALY DETECTOR ERROR", f"DB not found at {args.db}")
        return 2

    try:
        conn = open_db(args.db)
    except Exception as e:
        push("ANOMALY DETECTOR ERROR", f"could not open DB: {e}")
        return 2

    failures = []
    try:
        for name, fn, needs_conn in INVARIANTS:
            try:
                ok, msg = fn(conn) if needs_conn else fn()
            except Exception as e:
                ok, msg = False, f"check raised {type(e).__name__}: {e}"
            status = "OK" if ok else "FAIL"
            logger.info(f"[{status}] {name} {('— ' + msg) if msg else ''}")
            if not ok:
                failures.append((name, msg))
    finally:
        conn.close()

    if failures:
        title = f"SNIPER ANOMALY ({len(failures)})"
        body = "\n".join(f"• {n}: {m}" for n, m in failures)
        push(title, body)
        return 1

    if not args.quiet:
        logger.info("[ALL OK] every invariant passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
