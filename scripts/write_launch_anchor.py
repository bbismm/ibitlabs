#!/usr/bin/env python3
"""write_launch_anchor.py — one-shot multi-symbol go-live anchor writer.

Run this AFTER the ETH plist is bootstrapped in live mode and BEFORE relying
on the `multi_symbol` block in /api/live-status. The anchor freezes SOL's
balance at the launch instant so "since multi-symbol launch" deltas are
computable forever after.

Hard guards:
  - Refuses to overwrite an existing anchor unless --force is passed.
  - Refuses to write if SOL bot at 127.0.0.1:8086 is unreachable or reports
    alive=false (a stale SOL snapshot would poison the anchor).
  - Refuses to write if the ETH state file or DB declared on the command line
    is missing.

Usage:
  python3 scripts/write_launch_anchor.py \\
      --eth-mode live \\
      --eth-state sol_sniper_state_eth.json \\
      --eth-db sol_sniper_eth.db \\
      --eth-starting-capital 1000.0

  # Force overwrite (use only within minutes of a misfire):
  python3 scripts/write_launch_anchor.py --force ...
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ANCHOR_PATH = os.path.normpath(os.path.join(
    _HERE, "..", "state", "multi_symbol_launch_anchor.json"))
SOL_STATUS_URL = "http://127.0.0.1:8086/api/live-status"


def _fetch_sol_status() -> dict:
    req = urllib.request.Request(SOL_STATUS_URL)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--eth-mode", choices=("live", "paper"), required=True,
                    help="ETH bot mode at launch — 'paper' is for smoke tests only")
    ap.add_argument("--eth-state", required=True,
                    help="Path to ETH bot state file (e.g. sol_sniper_state_eth.json)")
    ap.add_argument("--eth-db", required=True,
                    help="Path to ETH bot DB (e.g. sol_sniper_eth.db)")
    ap.add_argument("--eth-starting-capital", type=float, default=1000.0,
                    help="ETH seed capital in USD (default 1000)")
    ap.add_argument("--anchor-path", default=DEFAULT_ANCHOR_PATH,
                    help="Where to write the anchor JSON")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing anchor (USE ONLY ON MISFIRE)")
    args = ap.parse_args()

    anchor_path = os.path.abspath(args.anchor_path)

    if os.path.exists(anchor_path) and not args.force:
        print(f"ERROR: anchor already exists at {anchor_path}", file=sys.stderr)
        print("       This is a one-shot write. Use --force only within minutes",
              file=sys.stderr)
        print("       of a known misfire (the file is load-bearing).",
              file=sys.stderr)
        sys.exit(2)

    eth_state_abs = os.path.abspath(args.eth_state)
    eth_db_abs = os.path.abspath(args.eth_db)
    if not os.path.exists(eth_state_abs):
        print(f"ERROR: ETH state file not found: {eth_state_abs}", file=sys.stderr)
        sys.exit(2)
    if not os.path.exists(eth_db_abs):
        print(f"ERROR: ETH DB file not found: {eth_db_abs}", file=sys.stderr)
        sys.exit(2)

    try:
        sol_status = _fetch_sol_status()
    except Exception as e:
        print(f"ERROR: SOL /api/live-status unreachable: {e}", file=sys.stderr)
        print("       Refusing to anchor against a stale/missing SOL snapshot.",
              file=sys.stderr)
        sys.exit(2)
    if not sol_status.get("alive"):
        print("ERROR: SOL bot reports alive=false at /api/live-status",
              file=sys.stderr)
        sys.exit(2)

    with open(eth_state_abs) as f:
        eth_state = json.load(f)
    eth_cash = float(eth_state.get("cash", 0))
    eth_pos = eth_state.get("position") or {}
    eth_margin = float(eth_pos.get("margin", 0)) if eth_pos else 0.0
    eth_balance_at_launch = round(eth_cash + eth_margin, 2)

    anchor = {
        "schema_version": 1,
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "launched_at_ts": time.time(),
        "eth_mode": args.eth_mode,
        "eth_state_file": eth_state_abs,
        "eth_db_file": eth_db_abs,
        "sol_starting_capital": float(sol_status.get("starting_capital", 1000.0)),
        "sol_balance_at_launch": float(sol_status.get("balance")),
        "sol_total_pnl_at_launch": float(sol_status.get("total_pnl", 0)),
        "eth_starting_capital": args.eth_starting_capital,
        "eth_balance_at_launch": eth_balance_at_launch,
    }

    os.makedirs(os.path.dirname(anchor_path), exist_ok=True)
    with open(anchor_path, "w") as f:
        json.dump(anchor, f, indent=2)
        f.write("\n")

    print(f"OK Anchor written: {anchor_path}")
    print(f"   Launched at UTC: {anchor['launched_at']}")
    print(f"   ETH mode:        {anchor['eth_mode']}")
    print(f"   SOL balance:     ${anchor['sol_balance_at_launch']:.2f}")
    print(f"   ETH balance:     ${anchor['eth_balance_at_launch']:.2f}")
    combined = anchor["sol_balance_at_launch"] + anchor["eth_balance_at_launch"]
    print(f"   Combined:        ${combined:.2f}")


if __name__ == "__main__":
    main()
