#!/bin/bash
# run_eth_cutover_reminder.sh
#
# One-shot ntfy push for the ETH paper -> live cut-over decision gate.
# Fires once at 2026-05-20 09:49 EDT (= 13:49 UTC, T-1h before the 14:49 UTC
# Phase 3 review / cut-over moment). Runs the 5 decision-gate read-only checks
# from docs/multi_symbol_live_cutover_checklist.md and pushes PASS/FAIL to ntfy.
#
# launchd has no Year key in StartCalendarInterval, so the plist refires on
# 5/20 each year. The TARGET_DATE guard below keeps the actual work one-shot.

set -u

LOG=/Users/bonnyagent/ibitlabs/logs/eth_cutover_reminder.log
DB=/Users/bonnyagent/ibitlabs/sol_sniper_eth_paper.db
NTFY_TOPIC=sol-sniper-bonny
TARGET_DATE="2026-05-20"

mkdir -p "$(dirname "$LOG")"

# ── One-shot date guard ──
TODAY=$(date +%Y-%m-%d)
if [ "$TODAY" != "$TARGET_DATE" ]; then
    echo "$(date -u +%FT%TZ) skipped (today=$TODAY != target=$TARGET_DATE)" >> "$LOG"
    exit 0
fi

# ── 5 decision-gate checks (all read-only) ──
# Use `direction` column (populated on close rows as "long"/"short") rather
# than `side` (the close-row exit side, which is the opposite of the trade
# direction — confusing for the human reader). COUNT(DISTINCT regime) gives
# an integer directly, no awk arithmetic required.
DIRECTIONS=$(sqlite3 "$DB" "SELECT direction, COUNT(*) FROM trade_log WHERE exit_price IS NOT NULL GROUP BY direction" 2>&1 | tr '\n' ' ')
REGIMES=$(sqlite3 "$DB" "SELECT regime, COUNT(*) FROM trade_log WHERE exit_price IS NOT NULL GROUP BY regime" 2>&1 | tr '\n' ' ')
REGIME_COUNT=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT regime) FROM trade_log WHERE exit_price IS NOT NULL" 2>&1)
TRADES=$(sqlite3 "$DB" "SELECT COUNT(*) FROM trade_log WHERE exit_price IS NOT NULL" 2>&1)
BOT_STATE=$(launchctl print "gui/$(id -u)/com.ibitlabs.sniper-eth" 2>/dev/null | grep -E "^[[:space:]]*(state|pid|last exit)" | head -3 | tr '\n' ' ')
MS_JSON=$(curl -s --max-time 5 http://127.0.0.1:8086/api/live-status 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('multi_symbol', 'MISSING'))" 2>&1)

# ── PASS/FAIL eval ──
if echo "$DIRECTIONS" | grep -q "long" && echo "$DIRECTIONS" | grep -q "short"; then DIR_PASS=PASS; else DIR_PASS=FAIL; fi
if [ "$REGIME_COUNT" -ge 2 ] 2>/dev/null; then REG_PASS=PASS; else REG_PASS=FAIL; fi
if echo "$BOT_STATE" | grep -q "never exited"; then BOT_PASS=PASS; else BOT_PASS="?"; fi
if echo "$MS_JSON" | grep -q "launched"; then MS_PASS=PASS; else MS_PASS=FAIL; fi

# ── Push body (kept short, ntfy soft cap) ──
PUSH="T-1h decision gate ($TODAY 09:49 EDT)
- Directions: $DIR_PASS [$DIRECTIONS]
- Regimes: $REG_PASS (N=$REGIME_COUNT)
- Closed trades: $TRADES
- Bot clean: $BOT_PASS
- Producer 2d: $MS_PASS ($MS_JSON)
Cut-over @ 10:49 EDT.
Runbook: ~/ibitlabs/docs/multi_symbol_live_cutover_checklist.md"

curl -s \
    -H "Title: ETH live cut-over T-1h" \
    -H "Priority: high" \
    -H "Tags: chart_with_upwards_trend" \
    -d "$PUSH" \
    "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1
NTFY_RC=$?

# ── Audit log (full output for the keyboard) ──
{
    echo "==== ETH cut-over T-1h reminder fired $(date -u +%FT%TZ) ===="
    echo "Directions: $DIRECTIONS"
    echo "Regimes:    $REGIMES"
    echo "Trades:     $TRADES"
    echo "Bot:        $BOT_STATE"
    echo "2d:         $MS_JSON"
    echo "Gates:      dir=$DIR_PASS regime=$REG_PASS bot=$BOT_PASS 2d=$MS_PASS"
    echo "ntfy_rc:    $NTFY_RC"
    echo ""
} >> "$LOG"

exit 0
