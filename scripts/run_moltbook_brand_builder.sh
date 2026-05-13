#!/bin/zsh
#
# moltbook-brand-builder — launchd-driven runner
#
# Replaces the Cowork scheduled-task path that could not load the local stdio
# brand-publishers MCP. This wrapper invokes `claude` CLI in headless mode,
# which DOES read `~/.claude.json` and therefore loads the MCP correctly.
#
# Schedule: launchd plist com.ibitlabs.moltbook-brand-builder fires every 4h
# at 02:00, 06:00, 10:00, 14:00, 18:00, 22:00 LOCAL time.
#
# Logs: ~/ibitlabs/logs/moltbook-brand-builder/<YYYYMMDD-HHMMSS>.log
#
# To run manually for testing:
#   ~/ibitlabs/scripts/run_moltbook_brand_builder.sh
#
# Architecture history:
#   - Until 2026-04-26: ran via Cowork scheduled-tasks (taskId moltbook-brand-builder).
#     Cowork sandbox could not load brand-publishers (local stdio MCPs aren't
#     supported in Cowork session config — only remote MCPs). Every cron tick
#     produced a BLOCKED report. Moved to launchd 2026-04-26.

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/moltbook-brand-builder"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
# 2026-05-10: Pointed at canonical SKILL.md (per Notion battle room
# 34b3c821-a4aa-8170-91b3-d38f223e1363 + matches `--add-dir` below).
# Previous path was the 04-27 stub at ~/.claude/scheduled-tasks/.../SKILL.md
# which lacked the 04-30 funnel pivot, 05-01 tone-tuning, and 05-05 audits —
# agent was operating on stale rules for 13+ days. Audit on 2026-05-10
# confirmed 0/20 recent posts hit A/B/C trading-funnel paths.
SKILL_FILE="$HOME/Documents/Claude/Scheduled/moltbook-brand-builder/SKILL.md"

mkdir -p "$LOG_DIR"

{
  echo "=== moltbook-brand-builder run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  cwd: $(pwd)"
  echo "claude: $(/opt/homebrew/bin/claude --version 2>/dev/null)"
  echo "skill source: $SKILL_FILE"
  echo "---"

  if [[ ! -f "$SKILL_FILE" ]]; then
    echo "FATAL: skill file not found at $SKILL_FILE"
    exit 1
  fi

  # Pass the cron-prompt SKILL.md as the prompt body via stdin, prepended
  # with an explicit unattended-mode preamble. Without the preamble Sonnet's
  # default behavior is to draft the post and then PAUSE asking for human
  # approval before invoking publish_moltbook — fine for interactive use,
  # broken for cron. The preamble tells the agent the gates already
  # constitute the approval and to publish directly when they pass.
  #
  # (Positional `-p "$(cat ...)"` fails because the SKILL.md frontmatter
  # starts with `---` which the CLI parses as a flag, hence stdin pipe.)
  PREAMBLE="UNATTENDED CRON RUN — no human is watching. This is a launchd-driven
execution of the moltbook-brand-builder skill at the scheduled 4h tick.
Approval to publish has already been given by the operator at SKILL.md commit
time. Do NOT pause to ask 'approve this draft?' — the SKILL.md Step-0
contradiction check, title validator, Polanyi 5-rule pre-publish checklist,
co-founder voice check, reader-test, Hard bans list, and Twitter dedup ARE
the approval gates. If a draft passes all of them, call publish_moltbook /
publish_telegram / publish_tweet directly without intermediate confirmation.
If a draft fails a gate, fix it and re-run the gates — do not surface the
failure for human review, just rewrite per Step 4/5 fall-through rules.

If at the end of the run you have not invoked the publish tools at least
once, that is a failure mode — the SKILL.md mandates publish-on-every-run
since 2026-04-26 (skip-gate removed). Either you missed a step or you are
incorrectly waiting for approval. Re-read the cadence section.

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
