#!/bin/bash
cd "$(dirname "$0")"

lsof -ti:8081 | xargs kill -9 2>/dev/null

python3 preview_harness.py
