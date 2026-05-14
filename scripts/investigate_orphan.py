#!/usr/bin/env python3
"""
Investigate a specific DB orphan by reconstructing the real close event
from Coinbase fills history.

Usage:
    scripts/investigate_orphan.py --db-row-id 267

The tool:
  1. Loads the orphan DB row (unclosed open)
  2. Fetches exchange fills in a ±3-day window around that open
  3. Simulates running-position FIFO to identify when the orphan actually
     closed on exchange
  4. Reports proposed reconciliation: close price, close time, realized PnL
  5. With --apply, inserts a reconciliation close row with full audit trail

Read-only unless --apply is passed.
"""

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime

from tz_format import format_utc_edt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from coinbase_exchange import CoinbaseExchange

SOL_PER_CONTRACT = 5.0


def load_db_row(db_path, row_id):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM trade_log WHERE id = ?", (row_id,))
    r = cur.fetchone()
    con.close()
    return dict(r) if r else None


def find_orphan_by_time_price(db_path, ts_approx, price_approx, side_contains):
    """Fallback: find orphan by timestamp + price when id unknown."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM trade_log "
        "WHERE ABS(timestamp - ?) < 300 "
        "  AND ABS(price - ?) < 0.5 "
        "  AND side LIKE ? "
        "ORDER BY timestamp",
        (ts_approx, price_approx, f"%{side_contains}%"),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def reconstruct_close(orphan, fills, direction):
    """
    Given an orphan open (DB row) and a list of exchange fills (sorted by
    time), find the close event. Strategy:

    - orphan open is BUY @ price P, time T, qty Q (in SOL from grid, or
      contracts from sniper)
    - The close must be a SELL after T that either (a) closes net position
      created by this open or (b) is a clear grid-deactivate batch where
      all long legs are closed
    - Prefer: earliest SELL whose cumulative SOL since T >= orphan SOL
    """
    orphan_ts = orphan["timestamp"]
    orphan_price = orphan["price"]
    orphan_qty_raw = orphan["quantity"]
    orphan_side = (orphan["side"] or "").upper()

    # Normalize orphan qty to SOL
    if "GRID" in orphan_side and orphan_qty_raw > 1.0 and \
            abs(orphan_qty_raw - round(orphan_qty_raw)) > 0.01:
        orphan_sol = orphan_qty_raw
    else:
        orphan_sol = orphan_qty_raw * SOL_PER_CONTRACT

    close_side = "SELL" if direction == "long" else "BUY"
    fills_sorted = sorted(fills, key=lambda f: f["ts"])
    # Only consider fills AFTER orphan_ts
    after = [f for f in fills_sorted if f["ts"] > orphan_ts + 30]

    cumulative_sol = 0.0
    matched = []
    for f in after:
        if f["side"] != close_side:
            # Same-side fill after open = cumulative long got bigger; skip
            continue
        qty_sol = f["quantity"] * SOL_PER_CONTRACT
        cumulative_sol += qty_sol
        matched.append(f)
        if cumulative_sol >= orphan_sol - 0.01:  # tolerance
            break

    if cumulative_sol < orphan_sol - 0.01:
        return {
            "close_found": False,
            "reason": f"insufficient {close_side} fills after orphan: "
                      f"found {cumulative_sol:.3f} SOL, need {orphan_sol:.3f}",
            "candidates": matched,
        }

    # Weighted average close price across the matched fills, weighted by the
    # portion of orphan_sol each fill contributes.
    remaining = orphan_sol
    weighted_price_sum = 0.0
    close_ts = matched[0]["ts"]
    for f in matched:
        qty_sol = f["quantity"] * SOL_PER_CONTRACT
        portion = min(qty_sol, remaining)
        weighted_price_sum += f["price"] * portion
        remaining -= portion
        close_ts = f["ts"]  # time of last fill used
        if remaining <= 0.01:
            break
    close_price = weighted_price_sum / orphan_sol

    # Compute realized PnL
    if direction == "long":
        pnl_per_sol = close_price - orphan_price
    else:
        pnl_per_sol = orphan_price - close_price
    realized_pnl = pnl_per_sol * orphan_sol

    return {
        "close_found": True,
        "close_price": close_price,
        "close_ts": close_ts,
        "sol_closed": orphan_sol,
        "realized_pnl": realized_pnl,
        "fills_used": matched,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/Users/bonnyagent/ibitlabs/sol_sniper.db")
    ap.add_argument("--symbol", default="SLP-20DEC30-CDE")
    ap.add_argument("--db-row-id", type=int,
                    help="trade_log id of the orphan open row")
    ap.add_argument("--ts", type=float,
                    help="Alternative: timestamp to search near")
    ap.add_argument("--price", type=float,
                    help="Alternative: price to search near (used with --ts)")
    ap.add_argument("--side-contains", default="BUY",
                    help="Filter side for fallback search (BUY or SELL)")
    ap.add_argument("--apply", action="store_true",
                    help="Insert reconstructed close row (default: report only)")
    args = ap.parse_args()

    cfg = Config()
    if not cfg.cb_api_key or not cfg.cb_api_secret:
        print("[ERROR] CB_API_KEY / CB_API_SECRET not set in env", file=sys.stderr)
        return 2
    exchange = CoinbaseExchange(cfg.cb_api_key, cfg.cb_api_secret)

    # Locate the orphan
    if args.db_row_id:
        orphan = load_db_row(args.db, args.db_row_id)
        if not orphan:
            print(f"[ERROR] no DB row with id={args.db_row_id}", file=sys.stderr)
            return 2
    elif args.ts and args.price:
        candidates = find_orphan_by_time_price(
            args.db, args.ts, args.price, args.side_contains
        )
        if not candidates:
            print(f"[ERROR] no candidate rows near ts={args.ts} "
                  f"price={args.price}", file=sys.stderr)
            return 2
        print(f"Found {len(candidates)} candidate rows:")
        for c in candidates:
            print(f"  id={c['id']} ts={datetime.fromtimestamp(c['timestamp'])} "
                  f"{c['side']} {c['quantity']} @ {c['price']} "
                  f"exit_reason={c['exit_reason']}")
        if len(candidates) != 1:
            print("Specify --db-row-id to pick one", file=sys.stderr)
            return 2
        orphan = candidates[0]
    else:
        print("[ERROR] need either --db-row-id or --ts + --price", file=sys.stderr)
        return 2

    print(f"\n== orphan ==")
    print(f"  id: {orphan['id']}")
    print(f"  time: {datetime.fromtimestamp(orphan['timestamp'])}")
    print(f"  side: {orphan['side']}  price: {orphan['price']}  "
          f"qty: {orphan['quantity']}")
    print(f"  exit_reason: {orphan['exit_reason']}  pnl: {orphan['pnl']}")

    orphan_side = (orphan["side"] or "").upper()
    if "BUY" in orphan_side:
        direction = "long"
    elif "SELL" in orphan_side:
        direction = "short"
    else:
        print("[ERROR] cannot determine direction", file=sys.stderr)
        return 2

    # Fetch fills for a wide window around the orphan
    start_ts = orphan["timestamp"] - 3 * 24 * 3600
    end_ts = orphan["timestamp"] + 4 * 24 * 3600  # 4 days forward should catch close
    print(f"\n== fetching exchange fills ==")
    print(f"  window: {datetime.fromtimestamp(start_ts)} → "
          f"{datetime.fromtimestamp(end_ts)}")
    fills = exchange.list_fills(
        product_id=args.symbol, start_ts=start_ts, end_ts=end_ts, limit=250
    )
    print(f"  {len(fills)} fills")

    result = reconstruct_close(orphan, fills, direction)

    if not result["close_found"]:
        print(f"\n❌ could not reconstruct close: {result['reason']}")
        print(f"  candidates found: {len(result['candidates'])}")
        for f in result["candidates"]:
            print(f"    {datetime.fromtimestamp(f['ts'])} {f['side']} "
                  f"{f['quantity']:.1f} @ {f['price']:.2f}")
        return 1

    print(f"\n✅ close reconstructed")
    print(f"  close time: {datetime.fromtimestamp(result['close_ts'])}")
    print(f"  close price (weighted avg): ${result['close_price']:.4f}")
    print(f"  SOL closed: {result['sol_closed']:.3f}")
    print(f"  realized PnL: ${result['realized_pnl']:+.2f}")
    print(f"  exchange fills used:")
    for f in result["fills_used"]:
        print(f"    {datetime.fromtimestamp(f['ts'])} {f['side']} "
              f"{f['quantity']:.1f} @ ${f['price']:.2f}  "
              f"order={f['order_id'][:8]}")

    if not args.apply:
        print(f"\n[report-only] pass --apply to insert reconciliation close row")
        return 1

    # Apply: insert close row
    orig_side = orphan_side
    if orig_side == "GRID_BUY":
        close_side = "GRID_CLOSE_BUY"
    elif orig_side == "GRID_SELL":
        close_side = "GRID_CLOSE_SELL"
    elif orig_side == "BUY":
        close_side = "SELL"
    elif orig_side == "SELL":
        close_side = "BUY"
    else:
        close_side = "RECONCILE_CLOSE"

    notes = (
        f"Orphan reconciled {format_utc_edt()} from exchange fills: "
        f"DB open id={orphan['id']} ({orig_side} @ {orphan['price']}) had no "
        f"matching close. Exchange fills show real close at "
        f"{datetime.fromtimestamp(result['close_ts'])} — weighted avg "
        f"${result['close_price']:.4f}. "
        f"Realized PnL ${result['realized_pnl']:+.2f}. "
        f"Fill IDs: {','.join(f['fill_id'][:8] for f in result['fills_used'])}"
    )

    con = sqlite3.connect(args.db)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO trade_log "
        "  (symbol, side, price, quantity, usdt_value, pnl, timestamp, "
        "   direction, entry_price, exit_price, exit_reason, strategy_intent, "
        "   instance_name, trigger_rule) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            orphan["symbol"],
            close_side,
            result["close_price"],
            orphan["quantity"],
            result["close_price"] * orphan["quantity"],
            result["realized_pnl"],
            result["close_ts"],
            direction,
            orphan["price"],
            result["close_price"],
            "reconciler_orphan_close_reconstructed",
            orphan["strategy_intent"],
            orphan["instance_name"],
            notes,
        ),
    )
    con.commit()
    new_id = cur.lastrowid
    con.close()

    print(f"\n✅ inserted close row id={new_id}")
    print(f"  exit_reason=reconciler_orphan_close_reconstructed")
    print(f"  trigger_rule contains full audit trail")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
