#!/usr/bin/env python3
"""
Gate 1: Sample size + regime coverage check.

Prep doc lines 79-82:
  (a) shadow ≥ 30 closed trades?
  (b) shadow regime distribution covers ≥ 2 buckets with ≥ 5 trades each?

If either fails → defer further, no swap. Print verdict + raw counts.
"""
import sqlite3
from collections import Counter
import json
import os
import time

SHADOW_DB = "/Users/bonnyagent/ibitlabs/sol_sniper_shadow.db"
GRID_WHAT_IF_LOG = "/Users/bonnyagent/ibitlabs/logs/grid_what_if.jsonl"
OUT_DIR = "/Users/bonnyagent/ibitlabs/logs/4gate_2026-06-05"
os.makedirs(OUT_DIR, exist_ok=True)


def gate1():
    conn = sqlite3.connect(f"file:{SHADOW_DB}?mode=ro", uri=True)
    rows = conn.execute("""
        SELECT direction, regime, exit_reason, pnl, entry_price, exit_price,
               strategy_version, instance_name
        FROM trade_log
        WHERE exit_reason IS NOT NULL AND exit_reason != ''
          AND strategy_version IN ('hybrid_v5.1', 'v5.1', 'sniper_v5.1')
    """).fetchall()
    conn.close()

    n_closed = len(rows)
    regime_counts = Counter(r[1] for r in rows if r[1])
    buckets_with_5 = sum(1 for v in regime_counts.values() if v >= 5)

    a_pass = n_closed >= 30
    b_pass = buckets_with_5 >= 2

    print(f"Gate 1: shadow sample-size + regime-coverage check")
    print(f"  Closed shadow trades (v5.1):  {n_closed}")
    print(f"  Regime distribution:          {dict(regime_counts)}")
    print(f"  Buckets with >=5 trades:      {buckets_with_5}")
    print()
    print(f"  (a) >=30 closed trades:       {'PASS' if a_pass else 'FAIL'}")
    print(f"  (b) >=2 buckets x >=5 trades: {'PASS' if b_pass else 'FAIL'}")
    print()
    print(f"GATE 1 VERDICT: {'PASS' if (a_pass and b_pass) else 'FAIL — DEFER, no swap'}")

    return {
        "ts": time.time(),
        "n_closed": n_closed,
        "regime_counts": dict(regime_counts),
        "buckets_with_5_plus": buckets_with_5,
        "a_pass": a_pass,
        "b_pass": b_pass,
        "overall": a_pass and b_pass,
    }


def path_c_supplement():
    """Path C event count + regime coverage as a Gate 1 modifier.

    Per `project_c_hook_2026_05_12.md`, target is >=20 events / >=2 regimes
    by 2026-06-05. If Path C is starved, regime coverage in Gate 1 is also
    likely thin — flag both together.
    """
    if not os.path.exists(GRID_WHAT_IF_LOG):
        print("\nPath C log: NOT YET CREATED. Hook may have logged 0 state-changes.")
        return None

    events = []
    with open(GRID_WHAT_IF_LOG) as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if not events:
        print("\nPath C log: 0 events.")
        return None

    regime_dist = Counter(e["regime"] for e in events)
    print(f"\nPath C supplement (from {GRID_WHAT_IF_LOG}):")
    print(f"  Total events:        {len(events)}")
    print(f"  Regime distribution: {dict(regime_dist)}")
    print(f"  Target by 06-05:     >=20 events, >=2 regimes")
    print(f"  Target met:          {len(events) >= 20 and len(regime_dist) >= 2}")
    return {"events": len(events), "regime_dist": dict(regime_dist)}


if __name__ == "__main__":
    result = gate1()
    pathc = path_c_supplement()
    out = {"gate1": result, "path_c_supplement": pathc}
    out_path = os.path.join(OUT_DIR, "gate1.out")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nRaw output: {out_path}")
