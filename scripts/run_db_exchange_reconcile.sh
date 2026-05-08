#!/bin/zsh
# run_db_exchange_reconcile.sh
# Thin wrapper around db_vs_exchange_reconcile.py, designed for a 15-min
# LaunchAgent cadence. Read-only: passes NO --apply flag, ever.
#
# Purpose: detect DB ↔ Coinbase state desync within 15 minutes instead of
# the daily-only cadence used by run_reconcile.sh (09:10 local).
#
# Motivation: 2026-04-19 #325 ghost position sat undetected for 5.5h between
# actual fill (18:15 UTC) and manual discovery (23:42 UTC). Daily reconcile
# would have caught it on 2026-04-20 09:10 — 15 hours too late.
#
# Exit code behavior (from db_vs_exchange_reconcile.py):
#   0 — clean, no push
#   1 — drift detected, push ntfy alert
#   2 — script error, push ntfy alert (distinct title)
#
# Log: ~/ibitlabs/logs/db_exchange_reconcile_frequent.log (appended, one
# run per invocation, prefixed with timestamp).
#
# Safe to run manually: ./scripts/run_db_exchange_reconcile.sh
# Safe to re-run: stateless, each run independent.

set -u  # unset vars are errors; DON'T set -e because we need to capture rc

# Load Coinbase API credentials from .env if not already in environment.
# Scheduled tasks (launchd) do not inherit the shell environment, so CB_API_KEY
# and CB_API_SECRET are empty unless we load them explicitly here.
# (This block is copied verbatim from scripts/run_reconcile.sh to stay in sync.)
ENV_FILE=/Users/bonnyagent/ibitlabs/.env
if [ -f "$ENV_FILE" ]; then
    _cb_key=$(grep -m1 '^CB_API_KEY=' "$ENV_FILE" | cut -d= -f2-)
    _cb_secret=$(grep -m1 '^CB_API_SECRET=' "$ENV_FILE" | cut -d= -f2-)
    export CB_API_KEY="${CB_API_KEY:-$_cb_key}"
    export CB_API_SECRET="${CB_API_SECRET:-$_cb_secret}"
fi

LOG=/Users/bonnyagent/ibitlabs/logs/db_exchange_reconcile_frequent.log
PY=/usr/bin/python3
NTFY_TOPIC=sol-sniper-bonny

echo "" >> "$LOG"
echo "==== db_vs_exchange reconcile (15min) @ $(date '+%Y-%m-%d %H:%M:%S') ====" >> "$LOG"

"$PY" /Users/bonnyagent/ibitlabs/scripts/db_vs_exchange_reconcile.py --days 2 \
    >> "$LOG" 2>&1
RC=$?

echo "exit_code=$RC" >> "$LOG"

if [ "$RC" -eq 1 ]; then
    curl -s \
        -H "Title: DB↔Exchange DRIFT (15min probe)" \
        -H "Priority: high" \
        -H "Tags: warning,rotating_light" \
        -d "Trade log diverged from Coinbase fills. See $LOG. Human review required before any --apply." \
        "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1
elif [ "$RC" -eq 2 ]; then
    curl -s \
        -H "Title: DB↔Exchange PROBE ERROR (15min)" \
        -H "Priority: default" \
        -H "Tags: x" \
        -d "db_vs_exchange_reconcile.py exited 2. Coinbase API may be down. See $LOG" \
        "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1
fi

exit $RC
