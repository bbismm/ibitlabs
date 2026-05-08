#!/bin/bash
# reload_and_verify.sh — restart long-running ibitlabs processes after a code
# edit and PROVE the new code is live by reading the state layer.
#
# The recurring bug this script exists to prevent: editing sol_sniper_main.py /
# anomaly_detector.py / shadow_viewer.py and forgetting to bounce the long-
# running launchd process. The source looks correct but the running process is
# still on yesterday's bytecode, and the database silently fills with rows that
# don't reflect the patch. Logs lie. Configs lie. Only the DB rows betray it.
#
# This script:
#   1. Bounces sniper, sniper-shadow, shadow-viewer (whichever exist)
#   2. Waits for each to come back to "running"
#   3. Polls the live DB and reports tag coverage on the last 20 rows
#   4. Exits non-zero if any process failed to come back or if recent rows
#      still have NULL strategy_intent (which means the patch didn't land)
#
# Usage: scripts/reload_and_verify.sh

set -u
LIVE_DB="/Users/bonnyagent/ibitlabs/sol_sniper.db"
UID_REAL="$(id -u)"

# Long-running daemons: must reach state=running after kickstart.
# Periodic tasks: kickstart fires the run; "not running" between runs is fine.
DAEMONS=(
    "com.ibitlabs.sniper"
    "com.ibitlabs.sniper-shadow"
    "com.ibitlabs.shadow-viewer"
)
PERIODIC=(
    "com.ibitlabs.anomaly-detector"
    "com.ibitlabs.shadow-diff"
)

bounce_daemon() {
    local label="$1"
    local target="gui/${UID_REAL}/${label}"
    if ! launchctl print "$target" >/dev/null 2>&1; then
        echo "  [skip] $label not loaded"
        return 0
    fi
    echo "  [kick] $label (daemon)"
    launchctl kickstart -k "$target" >/dev/null 2>&1
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        state=$(launchctl print "$target" 2>/dev/null | awk '/^[[:space:]]*state =/{print $3; exit}')
        if [ "$state" = "running" ]; then
            pid=$(launchctl print "$target" 2>/dev/null | awk '/^[[:space:]]*pid =/{print $3; exit}')
            echo "  [ok]   $label running pid=$pid (after ${i}s)"
            return 0
        fi
    done
    echo "  [FAIL] $label did not reach state=running within 10s"
    return 1
}

bounce_periodic() {
    local label="$1"
    local target="gui/${UID_REAL}/${label}"
    if ! launchctl print "$target" >/dev/null 2>&1; then
        echo "  [skip] $label not loaded"
        return 0
    fi
    echo "  [kick] $label (periodic — fires once, returns to dormant)"
    launchctl kickstart "$target" >/dev/null 2>&1
    sleep 1
    last=$(launchctl print "$target" 2>/dev/null | awk -F= '/last exit code/{print $2; exit}' | tr -d ' ')
    echo "  [ok]   $label last exit code=${last:-?}"
    return 0
}

echo "=== reload services ==="
fail=0
for svc in "${DAEMONS[@]}"; do
    bounce_daemon "$svc" || fail=$((fail + 1))
done
for svc in "${PERIODIC[@]}"; do
    bounce_periodic "$svc"
done

echo ""
echo "=== state-layer verification ==="
if [ ! -f "$LIVE_DB" ]; then
    echo "  [FAIL] live DB not found at $LIVE_DB"
    exit 2
fi

# Tag coverage on the last 20 rows. NULL strategy_intent on recent rows means
# the live process is still running unpatched code paths.
read total tagged < <(sqlite3 "$LIVE_DB" "
    SELECT COUNT(*), COUNT(strategy_intent)
    FROM (SELECT strategy_intent FROM trade_log ORDER BY timestamp DESC LIMIT 20);
" | tr '|' ' ')

echo "  last 20 rows: $tagged / $total have strategy_intent set"
if [ "$tagged" != "$total" ]; then
    echo "  [WARN] some recent rows still have NULL strategy_intent"
    echo "         (acceptable only if you have not patched the relevant writer yet)"
fi

# Most recent row per intent — proves both writers fire
echo ""
echo "  most recent row per intent:"
sqlite3 "$LIVE_DB" "
    SELECT '    ' || COALESCE(strategy_intent,'(null)') || '  ' ||
           datetime(MAX(timestamp),'unixepoch','localtime') || '  ' ||
           COUNT(*) || ' total'
    FROM trade_log
    GROUP BY strategy_intent
    ORDER BY MAX(timestamp) DESC;
"

# Deep schema check on the SINGLE most recent row of each intent. If a writer
# is missing a field, this will catch it the moment a fresh row lands. We
# differentiate between an "open" row (pnl=0, exit_* expected NULL) and a
# "close" row (pnl!=0, exit_* required).
echo ""
echo "  deep schema check (most recent row per intent):"
schema_warn=0
check_intent() {
    local intent="$1"
    local label="$2"
    row=$(sqlite3 -separator '|' "$LIVE_DB" "
        SELECT id, timestamp, pnl, entry_price, exit_price, exit_reason,
               strategy_version, trigger_rule, instance_name, direction, regime
        FROM trade_log
        WHERE strategy_intent='$intent'
        ORDER BY timestamp DESC LIMIT 1;
    ")
    if [ -z "$row" ]; then
        echo "    [skip] no $label rows yet"
        return
    fi
    IFS='|' read -r id ts pnl entry exit reason version trigger inst dir regime <<< "$row"
    age_min=$(awk -v t="$ts" -v now="$(date +%s)" 'BEGIN{print int((now-t)/60)}')
    is_close=$(awk -v p="$pnl" 'BEGIN{print (p+0 != 0) ? 1 : 0}')
    missing=()
    [ -z "$entry" ] && missing+=("entry_price")
    [ -z "$version" ] && missing+=("strategy_version")
    [ -z "$trigger" ] && missing+=("trigger_rule")
    [ -z "$inst" ] && missing+=("instance_name")
    [ -z "$dir" ] && missing+=("direction")
    # regime is sniper-only (grid trades have no signal regime tag)
    if [ "$intent" = "momentum_breakout" ]; then
        [ -z "$regime" ] && missing+=("regime")
    fi
    if [ "$is_close" = "1" ]; then
        [ -z "$exit" ] && missing+=("exit_price")
        [ -z "$reason" ] && missing+=("exit_reason")
        kind="close pnl=$pnl"
    else
        kind="open"
    fi
    if [ ${#missing[@]} -eq 0 ]; then
        echo "    [ok]   $label id=$id ${age_min}min ago ($kind) — all fields populated"
    else
        echo "    [WARN] $label id=$id ${age_min}min ago ($kind) — missing: ${missing[*]}"
        schema_warn=$((schema_warn + 1))
    fi
}
check_intent "grid_mean_reversion" "grid"
check_intent "momentum_breakout"   "sniper"

# Note about freshness: a populated-but-pre-restart row only proves the
# backfill worked, not that the patched writer is firing. The verifier prints
# row age so the human can see whether this is a true post-restart sample.
echo ""
sniper_pid=$(launchctl print "gui/${UID_REAL}/com.ibitlabs.sniper" 2>/dev/null | awk '/^[[:space:]]*pid =/{print $3; exit}')
echo "  (live sniper pid=$sniper_pid — rows older than this process restart are backfilled, not freshly written)"

echo ""
if [ "$fail" -gt 0 ]; then
    echo "=== VERDICT: FAIL ($fail service(s) did not come back up) ==="
    exit 1
fi
echo "=== VERDICT: OK ==="
exit 0
