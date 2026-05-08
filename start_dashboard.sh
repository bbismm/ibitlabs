#!/bin/bash
cd "$(dirname "$0")"
source .env

lsof -ti:8080 | xargs kill -9 2>/dev/null

python3 dashboard_harness.py
