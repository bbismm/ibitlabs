#!/bin/zsh
#
# edge-halflife — daily decay snapshot for the harness's 4th rollback layer.
#
# Runs the EdgeHalflifeMonitor across baseline (v5.1 live trade_log) + every
# proposal yaml, writes a dated JSON snapshot, and pushes ntfy ONLY when at
# least one target is `degrading` or `decayed`. Silent on all-healthy.
#
# Why silent-on-healthy: a daily healthy=healthy=healthy push is noise; the
# value here is (a) accumulating a backlog of snapshots so the operator can
# scroll back when something does flip, and (b) one real push when it does.
#
# Schedule: launchd plist com.ibitlabs.edge-halflife fires daily at 09:05 LOCAL.
# Snapshots: ~/ibitlabs/logs/edge-halflife/<YYYY-MM-DD>.json
# Run log:   ~/ibitlabs/logs/edge-halflife/<TS>.log
#
# To run manually:
#   ~/ibitlabs/scripts/run_edge_halflife.sh

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/edge-halflife"
TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
DATE_LOCAL="$(date +%Y-%m-%d)"
SNAPSHOT="$LOG_DIR/${DATE_LOCAL}.json"
LOG="$LOG_DIR/$TS_UTC.log"
NTFY_TOPIC=sol-sniper-bonny
CLI="$HOME/ibitlabs/harness/bin/edge_halflife.py"

mkdir -p "$LOG_DIR"

{
  echo "=== edge-halflife run @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "snapshot: $SNAPSHOT"
  echo "---"

  if [[ ! -f "$CLI" ]]; then
    echo "FATAL: CLI not found at $CLI"
    exit 1
  fi

  if ! python3 "$CLI" --json > "$SNAPSHOT.tmp"; then
    echo "FATAL: edge_halflife CLI failed"
    rm -f "$SNAPSHOT.tmp"
    exit 1
  fi
  mv "$SNAPSHOT.tmp" "$SNAPSHOT"

  # Build a one-line summary + decide whether to push.
  # Uses python over the same JSON to keep this script jq-free.
  PUSH_BODY=$(python3 - "$SNAPSHOT" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
alerts = [d for d in data if d["status"] in ("degrading", "decayed")]
lines = []
for d in data:
    w30 = next((w for w in d["windows"] if w["window_days"] == 30), None)
    n = w30["n_paired"] if w30 else 0
    hr = w30["hit_rate"] if w30 else None
    pf = w30["profit_factor"] if w30 else None
    hr_s = "n/a" if hr is None else f"{hr*100:.1f}%"
    pf_s = "n/a" if pf is None else ("inf" if pf == float("inf") else f"{pf:.2f}")
    lines.append(f"[{d['status']}] {d['target_id']} 30d n={n} HR={hr_s} PF={pf_s}")
if alerts:
    print("EDGE-HALFLIFE alert")
    for line in lines:
        print(line)
else:
    # Empty stdout -> wrapper skips the push.
    pass
PY
)

  if [[ -n "$PUSH_BODY" ]]; then
    echo "--- ntfy push ---"
    echo "$PUSH_BODY"
    curl -s -H "Title: edge-halflife: decay signal" -H "Priority: high" \
      -d "$PUSH_BODY" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null
    PUSH_RC=$?
    echo "ntfy_rc: $PUSH_RC"
  else
    echo "all healthy or insufficient_data; no push."
  fi

  # Prune snapshot logs older than 180d (keep ~6 months of decay history).
  find "$LOG_DIR" -name "*.json" -mtime +180 -delete 2>/dev/null || true
  find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true

  echo "=== done @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
} 2>&1 | tee -a "$LOG"
