#!/usr/bin/env python3
"""
Breakout Sniper SPOT v0.1 — paper bot.

NEW strategy family (NOT a v5.3 or pump_sniper variant). Trend-following
breakout instead of mean-reversion.

Trigger : 15m bar where ALL 6 conditions met (breakout v0.1, long-side only):
            b1  StochRSI > 0.90        (overbought = continuation)
            b2  price >= BB upper       (broken volatility band)
            b3  vol_ratio >= 1.5x       (false-breakout protection)
            b4  1H trend == up          (medium-TF aligned)
            b5  4H trend == up          (higher-TF aligned)
            b6  15m momentum >= +0.5%   (price moving in direction)
Exit    : 24h time-stop OR trailing (activate 0.4%, stop 0.5%) OR -3% SL
Sizing  : top10 → $200, 11-20 → $100  (paper, shared universe with pump_sniper)
Concur  : ≤ 5 open positions (24h holds saturate quickly)
Cooldown: 24h per symbol after fire (one breakout = one entry)

Phase 0 backtest (2026-05-19, 30 syms × 90d):
  PF = 2.05, sym+ = 19/20, n = 805
  exit mix: 705 trailing / 90 SL / 10 timeout
  Decision gate PASSED.

Paper accounting model identical to pump_sniper_spot:
  - No real orders
  - Fetches REAL Coinbase L2 orderbook at fire and exit, walks book for fill
  - Coinbase One assumption: fee = 0% maker/taker

Universe: shared `pump_sniper_spot_universe.json` (weekly refresh).

Driven by launchd `com.ibitlabs.breakout-sniper-spot-v01` at StartInterval=60s.

State     : /Users/bonnyagent/ibitlabs/state/breakout_sniper_spot_v01.json
Log       : /Users/bonnyagent/ibitlabs/logs/breakout_sniper_spot_v01.jsonl
Dashboard : /Users/bonnyagent/ibitlabs/web/public/data/breakout_sniper_spot_v01.json
"""
import json
import os
import sys
import time
import urllib.request

# Indicators + 4h resampler live in the backtest module
sys.path.insert(0, '/Users/bonnyagent/ibitlabs')
from backfill_miss_rate_90d import (
    stoch_rsi, bollinger, vol_ratio, short_momentum, trend_state,
    resample_1h_to_4h,
    BB_PERIOD, BB_STD, MOMENTUM_CANDLES,
)

UNIVERSE_PATH_SRC = "/Users/bonnyagent/ibitlabs/state/pump_sniper_spot_universe.json"

FALLBACK_UNIVERSE = [
    ("BTC-USD",   1, 200), ("ETH-USD",   2, 200), ("XRP-USD",   3, 200),
    ("SOL-USD",   4, 200), ("ZEC-USD",   5, 200), ("DOGE-USD",  6, 200),
    ("SUI-USD",   7, 200), ("LINK-USD",  8, 200), ("HYPE-USD",  9, 200),
    ("TAO-USD",  10, 200),
    ("ONDO-USD", 11, 100), ("RAVE-USD", 12, 100), ("ADA-USD",  13, 100),
    ("VVV-USD",  14, 100), ("PENGU-USD",15, 100), ("BILL-USD", 16, 100),
    ("LTC-USD",  17, 100), ("XLM-USD",  18, 100), ("PEPE-USD", 19, 100),
    ("HBAR-USD", 20, 100),
]


def _load_universe():
    if not os.path.exists(UNIVERSE_PATH_SRC):
        return FALLBACK_UNIVERSE
    try:
        with open(UNIVERSE_PATH_SRC) as f:
            d = json.load(f)
        return [(u["symbol"], u["rank"], u["size_usd"]) for u in d["universe"]]
    except Exception:
        return FALLBACK_UNIVERSE


UNIVERSE = _load_universe()

# ── Breakout v0.1 trigger params (same as backtest) ─────────────────────
BO_STOCH_LONG    = 0.90
BO_VOL_MULT      = 1.5
BO_MOM_MIN_ALIGN = 0.005

# ── Exit envelope (same as backtest) ───────────────────────────────────
TRAIL_ACTIVATE   = 0.004
TRAIL_STOP       = 0.005
SL               = 0.03
HOLD_SEC         = 24 * 3600
COOLDOWN_SEC     = HOLD_SEC

MAX_CONCURRENT   = 5

STATE_PATH    = "/Users/bonnyagent/ibitlabs/state/breakout_sniper_spot_v01.json"
LOG_PATH      = "/Users/bonnyagent/ibitlabs/logs/breakout_sniper_spot_v01.jsonl"
DASHBOARD_PATH = "/Users/bonnyagent/ibitlabs/web/public/data/breakout_sniper_spot_v01.json"

PROMOTE_GATE = 30


def fetch_candles(product, granularity_sec, lookback_sec):
    end = int(time.time())
    start = end - lookback_sec
    url = (f"https://api.exchange.coinbase.com/products/{product}/candles"
           f"?granularity={granularity_sec}&start={start}&end={end}")
    req = urllib.request.Request(url, headers={"User-Agent": "M/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        # Coinbase row: [time, low, high, open, close, volume]
        rows = [(row[0], row[3], row[2], row[1], row[4], row[5]) for row in data]
        rows.sort(key=lambda x: x[0])
        return rows
    except Exception:
        return None


def fetch_book(product):
    url = f"https://api.exchange.coinbase.com/products/{product}/book?level=2"
    req = urllib.request.Request(url, headers={"User-Agent": "M/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            book = json.loads(r.read())
        if not book.get("bids") or not book.get("asks"):
            return None
        best_bid = float(book["bids"][0][0])
        best_ask = float(book["asks"][0][0])
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid": (best_bid + best_ask) / 2,
            "bids": [(float(p), float(q)) for p, q, *_ in book["bids"]],
            "asks": [(float(p), float(q)) for p, q, *_ in book["asks"]],
        }
    except Exception:
        return None


def buy_fill(book, size_usd):
    spent, qty = 0.0, 0.0
    for price, qty_lvl in book["asks"]:
        level_quote = price * qty_lvl
        if spent + level_quote >= size_usd:
            need = size_usd - spent
            qty += need / price
            spent = size_usd
            break
        spent += level_quote
        qty += qty_lvl
    if spent < size_usd:
        return None
    avg = size_usd / qty
    return {"fill_price": avg, "qty": qty,
            "slip_pct": (avg - book["mid"]) / book["mid"] * 100}


def sell_fill(book, qty):
    received, sold = 0.0, 0.0
    for price, qty_lvl in book["bids"]:
        if sold + qty_lvl >= qty:
            need = qty - sold
            received += need * price
            sold = qty
            break
        received += price * qty_lvl
        sold += qty_lvl
    if sold < qty:
        return None
    avg = received / qty
    return {"fill_price": avg, "received_usd": received,
            "slip_pct": (book["mid"] - avg) / book["mid"] * 100}


def eval_breakout(bars_15m, bars_1h):
    """Evaluate all 6 b-conditions at the LATEST closed 15m bar.
    Returns dict with signal data + 'fires' bool. None if insufficient bars."""
    if len(bars_15m) < BB_PERIOD + 2:
        return None
    if len(bars_1h) < 24:
        return None
    bars_4h = resample_1h_to_4h(bars_1h)
    if len(bars_4h) < 24:
        return None

    closes_15m = [b[4] for b in bars_15m]
    vols_15m   = [b[5] for b in bars_15m]
    closes_1h  = [b[4] for b in bars_1h]
    closes_4h  = [b[4] for b in bars_4h]

    price = closes_15m[-1]
    stoch = stoch_rsi(closes_15m)
    bb_u, _, _ = bollinger(closes_15m, BB_PERIOD, BB_STD)
    vr = vol_ratio(vols_15m)
    mom = short_momentum(closes_15m, MOMENTUM_CANDLES)
    t1h = trend_state(closes_1h)
    t4h = trend_state(closes_4h)

    conds = {
        "b1_stoch_high": stoch > BO_STOCH_LONG,
        "b2_bb_above":   price >= bb_u,
        "b3_vol_strong": vr >= BO_VOL_MULT,
        "b4_1h_up":      t1h == "up",
        "b5_4h_up":      t4h == "up",
        "b6_mom_align":  mom >= BO_MOM_MIN_ALIGN,
    }
    fires = all(conds.values())
    return {
        "fires": fires, "ts": bars_15m[-1][0], "price": price,
        "stoch": round(stoch, 3), "bb_upper": round(bb_u, 6),
        "vol_ratio": round(vr, 2), "mom_pct": round(mom * 100, 3),
        "t1h": t1h, "t4h": t4h,
        "conds_met": sum(1 for v in conds.values() if v),
    }


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"positions": [], "last_fire": {},
                "cumulative": {"trades": 0, "wins": 0, "net_usd": 0.0,
                               "fires_attempted": 0, "fires_filled": 0}}
    with open(STATE_PATH) as f:
        return json.load(f)


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def log_event(event):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")


def manage_exits(state, now):
    new_positions = []
    for pos in state["positions"]:
        sym = pos["symbol"]
        book = fetch_book(sym)
        if not book:
            new_positions.append(pos)
            continue
        mid = book["mid"]
        cur_pnl = (mid - pos["entry_fill"]) / pos["entry_fill"]
        if cur_pnl > pos["highest_pnl"]:
            pos["highest_pnl"] = cur_pnl
        if pos["highest_pnl"] >= TRAIL_ACTIVATE:
            pos["trail_armed"] = True
        elapsed = now - pos["entry_ts"]

        exit_reason = None
        if cur_pnl <= -SL:
            exit_reason = "sl"
        elif pos["trail_armed"] and (pos["highest_pnl"] - cur_pnl) >= TRAIL_STOP:
            exit_reason = "trailing"
        elif elapsed >= HOLD_SEC:
            exit_reason = "timeout"

        if not exit_reason:
            new_positions.append(pos)
            continue

        fill = sell_fill(book, pos["qty"])
        if not fill:
            new_positions.append(pos)
            continue
        received = fill["received_usd"]
        gross_pnl_usd = received - pos["size_usd"]
        gross_pnl_pct = gross_pnl_usd / pos["size_usd"]
        log_event({
            "ts": now, "kind": "EXIT", "symbol": sym, "rank": pos["rank"],
            "entry_ts": pos["entry_ts"], "exit_ts": now, "elapsed_sec": elapsed,
            "entry_fill": pos["entry_fill"], "exit_fill": fill["fill_price"],
            "entry_slip_pct": pos["entry_slip_pct"], "exit_slip_pct": fill["slip_pct"],
            "qty": pos["qty"], "size_usd": pos["size_usd"],
            "received_usd": received,
            "highest_pnl_pct": pos["highest_pnl"] * 100,
            "gross_pnl_usd": gross_pnl_usd, "gross_pnl_pct": gross_pnl_pct * 100,
            "exit_reason": exit_reason,
            "trigger_stoch": pos.get("trigger_stoch"),
            "trigger_vol_ratio": pos.get("trigger_vol_ratio"),
            "trigger_mom_pct": pos.get("trigger_mom_pct"),
        })
        state["cumulative"]["trades"] += 1
        if gross_pnl_usd > 0:
            state["cumulative"]["wins"] += 1
        state["cumulative"]["net_usd"] += gross_pnl_usd
    state["positions"] = new_positions


def scan_entries(state, now):
    for sym, rank, size_usd in UNIVERSE:
        if len(state["positions"]) >= MAX_CONCURRENT:
            break
        if any(p["symbol"] == sym for p in state["positions"]):
            continue
        last = state["last_fire"].get(sym, 0)
        if now - last < COOLDOWN_SEC:
            continue

        # Fetch 15m (2d=192 bars) + 1h (10d=240 bars; Coinbase 300-row cap).
        # 10d × 1h → 60 4h bars after resample, > eval_breakout's 24-bar floor.
        bars_15m = fetch_candles(sym, 900, 60 * 60 * 24 * 2)
        bars_1h  = fetch_candles(sym, 3600, 60 * 60 * 24 * 10)
        if not bars_15m or not bars_1h:
            continue

        sig = eval_breakout(bars_15m, bars_1h)
        if not sig or not sig["fires"]:
            continue

        state["cumulative"]["fires_attempted"] += 1
        book = fetch_book(sym)
        if not book:
            continue
        fill = buy_fill(book, size_usd)
        if not fill:
            continue

        state["cumulative"]["fires_filled"] += 1
        pos = {
            "symbol": sym, "rank": rank, "size_usd": size_usd,
            "entry_ts": now, "entry_mid": book["mid"],
            "entry_fill": fill["fill_price"], "entry_slip_pct": fill["slip_pct"],
            "qty": fill["qty"],
            "trigger_stoch": sig["stoch"],
            "trigger_vol_ratio": sig["vol_ratio"],
            "trigger_mom_pct": sig["mom_pct"],
            "trigger_t1h": sig["t1h"], "trigger_t4h": sig["t4h"],
            "highest_pnl": 0.0, "trail_armed": False,
        }
        state["positions"].append(pos)
        state["last_fire"][sym] = now
        log_event({
            "ts": now, "kind": "ENTRY", "symbol": sym, "rank": rank,
            "size_usd": size_usd,
            "trigger": "breakout_v01 (b1-b6 all)",
            "trigger_signal": sig,
            "entry_mid": book["mid"], "entry_fill": fill["fill_price"],
            "entry_slip_pct": fill["slip_pct"], "qty": fill["qty"],
        })


def read_all_exits():
    if not os.path.exists(LOG_PATH):
        return []
    exits = []
    with open(LOG_PATH) as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("kind") == "EXIT":
                exits.append(e)
    return exits


def compute_per_symbol(all_exits):
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "wins": 0, "net_usd": 0.0,
                                "entry_slip_sum": 0.0, "exit_slip_sum": 0.0})
    for e in all_exits:
        sym = e["symbol"]
        d = agg[sym]
        d["n"] += 1
        if e.get("gross_pnl_usd", 0) > 0:
            d["wins"] += 1
        d["net_usd"] += e.get("gross_pnl_usd", 0) or 0
        d["entry_slip_sum"] += e.get("entry_slip_pct", 0) or 0
        d["exit_slip_sum"] += e.get("exit_slip_pct", 0) or 0
    out = {}
    for sym, d in agg.items():
        out[sym] = {
            "n": d["n"], "wins": d["wins"],
            "wr_pct": d["wins"] / d["n"] * 100 if d["n"] else None,
            "net_usd": round(d["net_usd"], 2),
            "avg_entry_slip_pct": round(d["entry_slip_sum"] / d["n"], 3) if d["n"] else None,
            "avg_exit_slip_pct": round(d["exit_slip_sum"] / d["n"], 3) if d["n"] else None,
        }
    return out


def write_dashboard(state, now):
    cum = state["cumulative"]
    n = cum["trades"]
    wr_pct = cum["wins"] / n * 100 if n else None
    all_exits = read_all_exits()
    wins_usd = sum(e.get("gross_pnl_usd", 0) for e in all_exits if e.get("gross_pnl_usd", 0) > 0)
    loss_usd = abs(sum(e.get("gross_pnl_usd", 0) for e in all_exits if e.get("gross_pnl_usd", 0) <= 0))
    pf = (wins_usd / loss_usd) if loss_usd > 0 else (None if not all_exits else float("inf"))

    avg_entry_slip = sum(e.get("entry_slip_pct", 0) for e in all_exits) / n if n else None
    avg_exit_slip = sum(e.get("exit_slip_pct", 0) for e in all_exits) / n if n else None
    avg_rt_slip = (avg_entry_slip + avg_exit_slip) if (avg_entry_slip is not None and avg_exit_slip is not None) else None

    dashboard = {
        "updated_at": now,
        "updated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "status": "ACTIVE",
        "started_at_iso": "2026-05-20T02:00:00Z",
        "production_cell": {
            "trigger": "breakout v0.1 (b1-b6 all): stoch>0.9 + price≥BB-up + vol≥1.5x + 1H up + 4H up + 15m mom≥+0.5%",
            "exit": "24h time-stop | trailing 0.4%/0.5% | -3% SL",
            "sizing": "top10 $200 / 11-20 $100 (paper)",
            "fee_assumption": "Coinbase One 0% maker/taker",
            "max_concurrent": MAX_CONCURRENT,
        },
        "universe_count": len(UNIVERSE),
        "universe": [{"symbol": s, "rank": r, "size_usd": z}
                     for s, r, z in UNIVERSE],
        "open_positions_count": len(state["positions"]),
        "open_positions": [
            {
                "symbol": p["symbol"], "rank": p["rank"],
                "size_usd": p["size_usd"],
                "entry_ts": p["entry_ts"],
                "entry_fill": p["entry_fill"],
                "entry_slip_pct": round(p["entry_slip_pct"], 3),
                "trigger_ret_pct": p.get("trigger_mom_pct", 0),  # surfaced as 'trigger_ret_pct' in /lab template
                "trigger_stoch": p.get("trigger_stoch"),
                "trigger_vol_ratio": p.get("trigger_vol_ratio"),
                "highest_pnl_pct": round(p["highest_pnl"] * 100, 2),
                "elapsed_sec": now - p["entry_ts"],
                "trail_armed": p["trail_armed"],
            }
            for p in state["positions"]
        ],
        "kpi": {
            "trades": n,
            "wins": cum["wins"],
            "wr_pct": round(wr_pct, 1) if wr_pct is not None else None,
            "net_usd": round(cum["net_usd"], 2),
            "pf": round(pf, 2) if isinstance(pf, (int, float)) and pf != float("inf") else (None if pf is None else "inf"),
            "fires_attempted": cum["fires_attempted"],
            "fires_filled": cum["fires_filled"],
            "gate_total": PROMOTE_GATE,
            "gate_progress": f"{n}/{PROMOTE_GATE}",
            "gate_pct": round(min(100, n / PROMOTE_GATE * 100), 1),
        },
        "realized_slip": {
            "avg_entry_pct": round(avg_entry_slip, 3) if avg_entry_slip is not None else None,
            "avg_exit_pct": round(avg_exit_slip, 3) if avg_exit_slip is not None else None,
            "avg_round_trip_pct": round(avg_rt_slip, 3) if avg_rt_slip is not None else None,
        },
        "recent_trades": [
            {
                "symbol": e["symbol"],
                "entry_ts": e.get("entry_ts"),
                "exit_ts": e.get("exit_ts"),
                "elapsed_sec": e.get("elapsed_sec"),
                "gross_pnl_usd": round(e.get("gross_pnl_usd", 0), 2),
                "gross_pnl_pct": round(e.get("gross_pnl_pct", 0), 2),
                "exit_reason": e.get("exit_reason"),
                "trigger_ret_pct": e.get("trigger_mom_pct"),
            }
            for e in all_exits[-5:]
        ],
        "per_symbol": compute_per_symbol(all_exits),
    }
    os.makedirs(os.path.dirname(DASHBOARD_PATH), exist_ok=True)
    tmp = DASHBOARD_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dashboard, f, indent=2)
    os.replace(tmp, DASHBOARD_PATH)


def main():
    state = load_state()
    now = int(time.time())
    manage_exits(state, now)
    scan_entries(state, now)
    save_state(state)
    write_dashboard(state, now)
    cum = state["cumulative"]
    wr = (cum["wins"] / cum["trades"] * 100) if cum["trades"] else 0.0
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
          f"open={len(state['positions'])} "
          f"trades={cum['trades']} (W={cum['wins']}, WR={wr:.1f}%) "
          f"net=${cum['net_usd']:+.2f} "
          f"fires_attempted={cum['fires_attempted']} "
          f"fires_filled={cum['fires_filled']}")


if __name__ == "__main__":
    main()
