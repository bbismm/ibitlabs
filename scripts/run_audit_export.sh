#!/bin/zsh
#
# run_audit_export — wraps audit_export.py, commits & pushes audit_export/
# only if files actually changed. Run daily via launchd.
#
# Logs: ~/ibitlabs/logs/audit-export/<YYYYMMDD-HHMMSS>.log
#
# Manual test:
#   ~/ibitlabs/scripts/run_audit_export.sh
#   ~/ibitlabs/scripts/run_audit_export.sh --dry-run   # build, show diff, no commit
#
# Created 2026-05-08 to wire the receipt-engine's GitHub distribution arm.

set -u
set -o pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

REPO="$HOME/ibitlabs"
LOG_DIR="$HOME/ibitlabs/logs/audit-export"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"
mkdir -p "$LOG_DIR"

{
  echo "=== audit-export run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)  dry_run: $DRY_RUN"
  echo "---"

  cd "$REPO" || { echo "FATAL: cd $REPO failed"; exit 1; }

  # Run the export
  python3 scripts/audit_export.py --summary
  RC=$?
  if [[ $RC -ne 0 ]]; then
    echo "FATAL: audit_export.py exited $RC"
    exit $RC
  fi

  # Check if anything changed
  if git diff --quiet audit_export/ && [[ -z "$(git status --porcelain audit_export/)" ]]; then
    echo ""
    echo "no changes in audit_export/ — skipping commit"
    exit 0
  fi

  echo ""
  echo "--- changes detected ---"
  git status --porcelain audit_export/

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "DRY RUN — no commit, no push"
    exit 0
  fi

  # Commit
  git add audit_export/
  COMMIT_DATE="$(date -u +%Y-%m-%d)"
  git commit -m "audit_export: refresh receipts $COMMIT_DATE

Auto-commit by run_audit_export.sh launchd job.
Source: ~/ibitlabs/scripts/audit_export.py
" || { echo "git commit failed"; exit 1; }

  # Push
  if ! git push origin main; then
    echo "WARN: git push failed (network? auth?). Commit landed locally; will retry next cycle."
    exit 0  # non-fatal — local commit is durable
  fi

  echo "✓ pushed audit_export refresh to origin/main"
} 2>&1 | tee -a "$LOG"
