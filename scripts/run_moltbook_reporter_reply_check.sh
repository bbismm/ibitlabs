#!/bin/zsh
#
# moltbook-reporter-reply-check — launchd-driven runner
#
# Every 6h scan: reactive comments on @ibitlabs_reporter posts only (max 1).
# Reporter persona — interviewer voice, no proactive hot-thread attack.
# Sibling to run_moltbook_reply_check.sh which scans @ibitlabs_agent.
#
# Schedule: launchd plist com.ibitlabs.moltbook-reporter-reply-check fires every
# 6h at minute :30 LOCAL — 04:30 / 10:30 / 16:30 / 22:30. Offset 3h from the
# agent reply-check (which fires :30 at 01/05/09/13/17/21) so the two never
# collide on the rate-limit window.
#
# Logs: ~/ibitlabs/logs/moltbook-reporter-reply-check/<YYYYMMDD-HHMMSS>.log
#
# To run manually for testing:
#   ~/ibitlabs/scripts/run_moltbook_reporter_reply_check.sh
#
# Created 2026-05-13 to close the gap noted in Moltbook Learning Summary
# Scan #55: "Reporter's surface; brand-builder did not engage. Observe."

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/moltbook-reporter-reply-check"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
SKILL_FILE="$HOME/.claude/scheduled-tasks/moltbook-reporter-reply-check/SKILL.md"

mkdir -p "$LOG_DIR"

{
  echo "=== moltbook-reporter-reply-check run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  cwd: $(pwd)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  # Verify reporter key is reachable (without printing it).
  if ! /usr/bin/security find-generic-password -s ibitlabs-moltbook-reporter -a ibitlabs -w >/dev/null 2>&1; then
    echo "FATAL: reporter Keychain entry 'ibitlabs-moltbook-reporter' not found."
    exit 1
  fi
  echo "keychain: ibitlabs-moltbook-reporter reachable (key sha-prefix: $(/usr/bin/security find-generic-password -s ibitlabs-moltbook-reporter -a ibitlabs -w | shasum -a 256 | cut -c1-8))"
  echo "---"

  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
6-hour reporter reply-check tick. You are speaking AS @ibitlabs_reporter,
NOT @ibitlabs_agent. Different persona, different voice, different API key.

Reporter Moltbook key: read at runtime from Keychain via
\`security find-generic-password -s ibitlabs-moltbook-reporter -a ibitlabs -w\`.
NEVER write the key to disk and NEVER print it in any log line or output.
Pass it explicitly to moltbook_comment.py via --api-key — do not rely on the
default Keychain lookup (which would resolve to the agent key).

Max 1 reactive reply per run. Reactive ONLY — no proactive hot-thread attack
on non-reporter posts (that surface belongs to moltbook-reply-check).
Silence is a SUCCESSFUL outcome if the gates correctly identified nothing
worthy.

The skill's Polanyi 5-rule pre-publish checklist, do-not-revive filter
(SKILL_REFERENCE.md §R4), karma-≥200 substance gate, nested-replies
self-reply check, and cross-persona dedup ARE the approval gates. Do NOT
pause to ask 'post this reply?' — if a candidate clears all gates, post
directly. If it fails, skip.

Do NOT write new posts. Do NOT update Notion or CLAUDE.md. Reactive
comment-reply only.

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
