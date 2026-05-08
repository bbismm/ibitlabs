#!/bin/zsh
#
# overnight-cron-check — launchd-driven runner
#
# Fires at 05:00 EDT daily, after the dense night window
# (01:55 anchor → 02:00 learning-loop → 02:30 trading-learn → 03:00 trading-minds).
# Pure shell, no Claude calls. Writes a one-pane status report so the
# operator can `cat ~/ibitlabs/logs/overnight-cron-check.log` at breakfast.
#
# Schedule: launchd plist com.ibitlabs.overnight-cron-check at 05:00 LOCAL.
#
# Output: ~/ibitlabs/logs/overnight-cron-check.log (overwritten each run).

set -u

REPORT="$HOME/ibitlabs/logs/overnight-cron-check.log"
TODAY=$(date +%Y-%m-%d)

JOBS=(
  com.ibitlabs.claude-window-anchor
  com.ibitlabs.moltbook-learning-loop
  com.ibitlabs.moltbook-trading-learn
  com.ibitlabs.moltbook-trading-minds
  com.ibitlabs.moltbook-reply-check
)

# stdout log paths (resolve via plist, not assumption)
log_path_for() {
  /usr/libexec/PlistBuddy -c "Print :StandardOutPath" \
    "$HOME/Library/LaunchAgents/$1.plist" 2>/dev/null
}

{
  echo "================================================================"
  echo "  Overnight cron check — $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "================================================================"
  echo

  # ---- 1) launchctl exit codes ----
  echo "--- launchctl last-exit-code ---"
  for job in $JOBS; do
    line=$(launchctl list | awk -v j="$job" '$3 == j {print}')
    if [ -z "$line" ]; then
      echo "  $job: NOT LOADED"
    else
      pid=$(echo "$line" | awk '{print $1}')
      exit_code=$(echo "$line" | awk '{print $2}')
      tag=$([ "$exit_code" = "0" ] && echo "OK" || echo "FAIL($exit_code)")
      echo "  $job: $tag  (pid=$pid)"
    fi
  done
  echo

  # ---- 2) last run timestamp + status from each stdout log ----
  echo "--- last run per job (from stdout log) ---"
  for job in $JOBS; do
    log=$(log_path_for "$job")
    echo "  [$job]"
    if [ -z "$log" ] || [ ! -f "$log" ]; then
      echo "    (no stdout log at: $log)"
      continue
    fi
    last_run=$(grep -E "run @ " "$log" | tail -1)
    last_status=$(grep -E "claude exit status" "$log" | tail -1)
    last_budget=$(grep -E "Exceeded USD budget" "$log" | tail -1)
    echo "    last run:    ${last_run:-(none)}"
    echo "    last status: ${last_status:-(none)}"
    if [ -n "$last_budget" ]; then
      echo "    last budget: $last_budget"
    fi
  done
  echo

  # ---- 3) today's budget-overflow count ----
  echo "--- today's 'Exceeded USD budget' count (per job) ---"
  for job in $JOBS; do
    log=$(log_path_for "$job")
    [ -z "$log" ] || [ ! -f "$log" ] && continue
    # count budget-exceeded markers since today's date appeared in a 'run @' line
    today_section=$(awk -v d="$TODAY" '
      /run @ / { in_today = ($0 ~ d) }
      in_today { print }
    ' "$log")
    n=$(echo "$today_section" | grep -c "Exceeded USD budget")
    runs=$(echo "$today_section" | grep -c "run @ ")
    echo "  $job: $n/$runs runs hit budget today"
  done
  echo

  # ---- 4) anchor verification: did 01:55 fire and claim window? ----
  echo "--- anchor verification ---"
  anchor_log=$(log_path_for com.ibitlabs.claude-window-anchor)
  if [ -n "$anchor_log" ] && [ -f "$anchor_log" ]; then
    anchor_today=$(grep "run @ ${TODAY}" "$anchor_log" | tail -1)
    if [ -n "$anchor_today" ]; then
      echo "  anchor fired today: $anchor_today"
    else
      echo "  WARN: no anchor fire found for $TODAY"
    fi
  else
    echo "  WARN: no anchor stdout log"
  fi
  echo

  echo "================================================================"
  echo "  end of report"
  echo "================================================================"
} > "$REPORT" 2>&1

exit 0
