#!/bin/zsh
#
# days-twitter-replay — launchd-driven runner
#
# 4×/day backfill of /days serial chronicle entries to Twitter @BonnyOuyang.
# Reads ~/ibitlabs/web/public/data/days_broadcast_queue.json, posts the next
# unposted Day, updates the queue. One Day per run, no burst. Twitter
# exception (per feedback_social_paused.md, days backfill is a recorded
# exception alongside saga-daily).
#
# Schedule: launchd plist com.ibitlabs.days-twitter-replay fires at 10:00,
# 14:00, 18:00, 22:00 LOCAL time daily. Matches the prior scheduled-tasks
# cron `0 10,14,18,22 * * *`.
#
# Logs: ~/ibitlabs/logs/days-twitter-replay/<YYYYMMDD-HHMMSS>.log
#
# Pure script execution — does NOT use claude CLI. The python script
# `days_broadcast.py --replay-next` does all the work and is idempotent
# (skips if queue empty, returns "queue_empty").
#
# Migrated to launchd 2026-04-28.

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/days-twitter-replay"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"

mkdir -p "$LOG_DIR"

{
  echo "=== days-twitter-replay run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  /usr/bin/python3 "$HOME/ibitlabs/scripts/days_broadcast.py" --replay-next
  STATUS=$?
  echo ""
  echo "=== exit $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
