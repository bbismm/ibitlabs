#!/bin/bash
cd "$(dirname "$0")"
source .env

python3 scalper.py
