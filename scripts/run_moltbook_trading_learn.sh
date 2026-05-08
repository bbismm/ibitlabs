#!/bin/zsh
#
# moltbook-trading-learn — launchd-driven runner
#
# Replaces the scheduled-tasks MCP path that depends on Claude Code app being
# open. Now runs via launchd (OS-level cron) every morning at 08:00 LOCAL,
# regardless of whether Claude Code is in the foreground.
#
# Schedule: launchd plist com.ibitlabs.moltbook-trading-learn fires at 08:00
# LOCAL (matches the prior scheduled-tasks cron `0 8 * * *`).
#
# Logs: ~/ibitlabs/logs/moltbook-trading-learn/<YYYYMMDD-HHMMSS>.log
#
# To run manually for testing:
#   ~/ibitlabs/scripts/run_moltbook_trading_learn.sh
#
# Migrated to launchd 2026-04-30 after observing scheduled-tasks MCP fires
# silently dropped 04-23 → 04-29 (7-day gap in moltbook_learnings.md). Same
# failure pattern as the moltbook-* family migration of 2026-04-27.
#
# OPEN ISSUE: this SKILL relies on the Claude-in-Chrome browser MCP because
# moltbook.com is a Next.js CSR site. If the headless launchd run cannot
# connect to the browser MCP, the run will fail at step 1. Watch tomorrow's
# log; if it dies on browser access, fall back to rewriting step 1 against
# moltbook's REST API (other moltbook-* tasks already use the API path).

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/moltbook-trading-learn"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
SKILL_FILE="$HOME/.claude/scheduled-tasks/moltbook-trading-learn/SKILL.md"

mkdir -p "$LOG_DIR"

{
  echo "=== moltbook-trading-learn run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  cwd: $(pwd)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
daily morning scan of moltbook.com/m/trading for insights relevant to the
SOL sniper strategy. Output target: ~/ibitlabs/docs/moltbook_learnings.md
(prepend today's section under '## YYYY-MM-DD'), plus Notion sync via
notion-update-page on page 3493c821-a4aa-8197-8ca6-d664aab4960e.

Execute autonomously. Do NOT pause for confirmation. Never edit strategy
code. Never commit/push. If Moltbook is unreachable or browser MCP isn't
available, log the failure clearly under today's heading and exit cleanly
with a one-line marker — silence is NOT a valid action for this task.

Skill instructions follow:
"
  printf '%s\n%s\n' "$PREAMBLE" "$(cat "$SKILL_FILE")" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --model sonnet \
    --add-dir "$HOME/ibitlabs"

  STATUS=$?
  echo ""
  echo "---"
  echo "=== claude exit status: $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
