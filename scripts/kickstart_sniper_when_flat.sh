#!/bin/zsh
#
# kickstart_sniper_when_flat.sh — one-shot launchd watcher.
#
# Polls /api/live-status every 15 min. The first time the bot is FLAT
# (no active position) AND the kill-switch fields look healthy, kickstart
# the sniper to load the 2026-04-30 bal_after fix (sol_sniper_main.py:870),
# push an ntfy confirmation, then self-disable so we never re-fire.
#
# Why a watcher instead of restarting now: a restart while a position is
# open would lose the in-memory trailing tracker / halt counters and risks
# triggering the close_position SDK class of bugs. Wait for natural exit.

set -u
set -o pipefail

LABEL="com.ibitlabs.sniper-kickstart-pending"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/ibitlabs/logs/sniper-kickstart-pending"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/$TS.log"

mkdir -p "$LOG_DIR"

NTFY_TOPIC="${NTFY_TOPIC:-sol-sniper-bonny}"

push() {
  local title="$1" body="$2"
  curl -s -H "Title: $title" -H "Priority: default" \
    -d "$body" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null 2>&1 || true
}

{
  echo "=== kickstart_sniper_when_flat @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

  STATUS_JSON="$(curl -s --max-time 8 https://www.ibitlabs.com/api/live-status 2>/dev/null)" || STATUS_JSON=""
  if [[ -z "$STATUS_JSON" ]]; then
    echo "live-status unreachable; deferring"
    exit 0
  fi

  ACTIVE="$(echo "$STATUS_JSON" | /usr/bin/python3 -c 'import json,sys; d=json.load(sys.stdin); p=d.get("position") or {}; print("yes" if p.get("active") else "no")' 2>/dev/null || echo "?")"
  echo "position.active = $ACTIVE"

  if [[ "$ACTIVE" != "no" ]]; then
    echo "still in position; deferring"
    exit 0
  fi

  echo "FLAT — kickstarting sniper to load bal_after fix"
  /bin/launchctl kickstart -k "gui/$(id -u)/com.ibitlabs.sniper"
  KICK_RC=$?
  echo "kickstart exit: $KICK_RC"

  if [[ $KICK_RC -ne 0 ]]; then
    push "sniper kickstart FAILED" "exit code $KICK_RC. Watcher staying armed; will retry next 15min tick."
    exit $KICK_RC
  fi

  push "sniper restarted (bal_after fix loaded)" \
    "Open notifications will now report total equity instead of pre-trade free cash. Watcher disabled."

  echo "self-disabling watcher"
  /bin/launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  if [[ -f "$PLIST" ]]; then
    /bin/mv "$PLIST" "$PLIST.disabled-fired-$(date +%Y-%m-%d)"
    echo "plist renamed to: $PLIST.disabled-fired-$(date +%Y-%m-%d)"
  fi
} 2>&1 | tee -a "$LOG"
