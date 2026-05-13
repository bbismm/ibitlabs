#!/usr/bin/env python3
"""SOL-vs-ETH trade-rate diff over a window.

Validates the +50% frequency assumption from `multi_symbol_eth_expansion_DD.md`
by counting closed trades on both symbols over the same time window. Used during
ETH paper Phase 3 (2026-05-06 → 2026-05-20) to distinguish "ETH thresholds
miscalibrated" from "regime is just slow this week."

Usage:
    python3 signal_counter_diff.py
    python3 signal_counter_diff.py --start 2026-05-06T14:49:00Z
    python3 signal_counter_diff.py --start 2026-05-06T14:49:00Z --end 2026-05-08T21:41:00Z

Default window: ETH paper Phase 3 4th-reset start → now (UTC).
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PHASE3_START = "2026-05-06T14:49:00Z"
SOL_DB = Path.home() / "ibitlabs" / "sol_sniper.db"
ETH_DB = Path.home() / "ibitlabs" / "sol_sniper_eth_paper.db"
SOL_HISTORICAL_RATE_PER_DAY = 3.0  # baseline since 2026-04-20 launch


def parse_iso(s: str) -> int:
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")
    return int(datetime.fromisoformat(s).timestamp())


def fmt_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def count_in_window(db_path: Path, start_ts: int, end_ts: int):
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            COUNT(*) AS rows,
            SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END) AS closes,
            SUM(CASE WHEN side='BUY'  THEN 1 ELSE 0 END) AS opens
        FROM trade_log
        WHERE timestamp >= ? AND timestamp <= ?
        """,
        (start_ts, end_ts),
    )
    row = cur.fetchone()
    conn.close()
    return {"rows": row[0] or 0, "closes": row[1] or 0, "opens": row[2] or 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default=PHASE3_START, help=f"ISO8601 UTC (default {PHASE3_START})")
    p.add_argument("--end", default=None, help="ISO8601 UTC (default: now)")
    args = p.parse_args()

    start_ts = parse_iso(args.start)
    end_ts = parse_iso(args.end) if args.end else int(datetime.now(timezone.utc).timestamp())
    if end_ts <= start_ts:
        sys.exit("end must be after start")
    hours = (end_ts - start_ts) / 3600
    days = hours / 24

    sol = count_in_window(SOL_DB, start_ts, end_ts)
    eth = count_in_window(ETH_DB, start_ts, end_ts)
    if sol is None or eth is None:
        sys.exit(f"missing DB: SOL={SOL_DB.exists()} ETH={ETH_DB.exists()}")

    sol_rate = sol["closes"] / max(days, 0.001)
    eth_rate = eth["closes"] / max(days, 0.001)

    print(f"Window: {fmt_utc(start_ts)} → {fmt_utc(end_ts)}  ({hours:.1f}h / {days:.2f}d)")
    print()
    print(f"  SOL live  : {sol['closes']:>3} closes, {sol['opens']:>3} opens  "
          f"(rate {sol_rate:.2f}/day)")
    print(f"  ETH paper : {eth['closes']:>3} closes, {eth['opens']:>3} opens  "
          f"(rate {eth_rate:.2f}/day)")
    print()

    if sol["closes"] > 0:
        ratio = eth["closes"] / sol["closes"]
        expectation = "matches" if 0.35 <= ratio <= 0.65 else "DEVIATES from"
        print(f"  Ratio ETH/SOL: {ratio:.2f}  ({expectation} +50% frequency expectation 0.50)")
    else:
        print("  Ratio ETH/SOL: undefined (SOL closes = 0 in window)")

    sol_vs_baseline = sol_rate / SOL_HISTORICAL_RATE_PER_DAY
    if sol_vs_baseline < 0.6:
        print(f"  ⚠ SOL itself at {sol_vs_baseline*100:.0f}% of historical baseline "
              f"({SOL_HISTORICAL_RATE_PER_DAY:.1f}/day) — regime is slow, not ETH-specific")
    elif sol_vs_baseline > 1.4:
        print(f"  ↑ SOL above baseline at {sol_vs_baseline*100:.0f}% of historical "
              f"({SOL_HISTORICAL_RATE_PER_DAY:.1f}/day)")
    else:
        print(f"  SOL near baseline ({sol_vs_baseline*100:.0f}% of "
              f"{SOL_HISTORICAL_RATE_PER_DAY:.1f}/day)")


if __name__ == "__main__":
    main()
