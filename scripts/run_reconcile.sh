#!/bin/bash
# run_reconcile.sh — daily wrapper for backtest_vs_paper_reconcile.py.
#
# Runs the reconciliation against BOTH instances (live + shadow), each with
# their own trailing params. Appends results to dated logs. If either exits
# non-zero (= divergence beyond tolerance) AND NTFY_TOPIC is set, fires a push
# so model drift surfaces the same morning.
#
# Read-only. Safe to invoke manually any time:
#     scripts/run_reconcile.sh

set -u
cd /Users/bonnyagent/ibitlabs

# ── Load Coinbase API credentials from .env if not already in environment ──
# Scheduled tasks (launchd) don't inherit the shell environment, so CB_API_KEY
# and CB_API_SECRET are empty unless we load them explicitly here.
ENV_FILE=/Users/bonnyagent/ibitlabs/.env
if [ -f "$ENV_FILE" ]; then
    _cb_key=$(grep -m1 '^CB_API_KEY=' "$ENV_FILE" | cut -d= -f2-)
    _cb_secret=$(grep -m1 '^CB_API_SECRET=' "$ENV_FILE" | cut -d= -f2-)
    export CB_API_KEY="${CB_API_KEY:-$_cb_key}"
    export CB_API_SECRET="${CB_API_SECRET:-$_cb_secret}"
fi

DATE=$(date +%Y-%m-%d)
LOG_DIR=/Users/bonnyagent/ibitlabs/logs
PY=/usr/bin/python3
SCRIPT=/Users/bonnyagent/ibitlabs/scripts/backtest_vs_paper_reconcile.py

# Live params (must match sol_sniper_config.py + com.ibitlabs.sniper.plist)
# 2026-04-16: trail widened 0.008/0.004 → 0.015/0.005 per sweep result
LIVE_DB=/Users/bonnyagent/ibitlabs/sol_sniper.db
LIVE_ACT=0.015
LIVE_STP=0.005

# Shadow params (must match com.ibitlabs.sniper-shadow.plist)
SHADOW_DB=/Users/bonnyagent/ibitlabs/sol_sniper_shadow.db
SHADOW_ACT=0.004
SHADOW_STP=0.005

NTFY_TOPIC=${NTFY_TOPIC:-}

# Alert cooldown state — keyed by title hash. A recurring condition (e.g. the
# regime-drift BREACH that persists for days) should notify ONCE per window,
# not every reconcile run. The detector still exits 1 so launchd/log reflects
# truth; only the ntfy push is suppressed.
ALERT_COOLDOWN_DIR=/Users/bonnyagent/ibitlabs/state/alert_cooldowns
mkdir -p "$ALERT_COOLDOWN_DIR"
ALERT_COOLDOWN_SECONDS=${ALERT_COOLDOWN_SECONDS:-86400}  # 24h default

push_alert() {
    local title="$1"
    local body="$2"
    if [ -z "$NTFY_TOPIC" ]; then
        return 0
    fi
    # Cooldown check — hash the title (not the body, which may contain paths
    # or timestamps that differ run-to-run). If we fired an identical-title
    # alert inside the cooldown window, log locally and skip ntfy.
    local key
    key=$(printf '%s' "$title" | md5 -q 2>/dev/null || printf '%s' "$title" | md5sum | awk '{print $1}')
    local state_file="$ALERT_COOLDOWN_DIR/$key"
    local now_ts
    now_ts=$(date +%s)
    if [ -f "$state_file" ]; then
        local last_ts
        last_ts=$(cat "$state_file" 2>/dev/null || echo 0)
        local age=$(( now_ts - last_ts ))
        if [ "$age" -lt "$ALERT_COOLDOWN_SECONDS" ]; then
            echo "[cooldown] suppressed alert '$title' (age ${age}s < ${ALERT_COOLDOWN_SECONDS}s)" >&2
            return 0
        fi
    fi
    curl -s -X POST \
        -H "Title: $title" \
        -H "Priority: urgent" \
        -H "Tags: warning,chart_with_downwards_trend" \
        -d "$body" \
        "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1
    echo "$now_ts" > "$state_file"
}

run_one() {
    local label="$1"
    local db="$2"
    local act="$3"
    local stp="$4"
    local log="$LOG_DIR/reconcile_${label}_${DATE}.log"

    echo "" >> "$log"
    echo "==== reconcile run @ $(date '+%Y-%m-%d %H:%M:%S') ====" >> "$log"
    "$PY" "$SCRIPT" --db "$db" --days 7 \
        --activate "$act" --stop "$stp" >> "$log" 2>&1
    local rc=$?
    echo "exit_code=$rc" >> "$log"

    if [ "$rc" -eq 1 ]; then
        push_alert "RECONCILE DRIFT — $label" \
                   "$label paper diverged from backtest beyond tolerance. See $log"
    elif [ "$rc" -eq 2 ]; then
        push_alert "RECONCILE ERROR — $label" \
                   "$label reconcile script errored (exit 2). See $log"
    fi
    return $rc
}

run_one live   "$LIVE_DB"   "$LIVE_ACT"   "$LIVE_STP"
LIVE_RC=$?
run_one shadow "$SHADOW_DB" "$SHADOW_ACT" "$SHADOW_STP"
SHADOW_RC=$?

# DB ↔ Exchange reconciler — catches silent-intent / silent-fill cases that
# backtest-vs-paper does NOT see (orphan DB rows, or exchange fills missing
# from DB). Report-only here; inserts require manual --apply flag.
DBXC_LOG="$LOG_DIR/db_vs_exchange_${DATE}.log"
echo "" >> "$DBXC_LOG"
echo "==== db↔exchange reconcile @ $(date '+%Y-%m-%d %H:%M:%S') ====" >> "$DBXC_LOG"
"$PY" /Users/bonnyagent/ibitlabs/scripts/db_vs_exchange_reconcile.py --days 7 \
    >> "$DBXC_LOG" 2>&1
DBXC_RC=$?
echo "exit_code=$DBXC_RC" >> "$DBXC_LOG"
if [ "$DBXC_RC" -eq 1 ]; then
    push_alert "DB↔EXCHANGE DRIFT" \
               "Trade log diverged from Coinbase fills. Review $DBXC_LOG then run with --apply"
elif [ "$DBXC_RC" -eq 2 ]; then
    push_alert "DB↔EXCHANGE ERROR" \
               "db_vs_exchange_reconcile.py errored (exit 2). See $DBXC_LOG"
fi

# Regime watch — independent of paper-vs-backtest divergence. Detects the
# OTHER kind of model drift: not "paper diverged from backtest" but "the
# market is no longer in the regime the strategy was trained on". Logs to
# its own dated file so the morning push pipeline can grep for breaches.
REGIME_LOG="$LOG_DIR/regime_watch_${DATE}.log"
echo "" >> "$REGIME_LOG"
echo "==== regime watch run @ $(date '+%Y-%m-%d %H:%M:%S') ====" >> "$REGIME_LOG"
"$PY" /Users/bonnyagent/ibitlabs/scripts/regime_watch.py >> "$REGIME_LOG" 2>&1
REGIME_RC=$?
echo "exit_code=$REGIME_RC" >> "$REGIME_LOG"
if [ "$REGIME_RC" -eq 1 ]; then
    push_alert "REGIME DRIFT" \
               "Strategy training regime no longer matches current market. See $REGIME_LOG"
fi

# Dashboard health check — alive process is not the same as healthy endpoint.
# On 04-10 the harness ran 22h but every /api/status request crashed inside
# build_status() (None.get bug). launchd never noticed because the process
# stayed up. So we curl the endpoint directly: anything other than 200 = page.
DASH_LOG="$LOG_DIR/dashboard_healthcheck_${DATE}.log"
echo "" >> "$DASH_LOG"
echo "==== dashboard health @ $(date '+%Y-%m-%d %H:%M:%S') ====" >> "$DASH_LOG"
DASH_CODE=$(curl -sS -o /dev/null -m 10 -w "%{http_code}" http://localhost:8086/api/status 2>>"$DASH_LOG")
DASH_RC=0
echo "http_code=$DASH_CODE" >> "$DASH_LOG"
if [ "$DASH_CODE" != "200" ]; then
    DASH_RC=1
    push_alert "DASHBOARD UNHEALTHY" \
               "localhost:8086/api/status returned $DASH_CODE. Likely build_status() exception. See $DASH_LOG"
fi

# Dashboard DECOUPLE probe — catches "static 200 is lying".
# The health-check above only asserts HTTP reachability. This probe asserts
# CAUSAL CONSISTENCY: the published view must advance when the engine writes.
# Samples snapshot_seq twice (60s apart) and cross-checks against trade_log.
# If trade_log gained rows but snapshot_seq froze, the dashboard has decoupled
# from the engine even though HTTP still returns 200. Only runs when the
# basic health check passed, otherwise we'd double-alert on the same failure.
DECOUPLE_RC=0
if [ "$DASH_RC" -eq 0 ]; then
    DECOUPLE_LOG="$LOG_DIR/dashboard_decouple_${DATE}.log"
    echo "" >> "$DECOUPLE_LOG"
    echo "==== decouple probe @ $(date '+%Y-%m-%d %H:%M:%S') ====" >> "$DECOUPLE_LOG"
    "$PY" /Users/bonnyagent/ibitlabs/scripts/dashboard_decouple_probe.py --gap 60 \
        >> "$DECOUPLE_LOG" 2>&1
    DECOUPLE_RC=$?
    echo "exit_code=$DECOUPLE_RC" >> "$DECOUPLE_LOG"
    if [ "$DECOUPLE_RC" -eq 1 ]; then
        push_alert "DASHBOARD DECOUPLED" \
                   "Engine wrote new trades but snapshot_seq froze. Published view has lost causal consistency with the engine. See $DECOUPLE_LOG"
    elif [ "$DECOUPLE_RC" -eq 2 ]; then
        push_alert "DECOUPLE PROBE ERROR" \
                   "dashboard_decouple_probe.py exited 2 (probe error). See $DECOUPLE_LOG"
    fi
fi

# Exit non-zero if anything failed, so launchd's last exit code reflects truth.
if [ "$LIVE_RC" -ne 0 ] || [ "$SHADOW_RC" -ne 0 ] || [ "$REGIME_RC" -ne 0 ] || [ "$DASH_RC" -ne 0 ] || [ "$DECOUPLE_RC" -eq 1 ] || [ "$DBXC_RC" -eq 1 ]; then
    exit 1
fi
exit 0
