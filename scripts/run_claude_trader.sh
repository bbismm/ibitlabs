#!/bin/zsh
#
# claude-trader — launchd-driven runner (Phase 0 / B-pure decision producer)
#
# Companion to ~/.claude/scheduled-tasks/claude-trader/SKILL.md.
# Replaces sol_sniper_main.py (paused 2026-05-25 00:37 EDT) as the SOL
# decision-maker on the iBitLabs \$1k→\$10k experiment.
#
# Schedule (Phase 0): manual invocation only for first day; launchd plist
# wires hourly heartbeat once smoke-test passes. plist:
#   ~/Library/LaunchAgents/com.ibitlabs.claude-trader.plist
#
# Logs: ~/ibitlabs/logs/claude-trader/<YYYYMMDD-HHMMSS>.log
# Decisions: ~/ibitlabs/logs/claude-trader/decisions.jsonl
#
# To run manually:
#   ~/ibitlabs/scripts/run_claude_trader.sh
#
# Phase 0 is decision-producer only — no Coinbase API calls, no order placement.
# Day 2-3 ships claude_trader_executor.py that consumes decisions.jsonl.

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/claude-trader"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
SKILL_FILE="$HOME/.claude/scheduled-tasks/claude-trader/SKILL.md"
DECISIONS_FILE="$LOG_DIR/decisions.jsonl"
NTFY_TOPIC="sol-sniper-bonny"

mkdir -p "$LOG_DIR"

# ntfy push helper — silent failure (never break the wrapper).
# Usage: ntfy_push "<title>" "<body>" "<priority>" "<tags>"
ntfy_push() {
  local title="$1" body="$2" priority="${3:-default}" tags="${4:-}"
  curl -s -o /dev/null --max-time 5 -X POST \
    -H "Title: $title" \
    -H "Priority: $priority" \
    -H "Tags: $tags" \
    -d "$body" \
    "https://ntfy.sh/$NTFY_TOPIC" 2>&1 || true
}

{
  echo "=== claude-trader run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  cwd: $(pwd)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill: $SKILL_FILE"
  echo "decisions log: $DECISIONS_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    ntfy_push "[claude-trader] FATAL — skill file missing" \
      "$SKILL_FILE not found. claude-trader cannot fire. Check ~/.claude/scheduled-tasks/claude-trader/" \
      "urgent" "rotating_light"
    exit 2
  fi

  # Sanity: confirm v5.3 LIVE bot is NOT running (Phase 0 requires v5.3 paused).
  if launchctl list | grep -q "com.ibitlabs.sniper$\| com.ibitlabs.sniper$"; then
    echo "FATAL: com.ibitlabs.sniper still loaded — claude-trader requires v5.3 paused"
    echo "       run: launchctl bootout gui/\$(id -u)/com.ibitlabs.sniper"
    ntfy_push "[claude-trader] FATAL — v5.3 collision" \
      "com.ibitlabs.sniper is loaded; claude-trader refusing to fire. Either v5.3 was bootstrapped or this is Day 3+ live wiring. Run: launchctl bootout gui/\$(id -u)/com.ibitlabs.sniper" \
      "urgent" "rotating_light"
    exit 3
  fi

  # Phase B.1 cadence gate. claude_trader_gate.py decides FIRE or SKIP based on:
  #   - invariant transition signals (regime flip / range break / position change)
  #   - cognition_mode-based heartbeat (Compression 1h / Regime Uncertain 15min /
  #     Expansion + Inventory Discovery 5min)
  #   - reflection clock (force fire if last reflection > 4h ago)
  #   - bootstrap (force fire if state.cognition_mode is null)
  #
  # Failure mode bias: any unreachable dependency → FIRE (safer to spawn
  # unnecessarily than silently skip during a real event).
  if [[ -x "$HOME/ibitlabs/scripts/claude_trader_gate.py" ]]; then
    GATE_VERDICT=$("$HOME/ibitlabs/scripts/claude_trader_gate.py" 2>&1)
    GATE_LOG_DIR="$HOME/ibitlabs/logs/claude-trader/gate"
    mkdir -p "$GATE_LOG_DIR"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $GATE_VERDICT" >> "$GATE_LOG_DIR/gate.log"
    echo "=== gate verdict: $GATE_VERDICT ==="
    if [[ "$GATE_VERDICT" == SKIP:* ]]; then
      echo "[claude-trader-gate] skip — wrapper exiting 0 without spawning Claude."
      echo "  reason: ${GATE_VERDICT#SKIP:}"
      exit 0
    fi
  else
    echo "WARN: gate script not found/executable; firing unconditionally"
  fi

  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
fire of the claude-trader skill (Phase 0 / B-pure decision producer for the
iBitLabs SOL perp \$1k→\$10k experiment). The skill contains your decision
framework, data sources, and output schema. You are the trader. No hard
constraints on sizing, leverage, symbol, or cohort — those are your call,
explain them in reasoning. Execute autonomously, do not pause for confirmation.

Phase 0 mode: produce a decision but DO NOT execute trades directly (the
separate executor handles execution and is currently in DRY_RUN). Append ONE
JSON line to ~/ibitlabs/logs/claude-trader/decisions.jsonl with the schema in
the skill. Print the 3-line stdout summary. Exit.

Skill instructions follow:
"
  # Capture decisions.jsonl line count BEFORE claude runs (else BEFORE==AFTER → false SILENT).
  LINES_BEFORE_FIRE=$(wc -l < "$DECISIONS_FILE" 2>/dev/null || echo 0)

  printf '%s\n%s\n' "$PREAMBLE" "$(cat "$SKILL_FILE")" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --model opus \
    --add-dir "$HOME/ibitlabs"

  STATUS=$?
  echo ""
  echo "---"
  echo "=== claude exit status: $STATUS ==="

  LINES_AFTER_FIRE=$LINES_BEFORE_FIRE  # default; will be set in validator below

  # Smoke test: verify decisions.jsonl grew by exactly 1 valid line.
  # Use file path (not stdin pipe) to avoid zsh inline-python UTF-8 locale issues.
  VALIDATOR_RC=0
  if [[ -f "$DECISIONS_FILE" ]]; then
    LINES_AFTER_FIRE=$(wc -l < "$DECISIONS_FILE" 2>/dev/null || echo 0)
    echo "=== last decision line (validate JSON) ==="
    PYTHONIOENCODING=utf-8 python3 - "$DECISIONS_FILE" <<'PYEOF' 2>&1 | head -40
import json, sys
path = sys.argv[1]
with open(path, encoding='utf-8') as f:
    last = None
    for line in f:
        if line.strip():
            last = line
if not last:
    print("ERROR: decisions.jsonl exists but is empty")
    sys.exit(1)
try:
    d = json.loads(last)
    print(f"decision={d.get('decision')} direction={d.get('direction')} confidence={d.get('confidence')}")
    print(f"price={d.get('current_price')} regime={d.get('regime')} balance={d.get('balance_usd')}")
    print(f"reasoning_chars={len(d.get('reasoning',''))}")
    print(f"valid JSON ✓")
except json.JSONDecodeError as e:
    print(f"INVALID JSON at char {e.pos}: {repr(last[max(0,e.pos-30):e.pos+30])}")
    sys.exit(2)
PYEOF
    VALIDATOR_RC=$?
  else
    echo "WARN: decisions.jsonl not created — Claude did not produce a decision"
  fi

  # Regenerate the public-facing JSON snapshot for /lab/claude. Silent failure;
  # the page is non-critical and we never want this to block the decision pipeline.
  if [[ -x "$HOME/ibitlabs/scripts/generate_claude_public_data.py" ]]; then
    echo "=== regenerate public data for /lab/claude ==="
    "$HOME/ibitlabs/scripts/generate_claude_public_data.py" 2>&1 | head -5 || \
      echo "WARN: public data regen failed (non-fatal)"
  fi

  # ── ntfy alerts on silent failures ─────────────────────────────────────────
  # Three failure modes worth a high-priority push (HOLD success is silent):
  #   a. claude exit code != 0
  #   b. decisions.jsonl didn't grow this fire
  #   c. validator caught invalid JSON
  if [[ "$STATUS" -ne 0 ]]; then
    ntfy_push "[claude-trader] FAIL — claude exit $STATUS" \
      "claude CLI returned exit code $STATUS at $(date -u +%H:%M:%SZ). Log: $LOG. Check subscription quota / API outage / wrapper sanity." \
      "high" "warning"
  elif [[ "$LINES_AFTER_FIRE" -le "$LINES_BEFORE_FIRE" ]]; then
    ntfy_push "[claude-trader] SILENT — no decision produced" \
      "Fire @ $(date -u +%H:%M:%SZ) finished exit=0 but decisions.jsonl did not grow (lines $LINES_BEFORE_FIRE → $LINES_AFTER_FIRE). Claude likely refused / forgot the JSONL write step. Log: $LOG" \
      "high" "warning"
  elif [[ "$VALIDATOR_RC" -ne 0 ]]; then
    ntfy_push "[claude-trader] INVALID JSON in last decision" \
      "Validator rc=$VALIDATOR_RC on last decisions.jsonl line. Executor will skip this decision. Log: $LOG" \
      "high" "warning"
  fi

  exit $STATUS
} 2>&1 | tee -a "$LOG"
