#!/usr/bin/env python3
"""
pixel_office_bridge — feed iBitLabs receipt chains and launchd logs into the
pixel-agents (pablodelucca/pixel-agents) VS Code extension.

We write Claude Code-format JSONL files into a fake project directory; the
extension's "external scanner" picks them up and spawns one animated character
per agent. Each new event in a source chain/log becomes an `assistant` record
with a `tool_use` block; the character animates (typing for Bash/Task/Edit,
reading for Read) for a few seconds before settling back to idle.

Phase A.0 agent inventory (all confidential ones — wallet_sniper, polymarket
— deliberately excluded):

  sniper-live      ← ~/ibitlabs/audit_export/sniper-v5.1.realtime.receipt.jsonl
  sniper-shadow    ← ~/ibitlabs/audit_export/sniper-v5.1-shadow.realtime.receipt.jsonl
  sniper-eth       ← ~/ibitlabs/logs/sniper_eth_paper_launchd.log
  rule-engine      ← ~/ibitlabs/audit_export/rule-engine.realtime.receipt.jsonl  (supervisor #2)
  ghost-watchdog   ← ~/ibitlabs/logs/ghost_watchdog.log                          (supervisor #1)

Open VS Code at  ~/ibitlabs/pixel-office  to see the office.

State persisted at  ~/ibitlabs/pixel-office/.bridge-state.json  so character
UUIDs (= jsonl filenames) stay stable across restarts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
WORKSPACE_DIR = HOME / "ibitlabs" / "pixel-office"
# Per-agent dir tree under WORKSPACE_DIR/agents/<agent_name>/transcript.jsonl
# pixel-agents derives the label from the basename of dirname(transcript_path) —
# putting each agent in its own dir gives each a distinct label without the
# "split on dashes, take last segment" rule mangling readable names.
AGENTS_DIR = WORKSPACE_DIR / "agents"
STATE_FILE = WORKSPACE_DIR / ".bridge-state.json"
PIXEL_SERVER_JSON = HOME / ".pixel-agents" / "server.json"


def agent_dir(agent_name: str) -> Path:
    # Underscore the name so pixel-agents' folderNameFromProjectDir (split-on-dash)
    # keeps the whole thing as the last token.
    return AGENTS_DIR / agent_name.replace("-", "_")


def agent_jsonl_path(agent_name: str, uuid_str: str) -> Path:
    return agent_dir(agent_name) / f"{uuid_str}.jsonl"

# How long a tool_use stays "active" (visible animation) before close.
TOOL_BURST_DURATION_SEC = 6
# Idle heartbeat keeps the character non-stale.
# pixel-agents EXTERNAL_STALE_CHECK_INTERVAL_MS defaults near 30s; stay under it.
HEARTBEAT_INTERVAL_SEC = 22
TICK_INTERVAL_SEC = 1.5

# kind_map entries are (tool_name, description, severity).
# severity ∈ {"info", "warn", "error"} — drives the colored dot + incident badge
# in the public-facing webapp. Bridge always emits info-level when unspecified.
AGENTS = [
    {
        "name": "sniper-live",
        "public_id": 101,
        "source_type": "receipt_chain",
        "source_path": HOME / "ibitlabs/audit_export/sniper-v5.1.realtime.receipt.jsonl",
        "kind_map": {
            "claim":     ("Bash", "live: trade decision",  "info"),
            "verified":  ("Read", "live: fill confirmed",  "info"),
            "anchor":    ("Read", "live: chain anchor",    "info"),
            "heartbeat": ("Read", "live: heartbeat",       "info"),
            "error":     ("Bash", "live: error",           "error"),
        },
        "default_tool": "Read",
        "default_severity": "info",
    },
    {
        "name": "sniper-shadow",
        "public_id": 102,
        "source_type": "receipt_chain",
        "source_path": HOME / "ibitlabs/audit_export/sniper-v5.1-shadow.realtime.receipt.jsonl",
        "kind_map": {
            "claim":     ("Bash", "shadow: paper trade",  "info"),
            "verified":  ("Read", "shadow: paper fill",   "info"),
            "anchor":    ("Read", "shadow: anchor",       "info"),
            "heartbeat": ("Read", "shadow: heartbeat",    "info"),
        },
        "default_tool": "Read",
        "default_severity": "info",
    },
    {
        # ETH paper bot writes SQLite + a state JSON; no JSONL chain.
        # We just watch the state file's mtime — every bot loop rewrites it.
        "name": "sniper-eth",
        "public_id": 103,
        "source_type": "file_mtime",
        "source_path": HOME / "ibitlabs/sol_sniper_state_eth_paper.json",
        "kind_map": {
            "tick": ("Read", "eth: state updated", "info"),
        },
        "default_tool": "Read",
        "default_severity": "info",
    },
    {
        # Task tool spawns sub-agents in pixel-agents — never use it here.
        # Bash/Edit/Write all give typing animation without sub-agent FSM.
        "name": "rule-engine",
        "public_id": 104,
        "source_type": "receipt_chain",
        "source_path": HOME / "ibitlabs/audit_export/rule-engine.realtime.receipt.jsonl",
        "kind_map": {
            "heartbeat":  ("Read", "supervisor: rules ok",    "info"),
            "rule_fired": ("Bash", "supervisor: RULE FIRED",  "warn"),
            "alert":      ("Bash", "supervisor: ALERT",       "warn"),
            "anchor":     ("Read", "supervisor: anchor",      "info"),
        },
        "default_tool": "Read",
        "default_severity": "info",
    },
    {
        "name": "ghost-watchdog",
        "public_id": 105,
        "source_type": "log_tail",
        "source_path": HOME / "ibitlabs/logs/ghost_watchdog.log",
        "kind_map": {
            "ok":      ("Read", "watchdog: state agrees", "info"),
            "alert":   ("Bash", "watchdog: GHOST",        "error"),
            "boot":    ("Bash", "watchdog: BOOTOUT",      "error"),
            "default": ("Read", "watchdog: tick",         "info"),
        },
        "default_tool": "Read",
        "default_severity": "info",
    },
    {
        # H4 sideways-only paper bot (added 2026-05-14, auto-retire 2026-06-14).
        # Plist `com.ibitlabs.sniper-sideways-paper` writes state_sideways_paper.json
        # on each bot loop — same file_mtime pattern as sniper-eth. Plist sets
        # SNIPER_RECEIPT=0, so there's no receipt chain to follow.
        # Leaderboard pulls trade stats from sol_sniper_sideways_paper.db (see
        # STRATEGY_DB_PATHS below).
        "name": "sniper-sideways-paper",
        "public_id": 106,
        "source_type": "file_mtime",
        "source_path": HOME / "ibitlabs/sol_sniper_state_sideways_paper.json",
        "kind_map": {
            "tick": ("Read", "sideways: state updated (H4 paper)", "info"),
        },
        "default_tool": "Read",
        "default_severity": "info",
    },
]


# ── PUBLIC MIRROR (B.1) ──────────────────────────────────────────────────
# Hardcoded whitelist — kept here in code, NOT loaded from config — so a
# stray AGENTS-list edit can never leak a confidential agent (wallet_sniper,
# polymarket_sniper) to ibitlabs.com/office. If you need to add a public
# agent, edit BOTH this set AND the AGENTS list above; one without the
# other does nothing.
PUBLIC_WHITELIST: frozenset[str] = frozenset(
    {
        "sniper-live",
        "sniper-shadow",
        "sniper-eth",
        "sniper-sideways-paper",
        "rule-engine",
        "ghost-watchdog",
    }
)

# Single canonical output, inside receipt-viewer's static-served dir so the
# existing `python3 -m http.server` on port 8090 exposes it without extra
# code. TCC-safe (under ~/ibitlabs/, not ~/Documents/). The same file is
# read by the Vite middleware (dev) and the production Pages Function (via
# Cloudflared path-match on trade.bibsus.com).
PUBLIC_EVENTS_PATH = HOME / "ibitlabs/receipt-viewer/data/office-events.json"
MAX_PUBLIC_EVENTS = 50

# In-memory ring of recent (whitelisted) events for the public mirror.
_public_events: list[dict] = []
_public_event_seq = 0

# ── Strategy leaderboard (C.1) ──────────────────────────────────────────
# Maps each trading-strategy public_id → SQLite path. Stats are recomputed
# every STATS_REFRESH_TICKS bridge ticks (DB I/O isn't free). Supervisors
# (rule_engine / ghost_watchdog) intentionally have no entry — they don't
# trade and don't show on the leaderboard.
STRATEGY_DB_PATHS: dict[int, Path] = {
    101: HOME / "ibitlabs/sol_sniper.db",                    # sniper-live
    102: HOME / "ibitlabs/sol_sniper_shadow.db",             # sniper-shadow
    103: HOME / "ibitlabs/sol_sniper_eth_paper.db",          # sniper-eth
    106: HOME / "ibitlabs/sol_sniper_sideways_paper.db",     # sniper-sideways-paper (H4)
}
# Without this filter, leaderboard SUM(pnl) mashes every strategy_version ever
# written to a db (breakout_v3.4 + grid_v1 + hybrid_v5.0 + hybrid_v5.1, etc).
# Live trader showed -$36/62 trades when v5.1 honest = +$0.60/18. See
# feedback_total_trades_not_v51_baseline.md. None → no filter (debug only).
STRATEGY_VERSION_FILTER: dict[int, str | None] = {
    101: "hybrid_v5.1",
    102: "hybrid_v5.1",
    103: "hybrid_v5.1",
    106: "hybrid_v5.1",
}
STATS_REFRESH_TICKS = 8  # bridge ticks at 1.5s → recompute stats every ~12s
_stats_cache: dict = {}
_stats_tick_counter = 0


# ── Achievements catalog (C.2 + C.4 daily) ──────────────────────────────
# Each entry: (id, label, icon, predicate(stats) -> bool, reset).
# `reset: "never"` = cumulative; once earned, persisted forever.
# `reset: "daily"` = resets at UTC midnight — Bridge clears stale entries
#   whose unlock_ts is from a previous UTC day, then re-checks against
#   current stats (today_pnl / today_trades), giving every UTC day a fresh
#   shot at the daily trophies. Persists same as cumulative.
ACHIEVEMENTS: list[dict] = [
    # ── Cumulative ─────────────────────────────────────────────────────
    {"id": "first_trade",      "label": "First trade",         "icon": "🚀", "reset": "never", "check": lambda s: s.get("total_trades", 0) >= 1},
    {"id": "ten_trades",       "label": "10 trades",           "icon": "🔟", "reset": "never", "check": lambda s: s.get("total_trades", 0) >= 10},
    {"id": "fifty_trades",     "label": "50 trades",           "icon": "📈", "reset": "never", "check": lambda s: s.get("total_trades", 0) >= 50},
    {"id": "hundred_trades",   "label": "100 trades",          "icon": "💯", "reset": "never", "check": lambda s: s.get("total_trades", 0) >= 100},
    {"id": "in_the_green",     "label": "In the green",        "icon": "💰", "reset": "never", "check": lambda s: s.get("total_pnl", 0) > 0 and s.get("total_trades", 0) >= 1},
    {"id": "wr_60",            "label": "60% win rate",        "icon": "🎯", "reset": "never", "check": lambda s: s.get("win_rate", 0) >= 0.6 and s.get("total_trades", 0) >= 20},
    {"id": "wr_80",            "label": "80% win rate",        "icon": "🏆", "reset": "never", "check": lambda s: s.get("win_rate", 0) >= 0.8 and s.get("total_trades", 0) >= 20},
    {"id": "comeback",         "label": "Comeback (PnL > $100)", "icon": "⚡", "reset": "never", "check": lambda s: s.get("total_pnl", 0) >= 100 and s.get("total_trades", 0) >= 10},
    # ── Daily (reset at UTC midnight) ───────────────────────────────────
    {"id": "today_active",     "label": "Active day (3+ trades)", "icon": "🔥", "reset": "daily", "check": lambda s: s.get("today_trades", 0) >= 3},
    {"id": "today_in_green",   "label": "Green day",              "icon": "🌱", "reset": "daily", "check": lambda s: s.get("today_pnl", 0) > 0 and s.get("today_trades", 0) >= 1},
    {"id": "today_big_green",  "label": "Big green day ($20+)",   "icon": "🌴", "reset": "daily", "check": lambda s: s.get("today_pnl", 0) >= 20},
    {"id": "today_huge_green", "label": "Huge green day ($100+)", "icon": "🎰", "reset": "daily", "check": lambda s: s.get("today_pnl", 0) >= 100},
]


def _utc_today_start_ms() -> int:
    """Unix ms timestamp of UTC midnight today."""
    return int(
        datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    )


def reset_stale_daily_achievements() -> bool:
    """Drop daily-resetting trophies whose unlock_ts is before today's UTC
    midnight. Called at startup + before each check pass. Returns True if
    anything was reset (caller can decide whether to persist)."""
    today_start = _utc_today_start_ms()
    daily_ids = {a["id"] for a in ACHIEVEMENTS if a.get("reset") == "daily"}
    changed = False
    for agent_id, m in _achievements_unlocked.items():
        for ach_id in list(m.keys()):
            if ach_id in daily_ids and m[ach_id] < today_start:
                del m[ach_id]
                changed = True
    return changed

# {agent_id_str: {ach_id: unlock_ts_ms}} — once unlocked, never removed even
# if the underlying metric regresses. Persisted to disk so a bridge restart
# (or a stat drop) doesn't lose hard-earned trophies. This is the load-bearing
# C.2.1 fix — previously a set re-derived from current stats.
_achievements_unlocked: dict[str, dict[str, int]] = {}
ACHIEVEMENTS_STATE_PATH = HOME / "ibitlabs/receipt-viewer/data/achievements_state.json"


def load_achievements_state() -> None:
    global _achievements_unlocked
    if not ACHIEVEMENTS_STATE_PATH.exists():
        return
    try:
        raw = json.loads(ACHIEVEMENTS_STATE_PATH.read_text())
        agents = raw.get("agents", {}) if isinstance(raw, dict) else {}
        _achievements_unlocked = {
            str(aid): {str(k): int(v) for k, v in m.items()}
            for aid, m in agents.items()
            if isinstance(m, dict)
        }
        # Drop stale daily entries from previous UTC day(s) so they re-fire fresh.
        if reset_stale_daily_achievements():
            save_achievements_state()
        total = sum(len(m) for m in _achievements_unlocked.values())
        print(
            f"[bridge] loaded {total} unlocked achievements across "
            f"{len(_achievements_unlocked)} agents (post-daily-reset)",
            file=sys.stderr,
        )
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"[bridge] achievements_state load failed: {e}", file=sys.stderr)


def save_achievements_state() -> None:
    try:
        ACHIEVEMENTS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = ACHIEVEMENTS_STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"agents": _achievements_unlocked}, indent=2))
        tmp.replace(ACHIEVEMENTS_STATE_PATH)
    except OSError as e:
        print(f"[bridge] achievements_state save failed: {e}", file=sys.stderr)


def check_achievements(stats_by_agent: dict) -> list[tuple[str, str]]:
    """Walk each agent's stats against the catalog. Returns a list of
    (agent_id, achievement_id) tuples for NEWLY-unlocked achievements in
    this pass. Cumulative entries are adds-only; daily entries get cleared
    each UTC midnight and can re-unlock on the new day."""
    newly: list[tuple[str, str]] = []
    now_ms = int(time.time() * 1000)
    # Roll over daily entries if we've crossed a UTC midnight.
    daily_reset = reset_stale_daily_achievements()
    for agent_id, stats in stats_by_agent.items():
        prev = _achievements_unlocked.setdefault(agent_id, {})
        for a in ACHIEVEMENTS:
            if a["id"] in prev:
                continue
            try:
                if a["check"](stats):
                    prev[a["id"]] = now_ms
                    newly.append((agent_id, a["id"]))
            except Exception:
                continue
    if newly or daily_reset:
        save_achievements_state()
    return newly


# Static, serializable view of the catalog — sent to the webapp so it can
# render icons + labels + distinguish daily vs cumulative without duplicating
# the predicate logic.
ACHIEVEMENTS_CATALOG = [
    {"id": a["id"], "label": a["label"], "icon": a["icon"], "reset": a.get("reset", "never")}
    for a in ACHIEVEMENTS
]


def compute_strategy_stats() -> dict:
    """Read trade_log out of each strategy's SQLite and aggregate.
    Returns: {agent_id_str: {total_trades, total_pnl, today_trades,
              today_pnl, win_count, loss_count, win_rate, last_pnl,
              last_trade_ts}}.
    Closed trades only (exit_price IS NOT NULL). Today = UTC midnight."""
    utc_midnight = int(
        datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    )
    out: dict = {}
    for agent_id, db_path in STRATEGY_DB_PATHS.items():
        if not db_path.exists():
            continue
        strat = STRATEGY_VERSION_FILTER.get(agent_id)
        strat_clause = " AND strategy_version = ?" if strat else ""
        strat_args: tuple = (strat,) if strat else ()
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT COUNT(*),
                       COALESCE(SUM(pnl), 0),
                       COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END), 0)
                FROM trade_log
                WHERE exit_price IS NOT NULL{strat_clause}
                """,
                strat_args,
            )
            total_n, total_pnl, win_n, loss_n = cur.fetchone()
            cur.execute(
                f"""
                SELECT COUNT(*),
                       COALESCE(SUM(pnl), 0)
                FROM trade_log
                WHERE exit_price IS NOT NULL
                  AND timestamp >= ?{strat_clause}
                """,
                (utc_midnight, *strat_args),
            )
            today_n, today_pnl = cur.fetchone()
            cur.execute(
                f"""
                SELECT pnl, timestamp
                FROM trade_log
                WHERE exit_price IS NOT NULL{strat_clause}
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                strat_args,
            )
            last_row = cur.fetchone()
            conn.close()
        except (sqlite3.Error, OSError) as e:
            print(f"[bridge] stats query failed for {db_path.name}: {e}", file=sys.stderr)
            continue

        win_rate = (win_n / total_n) if total_n else 0.0
        out[str(agent_id)] = {
            "total_trades": total_n,
            "total_pnl": round(total_pnl, 4),
            "today_trades": today_n,
            "today_pnl": round(today_pnl, 4),
            "win_count": win_n,
            "loss_count": loss_n,
            "win_rate": round(win_rate, 4),
            "last_pnl": round(last_row[0], 4) if last_row else None,
            "last_trade_ts": int(last_row[1] * 1000) if last_row else None,
        }
    return out


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Public mirror writers ────────────────────────────────────────────────

_agent_by_name: dict[str, dict] = {a["name"]: a for a in AGENTS}


def record_public_event(
    agent_name: str,
    kind: str,
    tool_id: str | None,
    tool_name: str | None,
    status: str | None,
    severity: str | None,
    payload: dict | None = None,
    source_kind: str | None = None,
    ts_ms: int | None = None,
) -> None:
    """Append an event to the in-memory ring (only if agent is whitelisted).
    Confidentiality enforcement: agents not in PUBLIC_WHITELIST never reach
    this list, so the file the webapp consumes can never expose them.

    `payload` carries the original receipt-chain `data` block (or log-line
    metadata) so the LiveEventTicker on /office can render structured content
    like "LONG SOL @ 95.79" instead of just the description string.
    """
    if agent_name not in PUBLIC_WHITELIST:
        return
    agent = _agent_by_name.get(agent_name)
    if agent is None or "public_id" not in agent:
        return

    global _public_event_seq
    _public_event_seq += 1
    ev: dict = {
        "cursor": _public_event_seq,
        "agentId": agent["public_id"],
        "kind": kind,
    }
    if ts_ms is not None:
        ev["ts"] = ts_ms
    else:
        ev["ts"] = int(time.time() * 1000)
    if tool_id is not None:
        ev["toolId"] = tool_id
    if tool_name is not None:
        ev["toolName"] = tool_name
    if status is not None:
        ev["status"] = status
    if severity is not None:
        ev["severity"] = severity
    if source_kind is not None:
        ev["sourceKind"] = source_kind  # original receipt kind (claim/verified/anchor/...)
    if payload:
        ev["payload"] = payload

    _public_events.append(ev)
    if len(_public_events) > MAX_PUBLIC_EVENTS:
        del _public_events[: len(_public_events) - MAX_PUBLIC_EVENTS]


def write_public_mirror() -> None:
    """Serialize the current view of the office to events.json + dev mirror.
    Always overwrites both files atomically (.tmp + rename)."""
    global _stats_cache, _stats_tick_counter
    _stats_tick_counter += 1
    if _stats_tick_counter >= STATS_REFRESH_TICKS or not _stats_cache:
        _stats_cache = compute_strategy_stats()
        _stats_tick_counter = 0

        # Achievements pass — derives unlocked set from the fresh stats and
        # emits a ticker-visible event for each newly-unlocked one.
        try:
            newly = check_achievements(_stats_cache)
        except Exception as e:
            newly = []
            print(f"[bridge] achievement check failed: {e}", file=sys.stderr)
        for agent_id, ach_id in newly:
            cat_entry = next((a for a in ACHIEVEMENTS_CATALOG if a["id"] == ach_id), None)
            if cat_entry is None:
                continue
            agent = next((a for a in AGENTS if a.get("public_id") == int(agent_id)), None)
            if agent is None:
                continue
            label = cat_entry["label"]
            icon = cat_entry["icon"]
            record_public_event(
                agent_name=agent["name"],
                kind="tool_start",
                tool_id=f"ach_{ach_id}_{agent_id}",
                tool_name="Read",
                status=f"{icon} Achievement: {label}",
                severity="info",
                payload={"achievement_id": ach_id, "label": label, "icon": icon},
                source_kind="achievement",
                ts_ms=int(time.time() * 1000),
            )
            print(f"[bridge] 🏆 achievement '{ach_id}' unlocked for agent {agent_id}",
                  file=sys.stderr)

    public_agents = [
        {
            "id": a["public_id"],
            "folderName": a["name"].replace("-", "_"),
        }
        for a in AGENTS
        if a["name"] in PUBLIC_WHITELIST and "public_id" in a
    ]
    payload = {
        "cursor": _public_event_seq,
        "agents": public_agents,
        "events": list(_public_events),
        "stats": _stats_cache,
        "achievements_catalog": ACHIEVEMENTS_CATALOG,
        "agents_achievements": {aid: sorted(v) for aid, v in _achievements_unlocked.items()},
    }
    body = json.dumps(payload, indent=2)

    try:
        PUBLIC_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PUBLIC_EVENTS_PATH.with_suffix(PUBLIC_EVENTS_PATH.suffix + ".tmp")
        tmp.write_text(body)
        tmp.replace(PUBLIC_EVENTS_PATH)
    except OSError as e:
        print(f"[bridge] public mirror write failed: {e}", file=sys.stderr)


def read_pixel_server_cfg() -> dict | None:
    """Read pixel-agents server.json (port + token). Returns None if extension
    hasn't activated yet."""
    try:
        return json.loads(PIXEL_SERVER_JSON.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def post_hook_event(cfg: dict, payload: dict) -> bool:
    """Pretend to be Claude Code: POST a hook event to pixel-agents.
    Returns True on success, False on network/server error."""
    url = f"http://127.0.0.1:{cfg['port']}/api/hooks/claude"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['token']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def register_external_session(cfg: dict, session_id: str, jsonl_path: Path, cwd: str) -> bool:
    """Send SessionStart + Stop to claim a fake external session.
    Pending sessions are filtered unless a confirmation event arrives — Stop counts."""
    ok = post_hook_event(
        cfg,
        {
            "hook_event_name": "SessionStart",
            "session_id": session_id,
            "transcript_path": str(jsonl_path),
            "cwd": cwd,
            "source": "startup",
        },
    )
    if not ok:
        return False
    time.sleep(0.05)
    return post_hook_event(
        cfg,
        {
            "hook_event_name": "Stop",
            "session_id": session_id,
        },
    )


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"agents": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def emit_session_opener(jsonl_path: Path, session_id: str, agent_name: str, cwd: str) -> str | None:
    if jsonl_path.exists() and jsonl_path.stat().st_size > 0:
        return None
    rec_uuid = str(uuid.uuid4())
    record = {
        "parentUuid": None,
        "isSidechain": False,
        "userType": "external",
        "cwd": cwd,
        "sessionId": session_id,
        "version": "1.0.0",
        "gitBranch": "",
        "type": "user",
        "uuid": rec_uuid,
        "timestamp": iso_now(),
        "message": {
            "role": "user",
            "content": f"[pixel-office] {agent_name} session bridged",
        },
    }
    append_jsonl(jsonl_path, record)
    return rec_uuid


def emit_tool_use(
    jsonl_path: Path,
    session_id: str,
    parent_uuid: str | None,
    tool_name: str,
    description: str,
    payload: dict,
    cwd: str,
) -> tuple[str, str]:
    rec_uuid = str(uuid.uuid4())
    tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
    record = {
        "parentUuid": parent_uuid,
        "isSidechain": False,
        "userType": "external",
        "cwd": cwd,
        "sessionId": session_id,
        "version": "1.0.0",
        "gitBranch": "",
        "type": "assistant",
        "uuid": rec_uuid,
        "timestamp": iso_now(),
        "requestId": "req_" + uuid.uuid4().hex[:24],
        "message": {
            "id": "msg_" + uuid.uuid4().hex[:24],
            "type": "message",
            "role": "assistant",
            "model": "ibitlabs-pixel-bridge",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tool_name,
                    "input": {"description": description, **payload},
                }
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    }
    append_jsonl(jsonl_path, record)
    return rec_uuid, tool_use_id


def emit_tool_result(
    jsonl_path: Path,
    session_id: str,
    parent_uuid: str,
    tool_use_id: str,
    content: str,
    cwd: str,
) -> str:
    rec_uuid = str(uuid.uuid4())
    record = {
        "parentUuid": parent_uuid,
        "isSidechain": False,
        "userType": "external",
        "cwd": cwd,
        "sessionId": session_id,
        "version": "1.0.0",
        "gitBranch": "",
        "type": "user",
        "uuid": rec_uuid,
        "timestamp": iso_now(),
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                }
            ],
        },
    }
    append_jsonl(jsonl_path, record)
    return rec_uuid


def emit_turn_duration(jsonl_path: Path, session_id: str, cwd: str, duration_ms: int = 1200) -> None:
    record = {
        "type": "system",
        "subtype": "turn_duration",
        "uuid": str(uuid.uuid4()),
        "sessionId": session_id,
        "timestamp": iso_now(),
        "cwd": cwd,
        "data": {"duration_ms": duration_ms},
    }
    append_jsonl(jsonl_path, record)


def read_new_events_chain(agent: dict, agent_state: dict) -> list[dict]:
    path: Path = agent["source_path"]
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with path.open("rb") as f:
            f.seek(agent_state.get("source_offset", 0))
            data = f.read()
            agent_state["source_offset"] = f.tell()
        for raw in data.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    except Exception as e:
        print(f"[bridge] error reading chain {path}: {e}", file=sys.stderr)
    return out


def classify_log_line(line: str) -> str:
    low = line.lower()
    if "error" in low or "traceback" in low or "exception" in low:
        return "error"
    if "bootout" in low:
        return "boot"
    if "alert" in low or "ghost" in low or "mismatch" in low or "drift" in low:
        return "alert"
    if "open" in low and ("position" in low or "long" in low or "short" in low):
        return "open"
    if "close" in low and ("position" in low or "exit" in low):
        return "close"
    if "ok" in low or "agree" in low:
        return "ok"
    return "default"


MTIME_THROTTLE_SEC = 15  # don't fire more than 1 mtime tick per N sec


def read_new_events_mtime(agent: dict, agent_state: dict) -> list[dict]:
    """Source type for rewrite-in-place state files (no append). Emits one
    'tick' event when the file's mtime advances — but throttled so a 1Hz
    state-file rewrite doesn't flood the office."""
    path: Path = agent["source_path"]
    if not path.exists():
        return []
    try:
        cur_mtime = path.stat().st_mtime
    except OSError:
        return []
    last_mtime = agent_state.get("source_mtime", 0.0)
    last_emit = agent_state.get("mtime_last_emit", 0.0)
    now = time.time()
    if cur_mtime > last_mtime and now - last_emit >= MTIME_THROTTLE_SEC:
        agent_state["source_mtime"] = cur_mtime
        agent_state["mtime_last_emit"] = now
        return [{"kind": "tick"}]
    if cur_mtime > last_mtime:
        # Still track latest mtime even if throttled, so we don't re-fire on the same change.
        agent_state["source_mtime"] = cur_mtime
    return []


def read_new_events_log(agent: dict, agent_state: dict) -> list[dict]:
    path: Path = agent["source_path"]
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        cur_offset = agent_state.get("source_offset", 0)
        size = path.stat().st_size
        if size < cur_offset:
            cur_offset = 0
        with path.open("rb") as f:
            f.seek(cur_offset)
            data = f.read()
            agent_state["source_offset"] = f.tell()
        for raw in data.splitlines():
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            out.append({"kind": classify_log_line(text), "_log_line": text[:200]})
    except Exception as e:
        print(f"[bridge] error reading log {path}: {e}", file=sys.stderr)
    return out


def close_active_tool(
    agent_state: dict,
    jsonl_path: Path,
    session_id: str,
    cwd: str,
    duration_ms: int = 1200,
    agent_name: str | None = None,
) -> None:
    tool_use_id = agent_state.get("active_tool_use_id")
    if not tool_use_id:
        return
    rec = emit_tool_result(
        jsonl_path,
        session_id,
        agent_state["last_record_uuid"],
        tool_use_id,
        agent_state.get("active_result_text", "done"),
        cwd,
    )
    emit_turn_duration(jsonl_path, session_id, cwd, duration_ms)
    agent_state["last_record_uuid"] = rec
    agent_state["active_tool_use_id"] = None

    # Public mirror: mark the tool as ended so browser FSM clears active state.
    if agent_name is not None:
        record_public_event(
            agent_name=agent_name,
            kind="tool_end",
            tool_id=tool_use_id,
            tool_name=None,
            status=None,
            severity=None,
        )


def process_agent(agent: dict, agent_state: dict, now_ts: float) -> None:
    name = agent["name"]
    session_id = agent_state["uuid"]
    jsonl_path = agent_jsonl_path(name, session_id)
    cwd = str(WORKSPACE_DIR)

    if agent["source_type"] == "receipt_chain":
        events = read_new_events_chain(agent, agent_state)
    elif agent["source_type"] == "log_tail":
        events = read_new_events_log(agent, agent_state)
    elif agent["source_type"] == "file_mtime":
        events = read_new_events_mtime(agent, agent_state)
    else:
        events = []

    # Close prior active tool if its burst duration has elapsed.
    if agent_state.get("active_tool_use_id"):
        started = agent_state.get("active_tool_started_ts", 0)
        if now_ts - started > TOOL_BURST_DURATION_SEC:
            close_active_tool(agent_state, jsonl_path, session_id, cwd, 1200, name)

    for ev in events:
        kind = ev.get("kind", "default")
        mapping = agent["kind_map"].get(kind)
        if mapping is None:
            tool_name = agent["default_tool"]
            desc = f"{name}: {kind}"
            severity = agent.get("default_severity", "info")
        else:
            tool_name, desc, severity = mapping

        # Hold-down for noisy ghost-watchdog alerts on the public surface.
        # The watchdog already escalates internally (ntfy at 1, iMessage at 3,
        # bootout at 5 per feedback_coinbase_ip_allowlist_signature.md), so a
        # single transient GHOST tick is not actionable for a casual visitor.
        # Downgrade severity error→warn until 3 consecutive alerts (matches
        # the iMessage threshold — by then the operator is paying attention).
        # Reset to 0 on any `ok` tick.
        if name == "ghost-watchdog":
            if kind == "alert":
                streak = agent_state.get("ghost_alert_streak", 0) + 1
                agent_state["ghost_alert_streak"] = streak
                if streak < 3 and severity == "error":
                    severity = "warn"
            elif kind == "ok":
                agent_state["ghost_alert_streak"] = 0

        # Close any in-flight tool before starting new one.
        if agent_state.get("active_tool_use_id"):
            close_active_tool(agent_state, jsonl_path, session_id, cwd, 600, name)

        payload: dict = {"agent": name, "kind": kind}
        if "data" in ev:
            payload["data"] = ev["data"]
        if "_log_line" in ev:
            payload["log"] = ev["_log_line"]

        rec_uuid, tool_use_id = emit_tool_use(
            jsonl_path,
            session_id,
            agent_state.get("last_record_uuid"),
            tool_name,
            desc,
            payload,
            cwd,
        )
        agent_state["last_record_uuid"] = rec_uuid
        agent_state["active_tool_use_id"] = tool_use_id
        agent_state["active_tool_started_ts"] = now_ts
        agent_state["active_result_text"] = f"{name} {kind} ok"
        agent_state["last_event_ts"] = now_ts

        # Public mirror — only if agent is on the whitelist.
        # Pass through the receipt-chain data block (or the log line text)
        # so the LiveEventTicker can render structured content rather than
        # just the description string.
        public_payload: dict = {}
        if isinstance(ev.get("data"), dict):
            public_payload = dict(ev["data"])
        if "_log_line" in ev:
            public_payload["log"] = ev["_log_line"]
        record_public_event(
            agent_name=name,
            kind="tool_start",
            tool_id=tool_use_id,
            tool_name=tool_name,
            status=desc,
            severity=severity,
            payload=public_payload or None,
            source_kind=kind,
            ts_ms=ev.get("ts") if isinstance(ev.get("ts"), int) else None,
        )

    # Idle heartbeat
    if not agent_state.get("active_tool_use_id"):
        last_emission = max(
            agent_state.get("last_event_ts", 0),
            agent_state.get("last_heartbeat_ts", 0),
        )
        if now_ts - last_emission > HEARTBEAT_INTERVAL_SEC:
            rec_uuid, tool_use_id = emit_tool_use(
                jsonl_path,
                session_id,
                agent_state.get("last_record_uuid"),
                "Read",
                f"{name}: idle heartbeat",
                {"agent": name, "kind": "heartbeat"},
                cwd,
            )
            agent_state["last_record_uuid"] = rec_uuid
            agent_state["active_tool_use_id"] = tool_use_id
            agent_state["active_tool_started_ts"] = now_ts
            agent_state["active_result_text"] = "alive"
            agent_state["last_heartbeat_ts"] = now_ts

            record_public_event(
                agent_name=name,
                kind="tool_start",
                tool_id=tool_use_id,
                tool_name="Read",
                status=f"{name}: idle heartbeat",
                severity="info",
            )


def main() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    cwd = str(WORKSPACE_DIR)

    # Restore previously-unlocked achievements before stats begin computing.
    # C.2.1: trophies are sticky — once earned, they stay even if the
    # underlying metric regresses (e.g. WR slipping back below threshold).
    load_achievements_state()

    state = load_state()
    state.setdefault("agents", {})

    for agent in AGENTS:
        name = agent["name"]
        if name not in state["agents"]:
            # On first init, skip past any historical content in the source.
            # We only want to bridge events that happen from "now" onward.
            src: Path = agent["source_path"]
            initial_offset = src.stat().st_size if src.exists() else 0
            initial_mtime = src.stat().st_mtime if src.exists() else 0.0
            state["agents"][name] = {
                "uuid": str(uuid.uuid4()),
                "source_offset": initial_offset,
                "source_mtime": initial_mtime,
                "last_event_ts": 0.0,
                "last_heartbeat_ts": 0.0,
                "active_tool_use_id": None,
                "active_tool_started_ts": 0.0,
                "active_result_text": "done",
                "last_record_uuid": None,
            }
        sid = state["agents"][name]["uuid"]
        agent_dir(name).mkdir(parents=True, exist_ok=True)
        jsonl_path = agent_jsonl_path(name, sid)
        opener_uuid = emit_session_opener(jsonl_path, sid, name, cwd)
        if opener_uuid:
            state["agents"][name]["last_record_uuid"] = opener_uuid

    save_state(state)

    print(f"[bridge] bridging {len(AGENTS)} agents → {AGENTS_DIR}", file=sys.stderr)
    for a in AGENTS:
        print(f"[bridge]   {a['name']:<16} ← {a['source_path']}", file=sys.stderr)

    state.setdefault("pixel_server_started_at", 0)

    while True:
        now_ts = time.time()

        # Register fake external sessions with pixel-agents' hook server.
        # In hooks mode the extension ignores untracked jsonl — we must claim
        # each session_id via SessionStart + Stop (any non-SessionEnd event
        # confirms a pending session).
        cfg = read_pixel_server_cfg()
        if cfg:
            server_started = cfg.get("startedAt", 0)
            if server_started != state["pixel_server_started_at"]:
                # Extension (re)started: reset registration flags so every
                # agent gets re-claimed with the fresh port + token.
                for a in state["agents"].values():
                    a["registered"] = False
                state["pixel_server_started_at"] = server_started

            for agent in AGENTS:
                ast = state["agents"][agent["name"]]
                if not ast.get("registered"):
                    jp = agent_jsonl_path(agent["name"], ast["uuid"])
                    if register_external_session(cfg, ast["uuid"], jp, cwd):
                        ast["registered"] = True
                        print(
                            f"[bridge] registered {agent['name']} → "
                            f"session={ast['uuid'][:8]}...",
                            file=sys.stderr,
                        )

        for agent in AGENTS:
            agent_state = state["agents"][agent["name"]]
            try:
                process_agent(agent, agent_state, now_ts)
            except Exception as e:
                print(f"[bridge] error processing {agent['name']}: {e}", file=sys.stderr)
        save_state(state)
        try:
            write_public_mirror()
        except Exception as e:
            print(f"[bridge] write_public_mirror failed: {e}", file=sys.stderr)
        time.sleep(TICK_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[bridge] stopped", file=sys.stderr)
        sys.exit(0)
