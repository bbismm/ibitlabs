#!/bin/bash
# Daily regen + deploy of ibitlabs.com/lab.
# Fired by com.ibitlabs.lab-deploy launchd. Safe to run manually.
set -u
set -o pipefail

ROOT="$HOME/ibitlabs"
WEB="$ROOT/web"
TARGET="$WEB/public/lab/index.html"
TS="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"

echo "==== [$TS] lab-deploy start ===="

# ---- 1. regenerate the public report
cd "$ROOT/notebooks" || { echo "[$TS] FAIL: cd notebooks"; exit 1; }
/usr/bin/python3 build_report.py --public
RC=$?
if [ "$RC" -ne 0 ]; then
    echo "[$TS] FAIL: build_report rc=$RC — skipping deploy"
    exit 1
fi

# ---- 2. sanity-check the output
if [ ! -s "$TARGET" ]; then
    echo "[$TS] FAIL: $TARGET missing or empty — skipping deploy"
    exit 1
fi
SIZE=$(stat -f '%z' "$TARGET")
if [ "$SIZE" -lt 50000 ]; then
    echo "[$TS] FAIL: $TARGET is only $SIZE bytes (expected >50KB) — skipping deploy"
    exit 1
fi
echo "[$TS] built: $SIZE bytes"

# ---- 3. wrangler deploy
cd "$WEB" || { echo "[$TS] FAIL: cd web"; exit 1; }
wrangler pages deploy public \
    --project-name=bibsus \
    --branch=main \
    --commit-dirty=true 2>&1 | tail -15
RC=${PIPESTATUS[0]}
if [ "$RC" -ne 0 ]; then
    echo "[$TS] FAIL: wrangler rc=$RC"
    exit 1
fi

echo "==== [$TS] lab-deploy ok ===="
