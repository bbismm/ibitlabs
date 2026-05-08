#!/bin/bash
# Watchdog — keeps all services alive. Run with: nohup bash watchdog.sh &
# Checks every 30 seconds, auto-restarts any crashed process.

cd "$(dirname "$0")"
source .env

LOG="watchdog.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1"
}

restart_scalper() {
    log "[Watchdog] Restarting scalper..."
    pkill -9 -f "scalper.py" 2>/dev/null
    sleep 2
    bash start_scalper.sh > /tmp/scalper.log 2>&1 &
    sleep 15
    if pgrep -f "scalper.py" > /dev/null; then
        log "[Watchdog] Scalper restarted OK"
    else
        log "[Watchdog] Scalper restart FAILED"
    fi
}

restart_monitor() {
    log "[Watchdog] Restarting monitor..."
    bash start_monitor.sh > /tmp/monitor.log 2>&1 &
    sleep 5
    log "[Watchdog] Monitor restarted"
}

restart_security() {
    log "[Watchdog] Restarting security..."
    bash start_security.sh > /tmp/security.log 2>&1 &
    sleep 5
    log "[Watchdog] Security restarted"
}

restart_dashboard() {
    log "[Watchdog] Restarting dashboard..."
    lsof -ti:8080 | xargs kill -9 2>/dev/null
    sleep 1
    bash start_dashboard.sh > /tmp/dashboard.log 2>&1 &
    sleep 5
    log "[Watchdog] Dashboard restarted"
}

restart_tunnel() {
    log "[Watchdog] Restarting cloudflare tunnel..."
    pkill -f cloudflared 2>/dev/null
    sleep 1
    cloudflared tunnel run bibsus-trade > /tmp/cloudflared.log 2>&1 &
    sleep 3
    log "[Watchdog] Tunnel restarted"
}

restart_signals() {
    log "[Watchdog] Restarting signals harness..."
    lsof -ti:8082 | xargs kill -9 2>/dev/null
    sleep 1
    python3 signals_harness.py > logs/signals_harness.log 2>&1 &
    sleep 5
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8082/ 2>/dev/null | grep -q "200"; then
        log "[Watchdog] Signals harness restarted OK"
    else
        log "[Watchdog] Signals harness restart FAILED"
    fi
}

# Send iMessage alert
alert() {
    osascript -e "tell application \"Messages\" to send \"[Watchdog] $1\" to buddy \"$NOTIFY_IMESSAGE\" of (service 1 whose service type is iMessage)" 2>/dev/null
}

log "=========================================="
log "Watchdog started — checking every 30s"
log "=========================================="

while true; do
    ISSUES=""

    # Check scalper
    if ! pgrep -f "scalper.py" > /dev/null; then
        ISSUES="$ISSUES scalper"
        restart_scalper
    fi

    # Check monitor
    if ! pgrep -f "monitor_harness" > /dev/null; then
        ISSUES="$ISSUES monitor"
        restart_monitor
    fi

    # Check security
    if ! pgrep -f "security_harness" > /dev/null; then
        ISSUES="$ISSUES security"
        restart_security
    fi

    # Check dashboard (port 8080)
    if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>/dev/null | grep -q "200"; then
        ISSUES="$ISSUES dashboard"
        restart_dashboard
    fi

    # Check signals harness (port 8082)
    if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:8082/ 2>/dev/null | grep -q "200"; then
        ISSUES="$ISSUES signals"
        restart_signals
    fi

    # Check cloudflare tunnel
    if ! pgrep -f "cloudflared" > /dev/null; then
        ISSUES="$ISSUES tunnel"
        restart_tunnel
    fi

    # Check internet connectivity
    if ! ping -c 1 -t 5 8.8.8.8 > /dev/null 2>&1; then
        log "[Watchdog] INTERNET DOWN"
        alert "Internet connection lost!"
    fi

    # Alert if any restarts happened
    if [ -n "$ISSUES" ]; then
        alert "Restarted:$ISSUES"
    fi

    sleep 30
done
