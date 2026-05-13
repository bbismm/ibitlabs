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
# Banlist lives outside the repo so confidential terms never enter git.
# Format: one term per line; `#` lines are comments. Loaded at runtime.
BANLIST_FILE="$HOME/.config/ibitlabs/saga_banlist.txt"

mkdir -p "$LOG_DIR"

{
  echo "=== saga-daily run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "banlist:     $BANLIST_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  if [[ ! -f "$BANLIST_FILE" ]]; then
    echo "FATAL: confidentiality banlist not found at $BANLIST_FILE"
    echo "       saga-daily refuses to run without a guardrail. Populate the"
    echo "       file (one banned term per line) before re-firing."
    exit 1
  fi

  BANLIST_BODY="$(grep -vE '^\s*(#|$)' "$BANLIST_FILE")"
  if [[ -z "$BANLIST_BODY" ]]; then
    echo "FATAL: banlist at $BANLIST_FILE has no terms (only comments/blank lines)."
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

🔒 CONFIDENTIALITY GUARDRAIL (operator-issued, NON-NEGOTIABLE):
The terms enumerated below refer to projects, agents, or addresses
that are completely confidential. They must NEVER appear in this
saga chapter or any saga chapter, in ANY form. Even ANONYMIZED
references that imply the EXISTENCE of these projects are banned —
the existence itself is the secret. The only public story is the
SOL perpetual sniper bot, \$1k → \$10k single flagship experiment.

Banned terms (loaded from operator-local banlist; listed only for
recognition — do not echo them back):
$BANLIST_BODY

If today's narrative survey surfaces any of this material, you MUST
either (a) write from a different angle that does not require it,
OR (b) emit 'no_scene_today: <reason> — confidentiality gate' and
stop without publishing. Re-read the relevant feedback_* memory
entries before drafting.

Skill instructions follow:
"
  # 2026-05-10: dropped --max-budget-usd 1.50 per feedback_no_per_run_usd_caps.md.
  # Anthropic's 5h token-window IS the cap; per-run USD caps double-count and
  # silently throttle wrappers mid-task. This was missed in the 11-wrapper
  # patch round 2026-05-02.
  printf '%s\n%s\n' "$PREAMBLE" "$(cat "$SKILL_FILE")" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --model sonnet \
    --add-dir "$HOME/ibitlabs" \
    --add-dir "$HOME/Documents/ai-creator-saga"

  STATUS=$?
  echo ""
  echo "---"
  echo "=== claude exit status: $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
