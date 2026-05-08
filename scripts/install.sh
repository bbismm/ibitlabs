#!/bin/bash
# iBitLabs — One-click LaunchAgent installer
# Run: bash ~/ibitlabs/scripts/install.sh

set -e
echo "🚀 Installing iBitLabs automation LaunchAgents..."

cp ~/ibitlabs/scripts/com.ibitlabs.daily-report-v2.plist ~/Library/LaunchAgents/
cp ~/ibitlabs/scripts/com.ibitlabs.weekly-report-v2.plist ~/Library/LaunchAgents/

launchctl load ~/Library/LaunchAgents/com.ibitlabs.daily-report-v2.plist
launchctl load ~/Library/LaunchAgents/com.ibitlabs.weekly-report-v2.plist

echo "✅ LaunchAgents loaded:"
launchctl list | grep ibitlabs

echo ""
echo "📌 Test now:"
echo "  TELEGRAM_BOT_TOKEN='your_token' python3 ~/ibitlabs/scripts/daily_report_generator.py --date 2026-04-03"
echo ""
echo "📌 Schedules:"
echo "  Daily report:  00:05 every day"
echo "  Weekly report: Sunday 20:00"
