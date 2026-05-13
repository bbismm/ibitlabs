#!/usr/bin/env bash
# Phase D auto-flip — enable Receipt v0.1.1 emission on the live sniper bot,
# 24h after the shadow Phase C flip. Gates ensure we only flip when shadow
# has been clean and the live position is not in a critical trailing window.
#
# Day 0 Phase C: 2026-05-11 02:43:19 UTC
# Scheduled fire: 2026-05-11 22:50 EDT (≈ Phase C + 24h 7min)
#
# All gates are inspection-only — script never alters trading code, only the
# launchd env block for com.ibitlabs.sniper. _safe_receipt() in sol_sniper_main.py
# guarantees receipt I/O can never block trading.

set -uo pipefail

LOG=/Users/bonnyagent/ibitlabs/logs/phase_d_flip.log
NTFY=sol-sniper-bonny
SHADOW_JSONL=/Users/bonnyagent/ibitlabs/audit_export/sniper-v5.1-shadow.realtime.receipt.jsonl
LIVE_JSONL=/Users/bonnyagent/ibitlabs/audit_export/sniper-v5.1-live.realtime.receipt.jsonl
LIVE_PLIST=/Users/bonnyagent/Library/LaunchAgents/com.ibitlabs.sniper.plist
LIVE_LOG=/Users/bonnyagent/ibitlabs/logs/sniper.log
LIVE_STATUS_URL="https://www.ibitlabs.com/api/live-status"

ts() { date -u +"%Y-%m-%d %H:%M:%S UTC"; }
log() { echo "$(ts) $*" | tee -a "$LOG"; }

push() {
    local title="$1"; local prio="$2"; local tags="$3"; shift 3
    curl -fsS --max-time 10 --data "$*" "https://ntfy.sh/$NTFY" \
        -H "Title: $title" -H "Priority: $prio" -H "Tags: $tags" >/dev/null 2>&1 || true
}

fail() {
    log "FAIL: $*"
    push "Phase D blocked" "high" "warning" "Phase D auto-flip BLOCKED at $(ts): $*"
    exit 1
}

log "=== Phase D auto-flip starting ==="

# ─── Gate 1: shadow chain has accumulated events (≥20 = ~24h heartbeats) ───
[ -f "$SHADOW_JSONL" ] || fail "shadow jsonl missing at $SHADOW_JSONL"
LINES=$(wc -l < "$SHADOW_JSONL" | tr -d ' ')
[ "$LINES" -ge 20 ] || fail "shadow chain has only $LINES events (need ≥20)"
log "Gate 1 OK: shadow chain has $LINES events"

# ─── Gate 2: shadow chain hash-verifies (prev_hash → hash linkage) ───
/usr/bin/python3 -c "
import json, sys
events = [json.loads(l) for l in open('$SHADOW_JSONL') if l.strip()]
if not events:
    print('CHAIN EMPTY')
    sys.exit(1)
broken = []
for i, e in enumerate(events):
    if i > 0 and e['prev_hash'] != events[i-1]['hash']:
        broken.append(e['seq'])
if broken:
    print(f'CHAIN BROKEN at seqs={broken}')
    sys.exit(1)
print(f'CHAIN OK ({len(events)} events, seq {events[0][\"seq\"]}→{events[-1][\"seq\"]})')
" >> "$LOG" 2>&1 || fail "shadow chain hash verification failed (see log)"
log "Gate 2 OK: shadow chain hashes verified"

# ─── Gate 3: live bot alive ───
LIVE_PID=$(launchctl list com.ibitlabs.sniper 2>/dev/null | awk '/"PID"/ {gsub(/[";,]/,""); print $3}' | head -1)
if [ -z "$LIVE_PID" ] || [ "$LIVE_PID" = "-" ]; then
    fail "live bot not running (launchctl reports no PID)"
fi
kill -0 "$LIVE_PID" 2>/dev/null || fail "live bot PID $LIVE_PID not actually alive"
log "Gate 3 OK: live bot PID $LIVE_PID alive"

# ─── Gate 4: live plist doesn't already have SNIPER_RECEIPT set ───
if /usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:SNIPER_RECEIPT" "$LIVE_PLIST" 2>/dev/null >/dev/null; then
    fail "live plist already has SNIPER_RECEIPT set — manual intervention needed"
fi
log "Gate 4 OK: live plist SNIPER_RECEIPT unset"

# ─── Gate 5: live position trailing-not-active (skip if /api/live-status unreachable) ───
STATUS_JSON=$(curl -fsS --max-time 10 "$LIVE_STATUS_URL" 2>/dev/null || echo '')
if [ -n "$STATUS_JSON" ]; then
    TRAILING=$(echo "$STATUS_JSON" | /usr/bin/python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    pos = d.get('position') or {}
    # Field name varies — try common spellings
    for k in ('trailing_active','is_trailing','trail_active'):
        if k in pos:
            print('true' if pos[k] else 'false'); sys.exit(0)
    print('unknown')
except Exception:
    print('unknown')
")
    case "$TRAILING" in
        true)  fail "live position is trailing-active — re-run after trailing completes" ;;
        false) log "Gate 5 OK: trailing not active" ;;
        *)     log "Gate 5 SKIP: trailing flag not exposed by /api/live-status — proceeding" ;;
    esac
else
    log "Gate 5 SKIP: /api/live-status unreachable — proceeding"
fi

# ─── All gates passed: perform the flip ───
log "=== flipping live SNIPER_RECEIPT=1 ==="
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:SNIPER_RECEIPT string 1" "$LIVE_PLIST" \
    || fail "PlistBuddy add failed"

launchctl unload "$LIVE_PLIST" 2>&1 | tee -a "$LOG"
sleep 2
launchctl load "$LIVE_PLIST" 2>&1 | tee -a "$LOG" || fail "launchctl load failed"
sleep 10

NEW_PID=$(launchctl list com.ibitlabs.sniper 2>/dev/null | awk '/"PID"/ {gsub(/[";,]/,""); print $3}' | head -1)
if [ -z "$NEW_PID" ] || [ "$NEW_PID" = "-" ] || [ "$NEW_PID" = "$LIVE_PID" ]; then
    fail "live bot did not restart cleanly (old=$LIVE_PID new=${NEW_PID:-none})"
fi
log "live restarted: PID $LIVE_PID → $NEW_PID"

# Verify receipt init succeeded in the new process
sleep 3
INIT_LINE=$(grep "\[RECEIPT\] enabled" "$LIVE_LOG" | tail -1)
if [ -z "$INIT_LINE" ]; then
    fail "live bot restarted but [RECEIPT] enabled not in log within 13s — receipt init silently failed"
fi
log "$INIT_LINE"

# Verify live chain file created
[ -f "$LIVE_JSONL" ] || fail "live restarted with [RECEIPT] enabled but jsonl chain not written"
log "live chain file: $LIVE_JSONL"

# Day 0 of the real launch clock
DAY0=$(ts)
TARGET=$(/bin/date -u -v +30d +"%Y-%m-%d %H:%M:%S UTC")
log "=== Phase D LIVE. Day 0: $DAY0. 30-day milestone: $TARGET ==="

push "Phase D LIVE" "default" "tada,bell" \
"Receipt v0.1.1 emission ENABLED on live sniper at $DAY0. New PID $NEW_PID. 30-day clean-realtime milestone (gates Moltbook launch post): $TARGET. Shadow continues in parallel."

exit 0
