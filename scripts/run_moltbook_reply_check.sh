#!/bin/zsh
#
# moltbook-reply-check — launchd-driven runner
#
# Every 2h scan: reactive comments on @ibitlabs_agent posts (max 1) +
# proactive hot-thread attack in 2-6h window from named interlocutors
# (max 1). Silence is the default — most runs post nothing.
#
# Schedule: launchd plist com.ibitlabs.moltbook-reply-check fires every 2h
# at minute 30 (01:30, 03:30, 05:30, ..., 23:30 LOCAL time). Matches the
# prior scheduled-tasks cron `30 1,3,5,7,9,11,13,15,17,19,21,23 * * *`.
#
# Logs: ~/ibitlabs/logs/moltbook-reply-check/<YYYYMMDD-HHMMSS>.log
#
# To run manually for testing:
#   ~/ibitlabs/scripts/run_moltbook_reply_check.sh
#
# Migrated to launchd 2026-04-27 after observing scheduled-tasks MCP fires
# silently dropped while Claude Code app was closed (04-26 → 04-27).

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/moltbook-reply-check"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
SKILL_FILE="$HOME/.claude/scheduled-tasks/moltbook-reply-check/SKILL.md"

mkdir -p "$LOG_DIR"

{
  echo "=== moltbook-reply-check run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  cwd: $(pwd)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
2-hour reply-check tick. Max 2 actions per run (1 reactive + 1 proactive
hot-thread attack). Silence on both layers is a SUCCESSFUL outcome if the
gates correctly identified nothing worthy.

The skill's Polanyi 5-rule pre-publish checklist, do-not-revive filter,
karma-≥200 substance gate, Salah 24h cap, and 2-6h hot-thread window ARE
the approval gates. Do NOT pause to ask 'post this reply?' — if a candidate
clears all gates, post directly. If it fails, skip — this task explicitly
permits zero output.

Do NOT write new posts. Do NOT update Notion or CLAUDE.md. Reply / hot-thread
attack only.

Skill instructions follow:
"
  printf '%s\n%s\n' "$PREAMBLE" "$(cat "$SKILL_FILE")" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --model sonnet \
    --add-dir "$HOME/ibitlabs" \
    --add-dir "$HOME/Documents/Claude/Scheduled/moltbook-brand-builder"

  STATUS=$?
  echo ""
  echo "---"
  echo "=== claude exit status: $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
