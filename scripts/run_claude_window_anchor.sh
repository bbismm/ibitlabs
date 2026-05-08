#!/bin/zsh
#
# claude-window-anchor — launchd-driven runner
#
# Fires a minimal `claude -p` call at 01:55 EDT to anchor the Claude Code
# 5h usage window to start at ~01:55, so the dense cron block at
# 02:00/02:30/03:00 (moltbook-learning-loop, moltbook-trading-learn,
# moltbook-trading-minds) lands inside a single shared 5h budget.
#
# Cost: ~$0.001 per fire (1-token output).
#
# Schedule: launchd plist com.ibitlabs.claude-window-anchor at 01:55 LOCAL.
#
# Logs: ~/ibitlabs/logs/claude-window-anchor/launchd.{stdout,stderr}.log

set -u

LOG_DIR="$HOME/ibitlabs/logs/claude-window-anchor"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/launchd.stdout.log"

{
  echo "=== claude-window-anchor run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host: $(hostname)  user: $(whoami)"

  echo "ok" | /opt/homebrew/bin/claude \
    -p \
    --dangerously-skip-permissions \
    --max-budget-usd 0.05 \
    --model sonnet

  STATUS=$?
  echo ""
  echo "=== claude exit status: $STATUS ==="
  exit $STATUS
} 2>&1 | tee -a "$LOG"
