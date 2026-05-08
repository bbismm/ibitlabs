#!/usr/bin/env python3
"""
One-time normalization of historical GRID_* trade_log rows.

The grid strategy stored `quantity` as SOL-intent (e.g., 3.485 = $300 / price).
Coinbase fills in contracts (1 contract = 5 SOL). The DB's quantity was
internally consistent with the DB's `pnl` (both computed from the same
under-counted qty), but BOTH are ~44% smaller than what actually filled
on the exchange.

This script rewrites each GRID_* row's qty and pnl using exchange fills
as ground truth. Strategy:

  1. Backup DB first (sol_sniper.db.bak-<ts>).
  2. Fetch all exchange fills in the historical grid window (2026-04-07 → 04-15).
  3. Group DB GRID_* rows by (timestamp ±30s, side-family).
  4. Group exchange fills by same window + side.
  5. For each matched (db-group, fill-group): compute a single multiplier
     = (sum of fill_qty × 5 SOL) / (sum of DB qty). Apply to every row in
     the db-group: qty *= M, pnl *= M.
  6. Rows with no matching fill-group stay untouched (audit-logged).

Read-only by default. Use --apply to write.

Usage:
    scripts/normalize_grid_qty.py            # dry-run
    scripts/normalize_grid_qty.py --apply    # commit changes
"""

import argparse
import os
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from coinbase_exchange import CoinbaseExchange

# SOL PERP contract size
SOL_PER_CONTRACT = 5.0

# Grouping window: trades within 30s on same side are treated as one batch
GROUP_WINDOW_S = 30

# Historical grid period — grid permanently disabled 2026-04-15
HIST_START = 1775731200  # 2026-04-07 00:00 UTC
HIST_END = 1776211200    # 2026-04-14 23:59 UTC (well after last grid activity)


def db_side_to_family(side):
    """Map trade_log side to (side_family, is_close) where side_family is
    the EXCHANGE-facing side that actually filled."""
    s = (side or "").upper()
    # Grid long legs: OPEN via BUY, CLOSE via SELL
    if s == "GRID_BUY":
        return ("BUY", False)
    if s in ("GRID_CLOSE_BUY", "GRID_BUY_TP"):
        return ("SELL", True)   # closing a long = SELL
    # Grid short legs: OPEN via SELL, CLOSE via BUY
    if s == "GRID_SELL":
        return ("SELL", False)
    if s in ("GRID_CLOSE_SELL", "GRID_SELL_TP"):
        return ("BUY", True)    # closing a short = BUY
    return (None, None)


def group_key(ts, side):
    """Bucket timestamps by GROUP_WINDOW_S so batch closes line up."""
    return (int(ts // GROUP_WINDOW_S), side)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/Users/bonnyagent/ibitlabs/sol_sniper.db")
    ap.add_argument("--symbol", default="SLP-20DEC30-CDE")
    ap.add_argument("--apply", action="store_true",
                    help="Commit changes (default: dry-run + print diff)")
    args = ap.parse_args()

    cfg = Config()
    if not cfg.cb_api_key or not cfg.cb_api_secret:
        print("[ERROR] CB_API_KEY / CB_API_SECRET env not set", file=sys.stderr)
        return 2

    try:
        exchange = CoinbaseExchange(cfg.cb_api_key, cfg.cb_api_secret)
    except Exception as e:
        print(f"[ERROR] exchange init failed: {e}", file=sys.stderr)
        return 2

    # ── Load all GRID_* DB rows ──
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT id, timestamp, side, price, quantity, pnl, exit_reason "
        "  FROM trade_log "
        " WHERE side LIKE 'GRID%' AND timestamp BETWEEN ? AND ? "
        " ORDER BY timestamp",
        (HIST_START, HIST_END),
    )
    db_rows = [dict(r) for r in cur.fetchall()]
    con.close()
    print(f"loaded {len(db_rows)} GRID_* rows from DB")

    # ── Fetch exchange fills for the window ──
    print(f"fetching exchange fills {datetime.fromtimestamp(HIST_START)} → "
          f"{datetime.fromtimestamp(HIST_END)}...")
    fills = exchange.list_fills(
        product_id=args.symbol, start_ts=HIST_START, end_ts=HIST_END, limit=250
    )
    print(f"got {len(fills)} exchange fills\n")

    # ── Group both ──
    db_groups = defaultdict(list)
    for r in db_rows:
        family, is_close = db_side_to_family(r["side"])
        if family is None:
            continue
        key = group_key(r["timestamp"], family)
        db_groups[key].append(r)

    fill_groups = defaultdict(list)
    for f in fills:
        key = group_key(f["ts"], f["side"])
        fill_groups[key].append(f)

    # ── Compute changes per group ──
    changes = []
    unmatched_db = []
    for key, rows in db_groups.items():
        if key not in fill_groups:
            # DB group has no matching fill group — likely the orphan we
            # already reconciled, or pre-cleanup residue. Try ±1 bucket
            # for clock-skew.
            bucket, side = key
            neighbor = None
            for off in (-1, 1, -2, 2):
                nk = (bucket + off, side)
                if nk in fill_groups:
                    neighbor = nk
                    break
            if neighbor is None:
                for r in rows:
                    unmatched_db.append(r)
                continue
            key = neighbor

        fs = fill_groups[key]
        total_db_qty = sum(r["quantity"] or 0 for r in rows)
        total_ex_sol = sum((f["quantity"] or 0) * SOL_PER_CONTRACT for f in fs)
        if total_db_qty <= 0 or total_ex_sol <= 0:
            for r in rows:
                unmatched_db.append(r)
            continue
        mult = total_ex_sol / total_db_qty
        for r in rows:
            new_qty = round(r["quantity"] * mult, 6)
            new_pnl = round((r["pnl"] or 0) * mult, 6)
            changes.append({
                "id": r["id"],
                "side": r["side"],
                "ts": r["timestamp"],
                "price": r["price"],
                "old_qty": r["quantity"],
                "new_qty": new_qty,
                "old_pnl": r["pnl"],
                "new_pnl": new_pnl,
                "multiplier": mult,
                "fills_used": [f["fill_id"][:8] for f in fs],
            })

    # ── Print diff ──
    print(f"{'='*92}")
    print(f"PROPOSED NORMALIZATION — {len(changes)} rows would change, "
          f"{len(unmatched_db)} rows have no fill match")
    print(f"{'='*92}")
    print(f"{'id':>4}  {'time':<19} {'side':<17} "
          f"{'price':>7} {'old_qty':>9} {'new_qty':>9} "
          f"{'old_pnl':>8} {'new_pnl':>8} {'x':>5}")
    total_pnl_delta = 0.0
    for c in sorted(changes, key=lambda x: x["ts"]):
        pnl_delta = c["new_pnl"] - (c["old_pnl"] or 0)
        total_pnl_delta += pnl_delta
        t = datetime.fromtimestamp(c["ts"]).strftime("%m-%d %H:%M:%S")
        print(f"{c['id']:>4}  {t:<19} {c['side']:<17} "
              f"{c['price']:>7.2f} {c['old_qty']:>9.3f} {c['new_qty']:>9.3f} "
              f"{(c['old_pnl'] or 0):>+8.2f} {c['new_pnl']:>+8.2f} "
              f"{c['multiplier']:>5.2f}")
    print(f"\ntotal pnl delta: ${total_pnl_delta:+.2f}")
    print(f"(this should absorb ~$13-18 of residual now misclassified as 'funding')")

    if unmatched_db:
        print(f"\n── UNMATCHED DB rows (no change) ──")
        for r in unmatched_db:
            t = datetime.fromtimestamp(r["timestamp"]).strftime("%m-%d %H:%M:%S")
            print(f"  id={r['id']} {t} {r['side']} qty={r['quantity']:.3f}")

    if not args.apply:
        print(f"\n[dry-run] pass --apply to commit changes")
        return 1

    # ── Backup DB, then apply ──
    backup = f"{args.db}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(args.db, backup)
    print(f"\n✅ DB backed up to {backup}")

    # Audit log
    log_dir = os.path.join(os.path.dirname(args.db), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(
        log_dir,
        f"grid_qty_normalize_{datetime.now():%Y%m%d_%H%M%S}.log"
    )
    with open(log_path, "w") as logf:
        logf.write(f"# Grid qty normalization — {datetime.now().isoformat()}\n")
        logf.write(f"# DB: {args.db}\n")
        logf.write(f"# Backup: {backup}\n")
        logf.write(f"# Rows changed: {len(changes)}\n")
        logf.write(f"# PnL delta: ${total_pnl_delta:+.2f}\n\n")
        for c in changes:
            logf.write(
                f"id={c['id']} ts={c['ts']} side={c['side']} price={c['price']} "
                f"qty {c['old_qty']:.6f}→{c['new_qty']:.6f} "
                f"pnl {c['old_pnl']:+.6f}→{c['new_pnl']:+.6f} "
                f"mult={c['multiplier']:.6f} fills={','.join(c['fills_used'])}\n"
            )

    # Apply
    con = sqlite3.connect(args.db)
    cur = con.cursor()
    for c in changes:
        cur.execute(
            "UPDATE trade_log SET quantity = ?, pnl = ? WHERE id = ?",
            (c["new_qty"], c["new_pnl"], c["id"]),
        )
    con.commit()
    con.close()

    print(f"✅ {len(changes)} rows updated")
    print(f"✅ Audit log: {log_path}")
    print(f"✅ Backup: {backup}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
