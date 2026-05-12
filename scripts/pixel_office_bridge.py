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
