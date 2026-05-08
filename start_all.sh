#!/bin/bash
# Start all BIBSUS harnesses + infrastructure
# Usage: ./start_all.sh
cd "$(dirname "$0")"

echo "=== BIBSUS 4-Harness System ==="
echo ""

# Infrastructure (must start first)
echo "[1/7] Starting Monitor Harness..."
nohup bash start_monitor.sh > logs/monitor.log 2>&1 &
sleep 2

echo "[2/7] Starting Security Harness..."
nohup bash start_security.sh > logs/security.log 2>&1 &
sleep 1

echo "[3/7] Starting Scalper..."
nohup bash start_scalper.sh > logs/scalper.log 2>&1 &
sleep 1

# Product harnesses
echo "[4/7] Starting Owner Harness (port 8080)..."
nohup bash start_owner.sh > logs/owner.log 2>&1 &
sleep 1

echo "[5/7] Starting Preview Harness (port 8081)..."
nohup bash start_preview.sh > logs/preview.log 2>&1 &
sleep 1

echo "[6/7] Starting Signals Harness (port 8082)..."
nohup bash start_signals.sh > logs/signals.log 2>&1 &
sleep 1

echo "[7/8] Starting Grid Autopilot Harness (port 8083)..."
nohup bash start_autopilot.sh > logs/autopilot.log 2>&1 &
sleep 1

echo "[8/9] Starting Crazy Trader (5x leverage)..."
nohup bash start_crazy.sh > logs/crazy.log 2>&1 &
sleep 1

echo "[9/10] Starting Crazy Dashboard (port 8085)..."
nohup bash start_crazy_dashboard.sh > logs/crazy_dashboard.log 2>&1 &
sleep 1

echo "[10/10] Starting Crazy Recorder (auto screen capture)..."
nohup bash start_crazy_recorder.sh > logs/crazy_recorder.log 2>&1 &
sleep 1

echo ""
echo "=== All systems launched ==="
echo "  Owner:    http://localhost:8080  (full trading dashboard, behind tunnel)"
echo "  Preview:  http://localhost:8081  (ibitlabs.com)"
echo "  Signals:  http://localhost:8082  (ibitlabs.com/signals)"
echo "  Autopilot:     http://localhost:8083  (legacy tier)"
echo "  Crazy:         Crazy Trader (\$1000→\$3000 challenge)"
echo "  Crazy Dash:    http://localhost:8085  (OBS capture)"
echo ""
echo "Logs: grid_trader/logs/"
echo "Stop all: pkill -f '_harness.py'; pkill -f scalper.py; pkill -f crazy_main.py; pkill -f crazy_dashboard"
