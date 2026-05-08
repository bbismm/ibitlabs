#!/usr/bin/env python3
"""
Trailing Stop Parameter Backtest
Simulates different trailing_activate / trailing_stop combos on historical 1m candles
for the 4 momentum_breakout trades.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coinbase_exchange import CoinbaseExchange
from sol_sniper_config import SniperConfig

cfg = SniperConfig()
cfg.validate()
ex = CoinbaseExchange(cfg.api_key, cfg.api_secret)

SYMBOL = cfg.symbol
CONTRACT_SOL = 5.0  # SOL per contract

# The 4 breakout trades: (id, direction, entry_price, entry_ts, exit_ts, quantity_contracts)
TRADES = [
    {"id": 254, "dir": "short", "entry": 85.37, "entry_ts": 1775848054, "exit_ts": 1775874450, "qty": 3},
    {"id": 256, "dir": "long",  "entry": 84.84, "entry_ts": 1775875391, "exit_ts": 1775904401, "qty": 3},
    {"id": 259, "dir": "long",  "entry": 84.08, "entry_ts": 1775906241, "exit_ts": 1775927138, "qty": 3},
    {"id": 267, "dir": "long",  "entry": 86.28, "entry_ts": 1775936031, "exit_ts": 1775958105, "qty": 3},
]

def fetch_candles_batched(exchange, symbol, start, end):
    """Fetch 1m candles in batches of 300 (Coinbase limit 350)."""
    all_candles = []
    chunk = 300 * 60  # 300 minutes in seconds
    cur = start
    while cur < end:
        batch_end = min(cur + chunk, end)
        resp = exchange.client.get_candles(symbol, str(cur), str(batch_end), "ONE_MINUTE")
        candles_raw = resp if isinstance(resp, dict) else vars(resp)
        candle_list = candles_raw.get("candles", [])
        for c in candle_list:
            if isinstance(c, dict):
                ts = int(c.get("start", 0))
                h = float(c.get("high", 0))
                l = float(c.get("low", 0))
                cl = float(c.get("close", 0))
            else:
                ts = int(getattr(c, "start", 0))
                h = float(getattr(c, "high", 0))
                l = float(getattr(c, "low", 0))
                cl = float(getattr(c, "close", 0))
            all_candles.append({"ts": ts, "high": h, "low": l, "close": cl})
        cur = batch_end
        time.sleep(0.3)
    # Deduplicate and sort
    seen = set()
    unique = []
    for c in all_candles:
        if c["ts"] not in seen:
            seen.add(c["ts"])
            unique.append(c)
    unique.sort(key=lambda x: x["ts"])
    return unique

# Fetch 1m candles for each trade
print("Fetching 1-minute candles for each trade...\n")
for t in TRADES:
    duration = t["exit_ts"] - t["entry_ts"]
    start = t["entry_ts"] - 60  # 1 min before
    end = t["exit_ts"] + 60

    candles = fetch_candles_batched(ex, SYMBOL, start, end)
    # Filter to only candles at or after entry
    candles = [c for c in candles if c["ts"] >= t["entry_ts"]]
    t["candles"] = candles
    print(f"  Trade #{t['id']} ({t['dir']}): {len(candles)} candles, "
          f"duration {duration/3600:.1f}h, entry ${t['entry']:.2f}")

print(f"\n{'='*80}")
print("PARAMETER SWEEP: trailing_activate x trailing_stop")
print(f"Fixed: sl_pct=3.5%, tp_pct=3.0%, max_hold=8h")
print(f"{'='*80}\n")

def simulate_trade(trade, tp_pct, sl_pct, trail_activate, trail_stop, max_hold=8*3600):
    """Simulate a single trade with given parameters. Returns (pnl, exit_reason, exit_price)."""
    entry = trade["entry"]
    direction = trade["dir"]
    qty_sol = trade["qty"] * CONTRACT_SOL  # total SOL
    candles = trade["candles"]

    if not candles:
        return 0, "no_data", entry

    best_price = entry  # best price seen (for trailing)
    trailing_active = False

    for c in candles:
        elapsed = c["ts"] - trade["entry_ts"]

        if direction == "long":
            # Check SL (hit low)
            if (entry - c["low"]) / entry >= sl_pct:
                exit_p = entry * (1 - sl_pct)
                pnl = (exit_p - entry) * qty_sol
                return pnl, "sl", exit_p

            # Track best high
            if c["high"] > best_price:
                best_price = c["high"]

            # Check if trailing activates
            if not trailing_active and (best_price - entry) / entry >= trail_activate:
                trailing_active = True

            # Check trailing stop
            if trailing_active:
                drawdown = (best_price - c["low"]) / best_price
                if drawdown >= trail_stop:
                    exit_p = best_price * (1 - trail_stop)
                    pnl = (exit_p - entry) * qty_sol
                    return pnl, "trailing", exit_p

            # Check TP
            if (c["high"] - entry) / entry >= tp_pct:
                exit_p = entry * (1 + tp_pct)
                pnl = (exit_p - entry) * qty_sol
                return pnl, "tp", exit_p

        else:  # short
            # Check SL (hit high)
            if (c["high"] - entry) / entry >= sl_pct:
                exit_p = entry * (1 + sl_pct)
                pnl = (entry - exit_p) * qty_sol
                return pnl, "sl", exit_p

            # Track best low
            if c["low"] < best_price:
                best_price = c["low"]

            # Check if trailing activates
            if not trailing_active and (entry - best_price) / entry >= trail_activate:
                trailing_active = True

            # Check trailing stop
            if trailing_active:
                drawdown = (c["high"] - best_price) / best_price
                if drawdown >= trail_stop:
                    exit_p = best_price * (1 + trail_stop)
                    pnl = (entry - exit_p) * qty_sol
                    return pnl, "trailing", exit_p

            # Check TP
            if (entry - c["low"]) / entry >= tp_pct:
                exit_p = entry * (1 - tp_pct)
                pnl = (entry - exit_p) * qty_sol
                return pnl, "tp", exit_p

        # Check timeout
        if elapsed >= max_hold:
            exit_p = c["close"]
            if direction == "long":
                pnl = (exit_p - entry) * qty_sol
            else:
                pnl = (entry - exit_p) * qty_sol
            return pnl, "timeout", exit_p

    # End of candles — use last close
    exit_p = candles[-1]["close"]
    if direction == "long":
        pnl = (exit_p - entry) * qty_sol
    else:
        pnl = (entry - exit_p) * qty_sol
    return pnl, "end_of_data", exit_p

# Fee estimate per trade (entry + exit)
FEE_PER_TRADE = 0.60  # ~$0.30 each side for 15 SOL at ~$85

# Parameter grid
activate_range = [0.005, 0.008, 0.010, 0.012, 0.015, 0.020, 0.025, 0.030]
stop_range = [0.003, 0.005, 0.008, 0.010, 0.012, 0.015, 0.020]

results = []

for act in activate_range:
    for stp in stop_range:
        if stp >= act:
            continue  # trailing stop must be smaller than activation

        total_pnl = 0
        total_fees = 0
        details = []

        for trade in TRADES:
            pnl, reason, exit_p = simulate_trade(
                trade, tp_pct=0.030, sl_pct=0.035,
                trail_activate=act, trail_stop=stp
            )
            net = pnl - FEE_PER_TRADE
            total_pnl += pnl
            total_fees += FEE_PER_TRADE
            details.append((trade["id"], pnl, reason, exit_p))

        net_total = total_pnl - total_fees
        results.append({
            "activate": act, "stop": stp,
            "gross": total_pnl, "net": net_total,
            "details": details
        })

# Sort by net profit
results.sort(key=lambda x: x["net"], reverse=True)

# Print top 15
print(f"{'Activate':>10} {'Stop':>8} {'Gross':>10} {'Net':>10}  Trade details")
print(f"{'-'*10} {'-'*8} {'-'*10} {'-'*10}  {'-'*50}")

for r in results[:15]:
    det = " | ".join(f"#{d[0]}:{d[2]}${d[1]:+.2f}" for d in r["details"])
    print(f"{r['activate']*100:>9.1f}% {r['stop']*100:>7.1f}% {r['gross']:>+10.2f} {r['net']:>+10.2f}  {det}")

print(f"\n{'='*80}")
print("CURRENT CONFIG RESULT:")
print(f"{'='*80}")

# Find current config result
for r in results:
    if abs(r["activate"] - 0.008) < 0.0001 and abs(r["stop"] - 0.005) < 0.0001:
        det = " | ".join(f"#{d[0]}:{d[2]}${d[1]:+.2f}" for d in r["details"])
        print(f"  activate=0.8%, stop=0.5% → Net: ${r['net']:+.2f}")
        for d in r["details"]:
            print(f"    Trade #{d[0]}: {d[2]:>10} → ${d[1]:+.2f} (exit ${d[3]:.2f})")
        break

print(f"\n{'='*80}")
print("BEST CONFIG:")
print(f"{'='*80}")
best = results[0]
print(f"  activate={best['activate']*100:.1f}%, stop={best['stop']*100:.1f}% → Net: ${best['net']:+.2f}")
for d in best["details"]:
    print(f"    Trade #{d[0]}: {d[2]:>10} → ${d[1]:+.2f} (exit ${d[3]:.2f})")

# Also show: what if we just used fixed TP/SL without trailing?
print(f"\n{'='*80}")
print("COMPARISON: No trailing stop (pure TP/SL)")
print(f"{'='*80}")
total_pnl = 0
for trade in TRADES:
    pnl, reason, exit_p = simulate_trade(
        trade, tp_pct=0.030, sl_pct=0.035,
        trail_activate=999, trail_stop=999  # effectively disabled
    )
    net = pnl - FEE_PER_TRADE
    total_pnl += pnl
    print(f"    Trade #{trade['id']}: {reason:>10} → ${pnl:+.2f} (exit ${exit_p:.2f})")
print(f"  Net (no trailing): ${total_pnl - 4*FEE_PER_TRADE:+.2f}")

# Show max favorable excursion for each trade
print(f"\n{'='*80}")
print("MAX FAVORABLE EXCURSION (how far price moved in our favor)")
print(f"{'='*80}")
for trade in TRADES:
    candles = trade["candles"]
    entry = trade["entry"]
    if trade["dir"] == "long":
        best_h = max(c["high"] for c in candles) if candles else entry
        mfe = (best_h - entry) / entry * 100
        print(f"  #{trade['id']} long  entry=${entry:.2f}  best_high=${best_h:.2f}  MFE={mfe:+.2f}%")
    else:
        best_l = min(c["low"] for c in candles) if candles else entry
        mfe = (entry - best_l) / entry * 100
        print(f"  #{trade['id']} short entry=${entry:.2f}  best_low=${best_l:.2f}  MFE={mfe:+.2f}%")
