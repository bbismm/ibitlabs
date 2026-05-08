#!/bin/zsh
#
# saga-daily — launchd-driven runner
#
# Daily Vol 2 entry of ai-creator-saga: writes 300-800 字 AI-POV scene,
# deploys to ibitlabs.com/saga/en/vol2/, cross-posts to Twitter @BonnyOuyang
# + Telegram ibitlabs_signal_bot. Twitter exception explicitly confirmed
# by Bonny 2026-04-26 for saga-daily only (see feedback_social_paused.md).
#
# Schedule: launchd plist com.ibitlabs.saga-daily fires daily at 22:30
# LOCAL time. Matches the prior scheduled-tasks cron `30 22 * * *`.
#
# Logs: ~/ibitlabs/logs/saga-daily/<YYYYMMDD-HHMMSS>.log
#
# Migrated to launchd 2026-04-28 — same architectural fix as the 4
# Moltbook automations migrated 2026-04-27. Cowork scheduled-tasks MCP
# only fires when Claude Code app is open; launchd runs at OS level
# regardless. Vol 2 is a daily serial — missed chapters break narrative
# continuity.

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/saga-daily"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
SKILL_FILE="$HOME/.claude/scheduled-tasks/saga-daily/SKILL.md"

mkdir -p "$LOG_DIR"

{
  echo "=== saga-daily run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
22:30 EDT daily Vol 2 saga entry. The skill itself defines the survey
protocol, voice, length, and publish chain (deploy + Twitter + Telegram).
Approval has already been given by the operator at SKILL.md commit time.
Do NOT pause to ask 'approve this entry?' — the SKILL's pre-publish
checks ARE the approval. If today's survey produces no scene worth
writing, output 'no_scene_today: <why>' and stop without publishing —
zero output is acceptable on a genuinely thin day, but the bot has been
trading and the lab has been shipping nearly every day, so this should
be rare.

Skill instructions follow:
"
  printf '%s\n%s\n' "$PREAMBLE" "$(cat "$SKILL_FILE")" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --max-budget-usd 1.50 \
    --model sonnet \
    --add-dir "$HOME/ibitlabs" \
    --add-dir "$HOME/Documents/ai-creator-saga"

  STATUS=$?
  echo ""
  echo "---"
  echo "=== claude exit status: $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
