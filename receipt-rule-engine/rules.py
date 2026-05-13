"""Operator's rules for the Receipt rule engine.

Loaded by `~/ibitlabs/receipt-rule-engine/engine.py` (mirror of the public
`scripts/rule_engine.py` from the receipt repo, copied here to dodge macOS
TCC on ~/Documents/).

Edit this file to change which chain events fire which actions. Reload
the daemon afterward:

    launchctl kickstart -k gui/$(id -u)/com.ibitlabs.receipt-rule-engine

Or just kill its PID — launchd will respawn within ~30s and pick up the
new rules.
"""

# Map short chain names → JSONL paths. The engine watches all of these.
CHAINS = {
    "shadow": "/Users/bonnyagent/ibitlabs/audit_export/sniper-v5.1-shadow.realtime.receipt.jsonl",
    "live":   "/Users/bonnyagent/ibitlabs/audit_export/sniper-v5.1-live.realtime.receipt.jsonl",
}

# Receipt rule schema:
#   name:               required, debounce key
#   chains:             optional, default ["*"] — list of chain names or "*"
#   match:              required, dict of {field_path: expected}
#       field_path uses dotted notation: "data.action", "agent", etc.
#       expected: scalar (equality), list (membership), or bool (truthiness)
#   do:                 required, list of action dicts
#   debounce_seconds:   optional, default 0 — same rule won't fire twice within N seconds
RULES = [
    # ---- Live trading events: trade opens ----
    # Fires when sniper-live emits a claim with action open_long / open_short.
    # Quiet on shadow because paper trades aren't worth a phone buzz.
    {
        "name": "live_position_opened",
        "chains": ["live"],
        "match": {
            "kind": "claim",
            "data.action": ["open_long", "open_short"],
        },
        "do": [
            {
                "type": "ntfy",
                "topic": "sol-sniper-bonny",
                "tags": "bell,money_with_wings",
                "title": "🎯 Live position opened",
                "body": "{data.action} {data.symbol} size={data.size} @ ${data.price_intended}",
            },
        ],
        "debounce_seconds": 10,
    },

    # ---- Live trading events: trade closes ----
    {
        "name": "live_position_closed",
        "chains": ["live"],
        "match": {
            "kind": "claim",
            "data.action": ["close_long", "close_short"],
        },
        "do": [
            {
                "type": "ntfy",
                "topic": "sol-sniper-bonny",
                "tags": "white_check_mark",
                "title": "Live position closing",
                "body": "{data.action} reason={data.exit_reason} @ ${data.price_intended}",
            },
        ],
        "debounce_seconds": 10,
    },

    # ---- Live trading events: fill confirmed by exchange ----
    # Lower priority — the open/close already pinged; this is the "venue
    # said it filled" follow-up. Useful for catching latency issues.
    {
        "name": "live_fill_confirmed",
        "chains": ["live"],
        "match": {
            "kind": "verified",
        },
        "do": [
            {
                "type": "ntfy",
                "topic": "sol-sniper-bonny",
                "priority": "low",
                "tags": "white_check_mark",
                "title": "Fill confirmed",
                "body": "{data.source} @ ${data.fill_price} ({data.filled_size})",
            },
        ],
        "debounce_seconds": 5,
    },

    # ---- Reconciliation failure on EITHER chain ----
    # This is the killer alert — agent's book disagrees with venue truth.
    # Either shadow strategy has a bug, or live has ghost-position drift.
    {
        "name": "recon_failed",
        "chains": ["*"],
        "match": {
            "kind": "reconciliation",
            "data.match": False,
        },
        "do": [
            {
                "type": "ntfy",
                "topic": "sol-sniper-bonny",
                "priority": "urgent",
                "tags": "warning,rotating_light",
                "title": "🚨 Reconciliation FAILED",
                "body": "agent={agent} chain seq={seq}",
            },
            # Bootout disabled by default — uncomment after confirming
            # the false-positive rate is low enough to auto-act on.
            # {"type": "shell", "cmd": "/Users/bonnyagent/ibitlabs/scripts/bootout.sh"},
        ],
        "debounce_seconds": 60,
    },

    # ---- Explicit error events from live bot ----
    {
        "name": "live_error",
        "chains": ["live"],
        "match": {
            "kind": "error",
        },
        "do": [
            {
                "type": "ntfy",
                "topic": "sol-sniper-bonny",
                "priority": "high",
                "tags": "x",
                "title": "Error in {agent}",
                "body": "{data.phase} phase: {data.message}",
            },
        ],
        "debounce_seconds": 30,
    },

    # ---- Anchor events (informational, low frequency) ----
    {
        "name": "live_anchor",
        "chains": ["live"],
        "match": {
            "kind": "anchor",
        },
        "do": [
            {
                "type": "ntfy",
                "topic": "sol-sniper-bonny",
                "priority": "low",
                "tags": "anchor",
                "title": "Chain anchored",
                "body": "{data.anchor_kind} :: {data.anchor_uri}",
            },
        ],
        "debounce_seconds": 3600,
    },

    # ════════════════════════════════════════════════════════════════════
    # AUTO-HEAL RULES (Tier 1: idempotent, safe to re-run)
    # ════════════════════════════════════════════════════════════════════
    # `auto: True` is the explicit consent for shell actions to execute.
    # Without it, shell actions are blocked-and-logged. ntfy/iMessage are
    # never gated (low blast radius). Tier 3 (irreversible / live-money)
    # actions MUST NOT have auto: True — they're ntfy-only above.
    # ════════════════════════════════════════════════════════════════════

    # If the live chain has gone > 24h without an anchor event, auto-run
    # anchor_daily.py. SDK now uses fcntl.flock so concurrent writes from
    # the live bot are safe.
    {
        "name": "auto_anchor_stale",
        "chains": ["live"],
        "match": {
            "absent": {"kind": "anchor", "for_seconds": 86400},  # 24h
        },
        "auto": True,
        "do": [
            {
                "type": "shell",
                "cmd": "/usr/bin/python3 /Users/bonnyagent/ibitlabs/receipt-rule-engine/scripts/anchor_daily.py --chain /Users/bonnyagent/ibitlabs/audit_export/sniper-v5.1-live.realtime.receipt.jsonl",
            },
            {
                "type": "ntfy",
                "topic": "sol-sniper-bonny",
                "priority": "low",
                "tags": "anchor,robot",
                "title": "Auto-anchored stale chain",
                "body": "live chain had no anchor in 24h+; rule engine ran anchor_daily.py",
            },
        ],
        "debounce_seconds": 1800,  # at most once per 30 min
    },

    # If the live chain has gone > 6h without a reconciliation event,
    # auto-run reconcile_now.py.
    {
        "name": "auto_reconcile_overdue",
        "chains": ["live"],
        "match": {
            "absent": {"kind": "reconciliation", "for_seconds": 21600},  # 6h
        },
        "auto": True,
        "do": [
            {
                "type": "shell",
                "cmd": "/usr/bin/python3 /Users/bonnyagent/ibitlabs/receipt-rule-engine/scripts/reconcile_now.py --out /Users/bonnyagent/ibitlabs/audit_export/sniper-v5.1-live.realtime.receipt.jsonl",
            },
            {
                "type": "ntfy",
                "topic": "sol-sniper-bonny",
                "priority": "low",
                "tags": "magnifying_glass_tilted_left,robot",
                "title": "Auto-reconciled overdue chain",
                "body": "live chain had no reconciliation in 6h+; rule engine ran reconcile_now.py",
            },
        ],
        "debounce_seconds": 900,  # at most once per 15 min
    },
]
