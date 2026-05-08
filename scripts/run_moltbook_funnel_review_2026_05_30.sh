#!/bin/zsh
#
# moltbook-funnel-review-2026-05-30 — one-shot 30-day review of the brand-builder
# agent-participation-funnel spec shipped 2026-04-30.
#
# Schedule: 2026-05-30 10:00 LOCAL (EDT = 14:00 UTC). Self-disables on success.
#
# Manual run (testing):
#   ~/ibitlabs/scripts/run_moltbook_funnel_review_2026_05_30.sh
#
# Reads:
#   - /Users/bonnyagent/ibitlabs/web/public/data/contributors.json
#   - /Users/bonnyagent/ibitlabs/logs/moltbook-brand-builder/*.log (last 7d)
#   - /Users/bonnyagent/ibitlabs/logs/shadow_*_rule.jsonl
#   - https://moltbook.com/api/v1/...  (public)
# Writes:
#   - Notion subpage under Strategy Optimization (3403c821a4aa81b5ba43dbcdb62e95bc)
#   - https://ntfy.sh/sol-sniper-bonny  (one push)
#   - This script self-disables the plist on success.

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/moltbook-funnel-review-2026-05-30"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
SKILL_FILE="$HOME/Documents/Claude/Scheduled/moltbook-funnel-review-2026-05-30/SKILL.md"

mkdir -p "$LOG_DIR"

{
  echo "=== moltbook-funnel-review-2026-05-30 run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  PREAMBLE="UNATTENDED LAUNCHD RUN — no human is watching. This is the 30-day
review of the brand-builder agent-participation-funnel spec shipped 2026-04-30.
The reader of the Notion report is Bonny — lead with verdict, no narrative
summarization, no restating what the spec already says.

Step 7 (self-disable) is mandatory and load-bearing. If you skip it, this job
fires every May 30 forever and pollutes the launchd log. Run it even if Steps
5-6 partially failed.

Skill instructions follow:
"
  printf '%s\n%s\n' "$PREAMBLE" "$(cat "$SKILL_FILE")" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --model sonnet \
    --add-dir "$HOME/ibitlabs" \
    --add-dir "$HOME/Library/LaunchAgents"

  STATUS=$?
  echo ""
  echo "---"
  echo "=== claude exit status: $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
