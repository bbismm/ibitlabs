#!/bin/zsh
#
# run_harness_status.sh — refresh the public harness status snapshot.
#
# Wraps `harness/bin/rollback_status.py --json` into an enriched JSON that
# includes generation timestamp + git HEAD SHA + counts summary, then writes
# to web/public/data/harness_status.json (served at
# https://ibitlabs.com/data/harness_status.json after Cloudflare deploy).
#
# This is the "live artifact" wiring — turns harness from a snapshot README
# into something an auditor can curl. Persona-4 fix per harness Notion debrief
# (2026-05-12).
#
# Manual usage:
#   ~/ibitlabs/scripts/run_harness_status.sh
#
# To install as a daily launchd job (later):
#   plist com.ibitlabs.harness-status, fires daily ~04:25 local (5 min before
#   /lab deploy at 04:30 so the JSON is current when /lab refreshes).
#
# Logs: ~/ibitlabs/logs/harness-status/<TS>.log

set -u
set -o pipefail

REPO="$HOME/ibitlabs"
HARNESS="$REPO/harness"
TARGET="$REPO/web/public/data/harness_status.json"
LOG_DIR="$HOME/ibitlabs/logs/harness-status"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"

mkdir -p "$LOG_DIR" "$(dirname "$TARGET")"

{
  echo "=== run_harness_status @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  GIT_HEAD="$(cd "$REPO" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  GIT_BRANCH="$(cd "$REPO" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"

  # Capture monitors JSON
  MONITORS_JSON="$(python3 "$HARNESS/bin/rollback_status.py" --json 2>>"$LOG")"
  if [[ -z "$MONITORS_JSON" ]]; then
    echo "FATAL: rollback_status.py produced empty output"
    exit 2
  fi

  # Enrich + summarize via inline Python (one tool, no jq dep)
  python3 - <<PYEOF >"$TARGET"
import json, sys
monitors = json.loads('''$MONITORS_JSON''')
counts = {"healthy": 0, "degraded": 0, "alarm": 0, "unknown": 0}
by_layer = {"realtime": 0, "observation": 0, "proposal": 0}
for m in monitors:
    counts[m.get("status", "unknown")] = counts.get(m.get("status", "unknown"), 0) + 1
    by_layer[m.get("layer", "?")] = by_layer.get(m.get("layer", "?"), 0) + 1
out = {
    "generated_at": "$GENERATED_AT",
    "git_head": "$GIT_HEAD",
    "git_branch": "$GIT_BRANCH",
    "summary": {
        "total_monitors": len(monitors),
        "by_status": counts,
        "by_layer": by_layer,
        "overall_status": (
            "alarm" if counts["alarm"] else
            "degraded" if counts["degraded"] else
            "unknown" if counts["unknown"] else
            "healthy"
        ),
    },
    "monitors": monitors,
    "source": {
        "generator": "scripts/run_harness_status.sh",
        "underlying_cli": "harness/bin/rollback_status.py --json",
        "repo": "https://github.com/bbismm/ibitlabs",
        "harness_dir": "https://github.com/bbismm/ibitlabs/tree/main/harness",
    },
}
json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
sys.stdout.write("\n")
PYEOF

  STATUS=$?
  if [[ $STATUS -ne 0 ]]; then
    echo "FATAL: JSON enrichment failed, status=$STATUS"
    exit $STATUS
  fi

  SIZE=$(wc -c <"$TARGET" | tr -d ' ')
  echo "wrote $TARGET ($SIZE bytes)"
  echo "preview:"
  head -20 "$TARGET"
  echo ""
  echo "=== done ==="
  exit 0
} 2>&1 | tee -a "$LOG"
