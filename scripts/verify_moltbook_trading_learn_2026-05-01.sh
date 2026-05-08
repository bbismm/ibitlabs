#!/bin/zsh
#
# verify_moltbook_trading_learn_2026-05-01.sh — one-shot local verification
# of the launchd com.ibitlabs.moltbook-trading-learn migration's first fire.
#
# Fires once at 2026-05-01 08:30 EDT via launchd plist
# com.ibitlabs.moltbook-trading-learn-verify-2026-05-01, then self-unloads.
#
# Output: ~/ibitlabs/logs/moltbook-trading-learn-verify-2026-05-01.txt
# Push:   ntfy via /Users/bonnyagent/scripts/send_ntfy.sh if available.

set -u

VERIFY_LOG="$HOME/ibitlabs/logs/moltbook-trading-learn-verify-2026-05-01.txt"
TASK_LOG_DIR="$HOME/ibitlabs/logs/moltbook-trading-learn"
LEARNINGS_FILE="$HOME/ibitlabs/docs/moltbook_learnings.md"
CUTOFF_EPOCH=$(date -j -f '%Y-%m-%dT%H:%M:%S' '2026-05-01T07:00:00' +%s 2>/dev/null || echo 0)

mkdir -p "$(dirname "$VERIFY_LOG")"

{
  echo "=== verify @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo

  # Find the newest run log created after the cutoff (08:00 fire window).
  LATEST=$(find "$TASK_LOG_DIR" -name '20260501-*.log' -type f -newer /tmp -print 2>/dev/null | sort | tail -1)
  if [[ -z "$LATEST" ]]; then
    LATEST=$(find "$TASK_LOG_DIR" -name '20260501-*.log' -type f 2>/dev/null | sort | tail -1)
  fi

  if [[ -z "$LATEST" ]]; then
    VERDICT="FAIL"
    ROOT_CAUSE="no log file found at $TASK_LOG_DIR matching 20260501-*.log — launchd never fired"
    NEXT_ACTION="check 'launchctl list | grep moltbook-trading-learn' and inspect launchd.stderr.log"
  else
    echo "latest run log: $LATEST"
    echo "--- log tail (last 30 lines) ---"
    tail -30 "$LATEST"
    echo "---"

    EXIT_LINE=$(grep -E 'claude exit status:' "$LATEST" | tail -1)
    echo "exit line: ${EXIT_LINE:-<missing>}"

    if [[ "$EXIT_LINE" == *"exit status: 0"* ]]; then
      # Check the learnings file for a 2026-05-01 heading near the top.
      if [[ -f "$LEARNINGS_FILE" ]] && head -8 "$LEARNINGS_FILE" | grep -q '## 2026-05-01'; then
        VERDICT="PASS"
        ROOT_CAUSE="(none)"
        NEXT_ACTION="do nothing — first launchd fire produced output"
      else
        VERDICT="PARTIAL"
        ROOT_CAUSE="exit 0 but no '## 2026-05-01' heading prepended to moltbook_learnings.md"
        NEXT_ACTION="inspect log — skill may have run without writing the markdown sync step"
      fi
    else
      VERDICT="FAIL"
      # Look for browser-MCP-style failure markers in the log.
      if grep -qE 'tabs_context_mcp|navigate.*moltbook|browser.*not.*available|MCP.*not.*connected|Claude in Chrome' "$LATEST" 2>/dev/null; then
        ROOT_CAUSE="browser MCP unavailable in headless launchd run (skill step 1)"
        NEXT_ACTION="rewrite SKILL step 1 to use moltbook REST API at https://moltbook.com/api/v1/ instead of browser"
      elif grep -qE 'Exceeded USD budget|max-budget-usd' "$LATEST" 2>/dev/null; then
        ROOT_CAUSE="budget cap hit ($1.50 too low for browser-mediated scan)"
        NEXT_ACTION="raise --max-budget-usd in run_moltbook_trading_learn.sh, or rewrite to API path"
      elif grep -qE '401 Unauthorized|403 Forbidden|Account is no longer' "$LATEST" 2>/dev/null; then
        ROOT_CAUSE="claude CLI auth broken (same failure mode as sniper-evening-check)"
        NEXT_ACTION="re-login claude CLI; check token org membership"
      else
        ROOT_CAUSE="unknown — see log tail above"
        NEXT_ACTION="manual inspection of $LATEST"
      fi
    fi
  fi

  echo
  echo "============ VERDICT ============"
  echo "VERDICT:    $VERDICT"
  echo "ROOT CAUSE: $ROOT_CAUSE"
  echo "NEXT:       $NEXT_ACTION"
  echo "================================="
} 2>&1 | tee "$VERIFY_LOG"

# Push notification if helper is available.
NTFY_HELPER="$HOME/scripts/send_ntfy.sh"
if [[ -x "$NTFY_HELPER" ]]; then
  "$NTFY_HELPER" "moltbook-trading-learn verify: $VERDICT" "$ROOT_CAUSE — see $VERIFY_LOG" 2>/dev/null || true
fi

# Self-unload — one-shot job is done.
launchctl unload -w "$HOME/Library/LaunchAgents/com.ibitlabs.moltbook-trading-learn-verify-2026-05-01.plist" 2>/dev/null || true
