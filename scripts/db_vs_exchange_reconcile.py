#!/usr/bin/env python3
"""
DB ↔ Exchange reconciler.

Compares local trade_log against Coinbase fills. Catches two silent failure
modes that backtest_vs_paper_reconcile does NOT see:

  (1) Orphan DB record: DB logged open/close but exchange has no matching fill
      → the bot recorded intent but the order never executed
  (2) Missing DB record: exchange fill exists but DB has no row
      → the bot filled but never logged (could be partial fill, restart crash,
        or close-handler that never ran)

Read-only by default. Pass --apply to insert reconciliation rows into DB.

Exit codes:
  0 — clean (no discrepancies)
  1 — discrepancies found (report only unless --apply)
  2 — script error (API down, etc.)

Usage:
    scripts/db_vs_exchange_reconcile.py --days 7
    scripts/db_vs_exchange_reconcile.py --days 7 --apply
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

from tz_format import format_utc_edt

STATE_FILE = "/Users/bonnyagent/ibitlabs/state/reconciliation_status.json"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from coinbase_exchange import CoinbaseExchange


PRICE_TOLERANCE = 0.20   # $0.20/SOL — ticker vs fill drift ($0.02-0.10 common)
QTY_TOLERANCE_PCT = 0.10 # 10% — DB/exchange qty unit mismatch is structural
TIME_TOLERANCE_S = 180   # ±3min for fill-to-DB timestamp match

# DB records ambient cleanup window: 2026-04-13 clearing of 149 old-format rows.
# Anything before this is historically known-lossy. Ongoing alerts should
# only fire for drift AFTER this timestamp.
POST_CLEANUP_TS = 1776079000  # 2026-04-13 ~14:00 UTC, after the mass deletion

# SOL PERP contract: 1 contract = 5 SOL. DB grid records store qty as SOL
# amount (e.g. 3.485). Exchange fills store qty as contracts (e.g. 1.0).
# Convert both to SOL for comparison.
SOL_PER_CONTRACT = 5.0


def fetch_db_trades(db_path, start_ts, end_ts):
    """Return list of DB trade rows with canonical fields."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT id, timestamp, symbol, side, price, quantity, exit_reason, "
        "       pnl, strategy_intent, instance_name "
        "  FROM trade_log "
        " WHERE timestamp BETWEEN ? AND ? "
        " ORDER BY timestamp",
        (start_ts, end_ts),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def fetch_exchange_fills(exchange, product_id, start_ts, end_ts):
    """Fetch all fills in window (paginated if needed)."""
    # The SDK may cap per request; we just ask for the window once at
    # limit=250 which covers typical 7-day volume.
    fills = exchange.list_fills(
        product_id=product_id, start_ts=start_ts, end_ts=end_ts, limit=250
    )
    return fills


def classify_db_side(row):
    """Map DB side labels to canonical OPEN|CLOSE + direction.

    side conventions in trade_log:
      'BUY'              — sniper long open
      'SELL'             — sniper long close (via trailing/tp/sl)
      'GRID_BUY'         — grid long level opened
      'GRID_CLOSE_BUY'   — grid long level closed
      'GRID_BUY_TP'      — grid long level hit internal TP
      'GRID_SELL'        — grid short level opened
      'GRID_CLOSE_SELL'  — grid short level closed
      'GRID_SELL_TP'     — grid short level hit internal TP
    """
    side = (row["side"] or "").upper()
    exit_reason = (row["exit_reason"] or "").lower()
    # Opens generally have no exit_reason; closes carry one
    if side in ("BUY",):
        return ("OPEN", "long") if not exit_reason else ("CLOSE", "short")
    if side in ("SELL",):
        return ("CLOSE", "long") if exit_reason else ("OPEN", "short")
    if side == "GRID_BUY":
        return ("OPEN", "long")
    if side == "GRID_SELL":
        return ("OPEN", "short")
    if side in ("GRID_CLOSE_BUY", "GRID_BUY_TP"):
        return ("CLOSE", "long")
    if side in ("GRID_CLOSE_SELL", "GRID_SELL_TP"):
        return ("CLOSE", "short")
    return ("UNKNOWN", "unknown")


def normalize_qty_to_sol(qty, side_label):
    """Convert qty to SOL units.

    Sniper DB rows store qty as contracts (integer, usually 1.0).
    Grid DB rows store qty as SOL amount (fractional, e.g. 3.485).
    Exchange fills store qty as contracts (integer, e.g. 1.0).

    Heuristic: integer qty ≤ 10 → contracts (convert to SOL).
    Fractional qty ≥ 1.0 → already in SOL.
    """
    side = (side_label or "").upper()
    if "GRID" in side and qty > 1.0 and abs(qty - round(qty)) > 0.01:
        # Fractional grid qty — treat as SOL already
        return qty
    # Integer qty — treat as contracts, convert to SOL
    return qty * SOL_PER_CONTRACT


def match_fill_to_db(fill, db_rows, used_ids):
    """Find a DB row matching this fill. Returns DB row or None.

    Match: same side + price within PRICE_TOLERANCE + ts within TIME_TOLERANCE
    + qty within QTY_TOLERANCE_PCT (after normalizing to SOL).
    """
    fill_side = fill["side"]
    fill_price = fill["price"]
    fill_qty_sol = fill["quantity"] * SOL_PER_CONTRACT  # exchange reports contracts
    fill_ts = fill["ts"]

    for r in db_rows:
        if r["id"] in used_ids:
            continue
        if abs((r["price"] or 0) - fill_price) > PRICE_TOLERANCE:
            continue
        if abs((r["timestamp"] or 0) - fill_ts) > TIME_TOLERANCE_S:
            continue
        db_side = (r["side"] or "").upper()
        if fill_side == "BUY" and "BUY" not in db_side:
            continue
        if fill_side == "SELL" and "SELL" not in db_side:
            continue
        r_qty_sol = normalize_qty_to_sol(r["quantity"] or 0, db_side)
        if abs(r_qty_sol - fill_qty_sol) / max(fill_qty_sol, 0.001) > QTY_TOLERANCE_PCT:
            continue
        return r
    return None


def insert_reconciliation_row(db_path, orphan, reason_code, notes):
    """Insert a zero-pnl close row to pair with an orphan open."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    # Build complementary side: GRID_BUY → GRID_CLOSE_BUY, GRID_SELL → GRID_CLOSE_SELL
    orig_side = (orphan["side"] or "").upper()
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
    # Timestamp: use original + 1 second to ensure ordering
    close_ts = (orphan["timestamp"] or 0) + 1.0
    cur.execute(
        "INSERT INTO trade_log "
        "  (symbol, side, price, quantity, usdt_value, pnl, timestamp, "
        "   direction, exit_price, exit_reason, strategy_intent, "
        "   instance_name, trigger_rule) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            orphan["symbol"],
            close_side,
            orphan["price"],             # same price = 0 PnL
            orphan["quantity"],
            (orphan["price"] or 0) * (orphan["quantity"] or 0),
            0.0,
            close_ts,
            None,
            orphan["price"],
            reason_code,
            orphan["strategy_intent"],
            orphan["instance_name"],
            notes,
        ),
    )
    con.commit()
    new_id = cur.lastrowid
    con.close()
    return new_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/Users/bonnyagent/ibitlabs/sol_sniper.db")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--symbol", default="SLP-20DEC30-CDE")
    ap.add_argument(
        "--apply", action="store_true",
        help="Insert reconciliation rows for orphans (default: report only)",
    )
    ap.add_argument(
        "--diagnose", action="store_true",
        help="List portfolios + probe each for recent fills. Use when get_fills "
             "returns stale/partial data to find the right retail_portfolio_id.",
    )
    args = ap.parse_args()

    cfg = Config()
    if not cfg.cb_api_key or not cfg.cb_api_secret:
        print("[ERROR] CB_API_KEY / CB_API_SECRET not set in env", file=sys.stderr)
        return 2

    try:
        exchange = CoinbaseExchange(cfg.cb_api_key, cfg.cb_api_secret)
    except Exception as e:
        print(f"[ERROR] exchange init failed: {e}", file=sys.stderr)
        return 2

    if args.diagnose:
        print("== portfolio diagnostic ==")
        try:
            resp = exchange.client.get_portfolios()
            raw = resp if isinstance(resp, dict) else vars(resp)
            portfolios = raw.get("portfolios", [])
            print(f"  found {len(portfolios)} portfolio(s)")
            for p in portfolios:
                pd = p if isinstance(p, dict) else vars(p)
                print(f"    uuid={pd.get('uuid')} name={pd.get('name')} "
                      f"type={pd.get('type')} deleted={pd.get('deleted')}")
        except Exception as e:
            print(f"  [ERR] get_portfolios: {e}")
        # Probe fills for last 3 days across all portfolios (default) and
        # each one individually to see which has the recent data.
        probe_end = time.time()
        probe_start = probe_end - 3 * 24 * 3600
        print(f"\n  probing fills for {args.symbol} last 3 days...")
        print("  (a) no portfolio filter (default):")
        f0 = exchange.list_fills(product_id=args.symbol,
                                 start_ts=probe_start, end_ts=probe_end)
        print(f"    → {len(f0)} fills")
        if f0:
            latest = max(f0, key=lambda x: x["ts"])
            print(f"    → latest: {datetime.fromtimestamp(latest['ts'])} "
                  f"{latest['side']} {latest['quantity']} @ {latest['price']}")
        try:
            for p in portfolios:
                pd = p if isinstance(p, dict) else vars(p)
                puuid = pd.get("uuid")
                if not puuid:
                    continue
                resp = exchange.client.get_fills(
                    product_ids=[args.symbol],
                    start_sequence_timestamp=datetime.utcfromtimestamp(probe_start).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    end_sequence_timestamp=datetime.utcfromtimestamp(probe_end).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    retail_portfolio_id=puuid,
                    limit=50,
                )
                r = resp if isinstance(resp, dict) else vars(resp)
                fls = r.get("fills", []) or []
                print(f"  (b) portfolio {pd.get('name')} ({puuid[:8]}): {len(fls)} fills")
                if fls:
                    latest = fls[0] if not isinstance(fls[0], dict) else fls[0]
                    latest = latest if isinstance(latest, dict) else vars(latest)
                    print(f"    → latest: trade_time={latest.get('trade_time')} "
                          f"side={latest.get('side')} size={latest.get('size')} "
                          f"price={latest.get('price')}")
        except Exception as e:
            print(f"  [ERR] per-portfolio probe: {e}")
        return 0

    end_ts = time.time()
    start_ts = end_ts - args.days * 24 * 3600

    print(f"== DB↔Exchange reconcile ==")
    print(f"  window: {datetime.fromtimestamp(start_ts):%Y-%m-%d %H:%M} → "
          f"{datetime.fromtimestamp(end_ts):%Y-%m-%d %H:%M}")
    print(f"  db: {args.db}")
    print(f"  symbol: {args.symbol}")

    db_rows = fetch_db_trades(args.db, start_ts, end_ts)
    try:
        fills = fetch_exchange_fills(exchange, args.symbol, start_ts, end_ts)
    except Exception as e:
        print(f"[ERROR] fills fetch failed: {e}", file=sys.stderr)
        return 2

    print(f"  db rows: {len(db_rows)}")
    print(f"  exchange fills: {len(fills)}")

    # Pass 1: match each fill to a DB row
    used_db_ids = set()
    unmatched_fills = []
    for f in fills:
        matched = match_fill_to_db(f, db_rows, used_db_ids)
        if matched:
            used_db_ids.add(matched["id"])
        else:
            unmatched_fills.append(f)

    # Pass 2: FIFO-pair opens with closes WITHIN DB itself to find truly
    # unpaired opens. "net opens - closes" is wrong because a close in the
    # window may have paired with an open BEFORE the window.
    opens_long = sorted(
        [r for r in db_rows if classify_db_side(r) == ("OPEN", "long")],
        key=lambda x: x["timestamp"],
    )
    opens_short = sorted(
        [r for r in db_rows if classify_db_side(r) == ("OPEN", "short")],
        key=lambda x: x["timestamp"],
    )
    closes_long = sorted(
        [r for r in db_rows if classify_db_side(r) == ("CLOSE", "long")],
        key=lambda x: x["timestamp"],
    )
    closes_short = sorted(
        [r for r in db_rows if classify_db_side(r) == ("CLOSE", "short")],
        key=lambda x: x["timestamp"],
    )

    # FIFO: each close consumes the oldest unclosed open. Remaining opens are
    # orphan candidates (exclude the currently-live position which is a valid
    # unclosed open by design).
    def fifo_unpaired(opens, closes):
        o_remain = list(opens)
        for c in closes:
            if not o_remain:
                break
            o_remain.pop(0)
        return o_remain

    unpaired_longs = fifo_unpaired(opens_long, closes_long)
    unpaired_shorts = fifo_unpaired(opens_short, closes_short)

    # Strip the most-recent unpaired open if it matches the live position
    # (since a live open position correctly has no close yet).
    import json as _json
    try:
        with open("/Users/bonnyagent/ibitlabs/sol_sniper_state.json") as _sf:
            _live = _json.load(_sf).get("position") or {}
    except Exception:
        _live = {}
    if _live and unpaired_longs and _live.get("direction") == "long":
        if abs((_live.get("entry_price", 0) or 0) - unpaired_longs[-1]["price"]) < PRICE_TOLERANCE:
            unpaired_longs = unpaired_longs[:-1]
    if _live and unpaired_shorts and _live.get("direction") == "short":
        if abs((_live.get("entry_price", 0) or 0) - unpaired_shorts[-1]["price"]) < PRICE_TOLERANCE:
            unpaired_shorts = unpaired_shorts[:-1]

    orphan_candidates = unpaired_longs + unpaired_shorts

    # Orphans are opens whose open-fill did exist on exchange (if no fill, the
    # open itself is the orphan — even worse). We separate them for clarity.
    orphans_with_fill = []
    orphans_without_fill = []
    for op in orphan_candidates:
        # Did a fill for this open exist on the exchange?
        fake_fill = {
            "side": "BUY" if "BUY" in (op["side"] or "").upper() else "SELL",
            "price": op["price"],
            "quantity": op["quantity"],
            "ts": op["timestamp"],
        }
        # Can't use match_fill_to_db (takes a real exchange fill);
        # just scan fills list instead.
        found = False
        for f in fills:
            if abs(f["price"] - op["price"]) > PRICE_TOLERANCE:
                continue
            if abs(f["quantity"] - op["quantity"]) / max(op["quantity"], 0.001) > QTY_TOLERANCE:
                continue
            if abs(f["ts"] - op["timestamp"]) > TIME_TOLERANCE_S:
                continue
            if f["side"] != fake_fill["side"]:
                continue
            found = True
            break
        if found:
            orphans_with_fill.append(op)  # fill happened but close missing
        else:
            orphans_without_fill.append(op)  # neither happened on exchange

    # Split unmatched into pre/post DB-cleanup (2026-04-13 ~14:00). The pre-
    # cleanup bucket is historically lossy (149 old-format rows were deleted
    # that day). Only the post-cleanup bucket should alert.
    unmatched_pre = [f for f in unmatched_fills if f["ts"] < POST_CLEANUP_TS]
    unmatched_post = [f for f in unmatched_fills if f["ts"] >= POST_CLEANUP_TS]

    print()
    print(f"  DB opens (FIFO unpaired after closes): "
          f"long={len(unpaired_longs)}, short={len(unpaired_shorts)}")
    if _live:
        print(f"  live position (excluded from orphans): {_live.get('direction')} "
              f"@ {_live.get('entry_price')}")
    print(f"  unmatched exchange fills: {len(unmatched_fills)} total")
    print(f"    pre-cleanup (before 2026-04-13 14:00): "
          f"{len(unmatched_pre)} — historical, from 4/13 mass deletion of 149 rows")
    print(f"    post-cleanup (ongoing): {len(unmatched_post)} — real drift signal")
    print(f"  DB orphans WITHOUT matching exchange fill: {len(orphans_without_fill)}")
    print(f"  DB orphans WITH matching exchange fill (close missing): {len(orphans_with_fill)}")

    # Write structured status file for dashboard consumption. Split pre/post
    # cleanup so dashboard can differentiate historical residue from ongoing
    # drift. "clean" only considers post-cleanup drift + live orphans.
    status_payload = {
        "last_run_ts": time.time(),
        "last_run_iso": datetime.now().isoformat(timespec="seconds"),
        "window_days": args.days,
        "db_rows": len(db_rows),
        "exchange_fills": len(fills),
        "unmatched_fills_total": len(unmatched_fills),
        "unmatched_pre_cleanup": len(unmatched_pre),
        "unmatched_post_cleanup": len(unmatched_post),
        "orphans_no_fill": len(orphans_without_fill),
        "orphans_with_fill": len(orphans_with_fill),
        "clean": not (unmatched_post or orphans_without_fill or orphans_with_fill),
        "apply_mode": args.apply,
    }
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(status_payload, f, indent=2)
    except Exception as e:
        print(f"[WARN] could not write state file: {e}", file=sys.stderr)

    if not (unmatched_fills or orphans_without_fill or orphans_with_fill):
        print("\n✅ clean — no discrepancies")
        return 0

    print("\n── discrepancies ──")

    # Report unmatched fills
    for f in unmatched_fills:
        ts = datetime.fromtimestamp(f["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  EXCHANGE-ONLY  {ts} {f['side']:4s} {f['quantity']:.3f} @ "
              f"{f['price']:.2f}  order={f['order_id'][:8]}  fill={f['fill_id'][:8]}")

    # Report orphans without fill (intent-only)
    for op in orphans_without_fill:
        ts = datetime.fromtimestamp(op["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  DB-ONLY NOFILL {ts} {op['side']:16s} {op['quantity']:.3f} "
              f"@ {op['price']:.2f}  id={op['id']}")

    # Report orphans with fill (close missing — more serious)
    for op in orphans_with_fill:
        ts = datetime.fromtimestamp(op["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  DB-ONLY FILLED {ts} {op['side']:16s} {op['quantity']:.3f} "
              f"@ {op['price']:.2f}  id={op['id']} "
              f"⚠ exchange fill exists but DB never recorded the close")

    if not args.apply:
        print("\n[report-only] pass --apply to insert reconciliation rows")
        return 1

    # Apply mode: insert zero-PnL closes for orphans-without-fill
    print("\n── applying reconciliations ──")
    applied = 0
    for op in orphans_without_fill:
        reason = "reconciler_orphan_no_fill"
        notes = (
            f"Orphan reconciled {format_utc_edt()}: "
            f"DB {op['side']} recorded @ {op['timestamp']} never filled on exchange "
            f"(confirmed via fills API, window {args.days}d). "
            f"Zero-PnL close inserted to preserve FIFO pairing."
        )
        new_id = insert_reconciliation_row(args.db, op, reason, notes)
        print(f"  inserted close row id={new_id} for orphan id={op['id']}")
        applied += 1

    for op in orphans_with_fill:
        # These need manual review — we don't know the close price
        print(f"  ⚠ SKIP orphan id={op['id']} (had fill) — needs manual review "
              f"to find actual close price & time")

    for f in unmatched_fills:
        # Missing DB records for real exchange fills
        print(f"  ⚠ SKIP unmatched fill order={f['order_id'][:8]} — "
              f"needs manual review to add open+close pair")

    if applied:
        print(f"\n✅ {applied} reconciliation row(s) inserted")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
