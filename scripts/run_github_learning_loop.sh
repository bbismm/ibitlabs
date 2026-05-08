#!/bin/zsh
#
# github-learning-loop — launchd-driven runner.
#
# Polls a fixed watchlist of public trading repos (hummingbot, freqtrade,
# ccxt) for new merged PRs / closed issues that match our hybrid_v5.1
# relevance keywords. Writes a digest under ~/ibitlabs/logs/github-learning-loop/.
#
# Strict mode: ingestion only. A GitHub author becomes a public contributor
# at ibitlabs.com/contributors ONLY when their idea is adopted as a named
# shadow rule in sol_sniper_executor.py (proposed_by/proposed_source/
# proposed_in_url on the shadow JSONL's first line). contributors_sync.py
# does the rest. This script never writes the ledger.
#
# Schedule: launchd plist com.ibitlabs.github-learning-loop fires at
# 08:00 and 20:00 LOCAL time (offset from moltbook-learning-loop's 05/17).
#
# Manual run:
#   ~/ibitlabs/scripts/run_github_learning_loop.sh
#   ~/ibitlabs/scripts/run_github_learning_loop.sh --backfill   # one-shot 30d sweep

set -u
set -o pipefail

# Same ntfy topic as ghost-watchdog + reconcile so all bot-related pushes hit
# one phone subscription. Push fires only on CRITICAL_PATTERN matches; first
# encounter is recorded in state/github_learning_critical_pushed.json so we
# never re-push the same PR/issue.
export NTFY_TOPIC="${NTFY_TOPIC:-sol-sniper-bonny}"

LOG_DIR="$HOME/ibitlabs/logs/github-learning-loop"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/launchd-runs/$TS.log"
PY="$HOME/ibitlabs/scripts/github_learning_loop.py"

mkdir -p "$LOG_DIR/launchd-runs"

{
  echo "=== github-learning-loop run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)"
  echo "gh: $(/opt/homebrew/bin/gh --version 2>/dev/null | head -1)"
  echo "---"
  /usr/bin/env python3 "$PY" "$@"
  STATUS=$?
  echo "---"
  echo "=== exit status: $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
