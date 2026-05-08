#!/usr/bin/env python3
"""
Dashboard decouple probe — the "200 is lying" detector.

Samples /api/status.snapshot_seq twice with a gap, and compares against
trade_log writes in the same interval. If the engine wrote new rows but
the dashboard's seq didn't advance, the published view has decoupled
from the engine's world model — the classic case the hardening commit
(69dc9dd) half-solved by keeping HTTP alive during exceptions.

A static 200 can lie almost as badly as a 502. This probe catches that.

Exit codes:
  0 = healthy (seq advancing, or engine idle so decouple is vacuous)
  1 = DECOUPLED (trade_log advanced, seq did not) — page
  2 = PROBE ERROR (dashboard unreachable, JSON malformed, DB locked)

Usage:
  python3 scripts/dashboard_decouple_probe.py [--gap 60] [--url http://...]
"""
import argparse
import json
import sqlite3
import sys
import time
import urllib.request

DEFAULT_URL = "http://localhost:8086/api/status"
DEFAULT_DB = "/Users/bonnyagent/ibitlabs/sol_sniper.db"
DEFAULT_GAP_SECONDS = 60


def fetch_seq(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        seq = data.get("snapshot_seq")
        generated_at = data.get("generated_at")
        watermark = data.get("source_watermark", {})
        stale_after = data.get("stale_after")
        if seq is None:
            return None, "status JSON missing snapshot_seq (harness not upgraded?)"
        return {
            "seq": int(seq),
            "generated_at": float(generated_at or 0),
            "watermark_id": int(watermark.get("max_trade_id", 0)),
            "stale_after": int(stale_after or 0),
            "stale_flag": bool(data.get("_stale", False)),
        }, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def count_new_trades_since(db_path, since_ts):
    conn = sqlite3.connect(db_path, timeout=3.0)
    try:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id),0) FROM trade_log WHERE timestamp > ?",
            (int(since_ts),),
        ).fetchone()
        return int(row[0]), int(row[1])
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--gap", type=int, default=DEFAULT_GAP_SECONDS,
                    help="seconds between the two seq samples")
    args = ap.parse_args()

    t0 = time.time()
    sample1, err = fetch_seq(args.url)
    if err:
        print(f"probe error on sample1: {err}", file=sys.stderr)
        return 2

    # Sleep the gap, then resample. During this window the engine may write
    # new trade_log rows; we check at the end how many it wrote.
    time.sleep(args.gap)

    sample2, err = fetch_seq(args.url)
    if err:
        print(f"probe error on sample2: {err}", file=sys.stderr)
        return 2

    try:
        new_trades, max_id_after = count_new_trades_since(args.db, t0)
    except Exception as e:
        print(f"probe error reading db: {e}", file=sys.stderr)
        return 2

    seq_delta = sample2["seq"] - sample1["seq"]
    staleness = time.time() - sample2["generated_at"] if sample2["generated_at"] else -1

    print(
        f"dashboard_decouple_probe: "
        f"seq {sample1['seq']}->{sample2['seq']} (delta={seq_delta}), "
        f"new_trades_in_gap={new_trades}, "
        f"watermark_id {sample1['watermark_id']}->{sample2['watermark_id']}, "
        f"staleness={staleness:.1f}s, stale_flag={sample2['stale_flag']}"
    )

    # The decouple condition: engine wrote, dashboard didn't update.
    # We use new_trades (engine activity) rather than watermark movement,
    # because a frozen dashboard would report the same watermark both times,
    # and we want ground-truth from the DB, not from the dashboard itself.
    if new_trades > 0 and seq_delta == 0:
        print(
            f"DECOUPLED: engine wrote {new_trades} trade_log row(s) during "
            f"the {args.gap}s probe window, but dashboard snapshot_seq did "
            f"not advance. Published view has frozen while engine keeps "
            f"trading. This is the 'static 200 is lying' failure mode.",
            file=sys.stderr,
        )
        return 1

    # Also flag if seq didn't advance AT ALL over the gap window, even without
    # new trades — the dashboard should still be rebuilding every CACHE_TTL.
    # A gap much larger than CACHE_TTL * 3 with zero seq movement means the
    # cache is frozen (same stale_cache fallback being served for every call).
    if seq_delta == 0 and args.gap >= 15:
        print(
            f"STALE: snapshot_seq did not advance in {args.gap}s — the "
            f"dashboard is serving cached/stale data even though the probe "
            f"interval is larger than CACHE_TTL. This is a softer version "
            f"of decouple (engine may be idle, so not page-worthy on its own).",
            file=sys.stderr,
        )
        # Not a hard failure — engine might be idle. Log only.

    return 0


if __name__ == "__main__":
    sys.exit(main())
