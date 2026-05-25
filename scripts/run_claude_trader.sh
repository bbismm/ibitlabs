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

mkdir -p "$LOG_DIR"

{
  echo "=== claude-trader run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  cwd: $(pwd)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill: $SKILL_FILE"
  echo "decisions log: $DECISIONS_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 2
  fi

  # Sanity: confirm v5.3 LIVE bot is NOT running (Phase 0 requires v5.3 paused).
  if launchctl list | grep -q "com.ibitlabs.sniper$\| com.ibitlabs.sniper$"; then
    echo "FATAL: com.ibitlabs.sniper still loaded — claude-trader requires v5.3 paused"
    echo "       run: launchctl bootout gui/\$(id -u)/com.ibitlabs.sniper"
    exit 3
  fi

  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
fire of the claude-trader skill (Phase 0 / B-pure decision producer for the
iBitLabs SOL perp \$1k→\$10k experiment). The skill contains all decision rules,
hard constraints (qty=1, lev=1, balance floor \$750), data sources, and output
schema. Execute autonomously, do not pause for confirmation.

Phase 0 DAY 1 specific: produce a decision but DO NOT execute trades. Append
ONE JSON line to ~/ibitlabs/logs/claude-trader/decisions.jsonl with the schema
in the skill. Print the 3-line stdout summary. Exit.

Skill instructions follow:
"
  printf '%s\n%s\n' "$PREAMBLE" "$(cat "$SKILL_FILE")" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --model opus \
    --add-dir "$HOME/ibitlabs"

  STATUS=$?
  echo ""
  echo "---"
  echo "=== claude exit status: $STATUS ==="

  # Smoke test: verify decisions.jsonl grew by exactly 1 valid line.
  # Use file path (not stdin pipe) to avoid zsh inline-python UTF-8 locale issues.
  if [[ -f "$DECISIONS_FILE" ]]; then
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
  else
    echo "WARN: decisions.jsonl not created — Claude did not produce a decision"
  fi

  exit $STATUS
} 2>&1 | tee -a "$LOG"
