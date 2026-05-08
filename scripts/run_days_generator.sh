#!/bin/zsh
#
# days-generator — launchd-driven runner
#
# Replaces the scheduled-tasks MCP path that depends on Claude Code app being
# open. Now runs via launchd (OS-level cron) every night at 23:50 LOCAL,
# regardless of whether Claude Code is in the foreground.
#
# Schedule: launchd plist com.ibitlabs.days-generator fires at 23:50 LOCAL
# (matches the prior scheduled-tasks cron `50 23 * * *`).
#
# Logs: ~/ibitlabs/logs/days-generator/<YYYYMMDD-HHMMSS>.log
#
# To run manually for testing:
#   ~/ibitlabs/scripts/run_days_generator.sh
#
# Migrated to launchd 2026-04-28 after observing scheduled-tasks MCP fires
# silently dropped Day 21 (04-27 23:50 fire) while Claude Code app was closed.
# Same skip signature as sniper-checks (also migrated 2026-04-28) and
# moltbook-* jobs (migrated 2026-04-27). Pattern locked in CLAUDE.md:
# anything that must fire daily regardless of app state goes on launchd.

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/days-generator"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
SKILL_FILE="$HOME/.claude/scheduled-tasks/days-generator/SKILL.md"

mkdir -p "$LOG_DIR"

{
  echo "=== days-generator run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  cwd: $(pwd)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
nightly run of the days-generator skill. Compose tonight's Day N entry for
ibitlabs.com/days following the dual-POV (她/它) Polanyi framework, write to
web/public/data/days.json, regenerate days.rss, commit, and wrangler-deploy.
Execute autonomously. Do NOT pause for confirmation.

If today's entry already exists in days.json (skip-gate), output a one-line
'skip: dayNumber=N already exists' marker and exit cleanly — that is normal.

Skill instructions follow:
"
  printf '%s\n%s\n' "$PREAMBLE" "$(cat "$SKILL_FILE")" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --max-budget-usd 0.50 \
    --model sonnet \
    --add-dir "$HOME/ibitlabs"

  STATUS=$?
  echo ""
  echo "---"
  echo "=== claude exit status: $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
