#!/bin/bash
# run_export_mcp_data.sh
# Regenerates /data/recent_trades.json and /data/rule_status.json,
# then git-commits + Cloudflare-deploys the changes.
# Runs after sniper morning-check (09:10) and evening-check (21:10).
# Fires at 09:15 and 21:15 via com.ibitlabs.export-mcp-data launchd plist.

set -euo pipefail

REPO="/Users/bonnyagent/ibitlabs"
LOG_DIR="$REPO/logs/export-mcp-data"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d_%H%M%S).log"

exec >> "$LOG" 2>&1
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] export_mcp_data starting"

cd "$REPO"

# 1. Generate the JSON files
/usr/bin/python3 scripts/export_mcp_data.py

# 2. Stage only the two data files (never stage DB, logs, or secrets)
git add web/public/data/recent_trades.json web/public/data/rule_status.json

# 3. Commit only if there are staged changes
if git diff --cached --quiet; then
  echo "[export_mcp_data] nothing changed, skipping commit"
else
  git commit -m "chore: refresh MCP data exports $(date -u +%Y-%m-%dT%H:%M:%SZ)

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
  echo "[export_mcp_data] committed"
fi

# 4. Deploy to Cloudflare Pages
cd web
/opt/homebrew/bin/wrangler pages deploy public \
  --project-name=bibsus \
  --branch=main \
  --commit-dirty=true \
  2>&1 | tail -5

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] export_mcp_data done"
