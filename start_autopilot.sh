#!/bin/bash
cd "$(dirname "$0")"
source .env

lsof -ti:8083 | xargs kill -9 2>/dev/null

python3 autopilot_harness.py
