#!/bin/zsh
#
# moltbook-learning-loop — launchd-driven runner
#
# Replaces the scheduled-tasks MCP path that depends on Claude Code app being
# open. Now runs via launchd (OS-level cron) every 12h, regardless of whether
# Claude Code is in the foreground.
#
# Schedule: launchd plist com.ibitlabs.moltbook-learning-loop fires at
# 05:00 and 17:00 LOCAL time (matches the prior scheduled-tasks cron
# `0 5,17 * * *`).
#
# Logs: ~/ibitlabs/logs/moltbook-learning-loop/<YYYYMMDD-HHMMSS>.log
#
# To run manually for testing:
#   ~/ibitlabs/scripts/run_moltbook_learning_loop.sh
#
# Migrated to launchd 2026-04-27 after observing scheduled-tasks MCP fires
# silently dropped while Claude Code app was closed (04-26 → 04-27).

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/moltbook-learning-loop"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
SKILL_FILE="$HOME/.claude/scheduled-tasks/moltbook-learning-loop/SKILL.md"

mkdir -p "$LOG_DIR"

{
  echo "=== moltbook-learning-loop run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  cwd: $(pwd)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
12-hour learning-loop scan. The skill's Step-0 contradiction check, Polanyi
5-rule pre-publish gate, do-not-revive list, and Salah 24h cap ARE the
approval gates. Do NOT pause to ask 'post this reply?' — if a candidate
clears the gates, post directly. If it fails, skip silently per the SKILL's
'silence is a valid action' clause.

This task writes to Notion Learning Log + updates ~/ibitlabs/CLAUDE.md.
Both writes are expected; do not surface them for confirmation. Replies are
optional (max 3 per run); zero replies is a valid successful run.

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
