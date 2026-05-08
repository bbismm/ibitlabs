#!/bin/zsh
#
# moltbook-archive — daily incremental archive of @ibitlabs_agent posts + comments.
#
# Schedule: launchd plist com.ibitlabs.moltbook-archive fires daily at 04:00
# LOCAL time (chosen to avoid the 02:00 brand-builder window). Archive is
# idempotent — already-stored posts are skipped, only new ones + comment
# refreshes happen each run.
#
# Logs: ~/ibitlabs/logs/moltbook-archive/<YYYYMMDD-HHMMSS>.log
# Data: ~/ibitlabs/data/moltbook_archive/<post_id>.json (one per post)
#       ~/ibitlabs/data/moltbook_archive/_index.json (summary)
#
# To run manually:
#   ~/ibitlabs/scripts/run_moltbook_archive.sh
#
# Created 2026-04-28 — protects against future loss of @ibitlabs_agent
# discussion threads (Moltbook profile cap is ~10 recent posts; older posts
# fall out of API view and we lose the comment frames that fed our
# contributor ledger).

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/moltbook-archive"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"

mkdir -p "$LOG_DIR"

{
  echo "=== moltbook-archive run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)"
  echo "---"
  /usr/bin/python3 "$HOME/ibitlabs/scripts/moltbook_archive.py"
  ARCHIVE_STATUS=$?
  echo ""
  echo "--- contributors_sync ---"
  /usr/bin/python3 "$HOME/ibitlabs/scripts/contributors_sync.py"
  SYNC_STATUS=$?
  echo ""
  echo "---"
  echo "=== archive exit: $ARCHIVE_STATUS  sync exit: $SYNC_STATUS ==="
  if [[ $ARCHIVE_STATUS -ne 0 ]]; then exit $ARCHIVE_STATUS; fi
  exit $SYNC_STATUS
} 2>&1 | tee -a "$LOG"
