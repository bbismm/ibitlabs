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

  # Capture monitors JSON to a temp file (avoids shell + heredoc double-escape
  # that mangled `\"stub\"`-style escaped quotes in receipt text -- 2026-05-14).
  MONITORS_FILE="$(mktemp -t harness_status_monitors.XXXXXX.json)"
  FREEZE_FILE="$(mktemp -t harness_status_freeze.XXXXXX.json)"
  trap 'rm -f "$MONITORS_FILE" "$FREEZE_FILE"' EXIT
  if ! python3 "$HARNESS/bin/rollback_status.py" --json >"$MONITORS_FILE" 2>>"$LOG"; then
    echo "FATAL: rollback_status.py exited non-zero (exit codes 1/2 are status,"
    echo "       not errors, but produced no JSON or invalid JSON)."
  fi
  if [[ ! -s "$MONITORS_FILE" ]]; then
    echo "FATAL: rollback_status.py produced empty output"
    exit 2
  fi

  # Capture schema-freeze state (operator-level governance, harness/docs/why.md §O1).
  # freeze_status exits: 0=unfrozen, 1=frozen, 2=error. Treat 0/1 as success.
  FREEZE_EXIT=0
  python3 "$HARNESS/bin/freeze_status.py" --json >"$FREEZE_FILE" 2>>"$LOG" || FREEZE_EXIT=$?
  if [[ "$FREEZE_EXIT" != "0" && "$FREEZE_EXIT" != "1" ]]; then
    echo "warning: freeze_status.py exit=$FREEZE_EXIT, recording schema_freeze as null"
    echo "null" > "$FREEZE_FILE"
  fi

  # Enrich + summarize via Python reading the temp files (one tool, no jq dep)
  python3 - "$MONITORS_FILE" "$GENERATED_AT" "$GIT_HEAD" "$GIT_BRANCH" "$FREEZE_FILE" <<'PYEOF' >"$TARGET"
import json, sys
monitors_file, generated_at, git_head, git_branch, freeze_file = sys.argv[1:6]
with open(monitors_file) as f:
    monitors = json.load(f)
with open(freeze_file) as f:
    schema_freeze = json.load(f)
counts = {"healthy": 0, "degraded": 0, "alarm": 0, "unknown": 0}
by_layer = {"realtime": 0, "observation": 0, "decay": 0, "proposal": 0}
for m in monitors:
    counts[m.get("status", "unknown")] = counts.get(m.get("status", "unknown"), 0) + 1
    by_layer[m.get("layer", "?")] = by_layer.get(m.get("layer", "?"), 0) + 1
out = {
    "generated_at": generated_at,
    "git_head": git_head,
    "git_branch": git_branch,
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
    "schema_freeze": schema_freeze,
    "monitors": monitors,
    "source": {
        "generator": "scripts/run_harness_status.sh",
        "underlying_cli": "harness/bin/rollback_status.py --json + harness/bin/freeze_status.py --json",
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
