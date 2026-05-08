#!/usr/bin/env python3
"""
BIBSUS Alpha Strategy Optimizer — Parameter Grid Search
Fetches recent N days of SOL/USD data and tests parameter combinations.
Outputs the best parameter set by net PnL.

Usage:
    python3 strategy_optimizer.py              # 30 days
    python3 strategy_optimizer.py --days 60    # 60 days
"""

import math
import sys
import time
import json
from datetime import datetime
from itertools import product

try:
    import ccxt
except ImportError:
    print("pip install ccxt")
    sys.exit(1)


# ══════════════════════════════════════
#  Data Fetching
# ══════════════════════════════════════

def fetch_ohlcv(exchange, symbol, timeframe, days):
    """Fetch OHLCV data in batches."""
    all_bars = []
    limit = 300
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - days * 24 * 3600 * 1000

    print(f"Fetching {days} days of {timeframe} data for {symbol}...")
    since = start_ts
    while since < end_ts:
        bars = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        if not bars:
            break
        all_bars.extend(bars)
        since = bars[-1][0] + 1
        time.sleep(0.15)

    # Deduplicate
    seen = set()
    unique = []
    for b in all_bars:
        if b[0] not in seen:
            seen.add(b[0])
            unique.append(b)
    unique.sort(key=lambda x: x[0])
    print(f"  Got {len(unique)} bars ({unique[0][0]} — {unique[-1][0]})")
    return unique


# ══════════════════════════════════════
#  Indicator Calculations
# ══════════════════════════════════════

def calc_ema(data, period):
    if len(data) < period:
        return data[-1] if data else 0
    k = 2 / (period + 1)
    ema = sum(data[:period]) / period
    for v in data[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def calc_stoch_rsi(closes, rsi_period=14, stoch_period=14, k_smooth=3):
    if len(closes) < rsi_period + stoch_period:
        return 0.5
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(max(d, 0) for d in deltas[:rsi_period]) / rsi_period
    avg_loss = sum(max(-d, 0) for d in deltas[:rsi_period]) / rsi_period
    rsi_vals = []
    if avg_loss == 0:
        rsi_vals.append(100.0)
    else:
        rsi_vals.append(100 - 100 / (1 + avg_gain / avg_loss))
    for i in range(rsi_period, len(deltas)):
        avg_gain = (avg_gain * (rsi_period - 1) + max(deltas[i], 0)) / rsi_period
        avg_loss = (avg_loss * (rsi_period - 1) + max(-deltas[i], 0)) / rsi_period
        if avg_loss == 0:
            rsi_vals.append(100.0)
        else:
            rsi_vals.append(100 - 100 / (1 + avg_gain / avg_loss))
    if len(rsi_vals) < stoch_period:
        return 0.5
    stoch_raw = []
    for i in range(stoch_period - 1, len(rsi_vals)):
        window = rsi_vals[i - stoch_period + 1: i + 1]
        lo, hi = min(window), max(window)
        stoch_raw.append(0.5 if hi == lo else (rsi_vals[i] - lo) / (hi - lo))
    if len(stoch_raw) < k_smooth:
        return stoch_raw[-1] if stoch_raw else 0.5
    return sum(stoch_raw[-k_smooth:]) / k_smooth


def calc_bollinger(closes, period=20, std_mult=2.0):
    if len(closes) < period:
        c = closes[-1]
        return c * 1.02, c, c * 0.98
    window = closes[-period:]
    mid = sum(window) / period
    std = math.sqrt(sum((x - mid) ** 2 for x in window) / period)
    return mid + std_mult * std, mid, mid - std_mult * std


def calc_volume_ratio(volumes, lookback=20):
    if len(volumes) < lookback + 1:
        return 1.0
    avg = sum(volumes[-lookback - 1:-1]) / lookback
    return volumes[-1] / avg if avg > 0 else 1.0


def calc_momentum(closes, lookback):
    if len(closes) < lookback + 1:
        return 0.0
    return (closes[-1] - closes[-(lookback + 1)]) / closes[-(lookback + 1)]


# ══════════════════════════════════════
#  Backtester
# ══════════════════════════════════════

def backtest(bars_15m, bars_1h, params):
    """
    Run momentum breakout backtest with given parameters.
    Returns: {pnl, trades, wins, win_rate, max_dd}
    """
    stoch_long_thresh = params["stoch_long"]   # Long when stoch > this
    stoch_short_thresh = params["stoch_short"]  # Short when stoch < this
    vol_mult = params["vol_mult"]
    tp_pct = params["tp_pct"]
    sl_pct = params["sl_pct"]
    momentum_block = params.get("momentum_block", 0.025)
    momentum_candles = params.get("momentum_candles", 6)

    capital = 1000.0
    position_pct = 0.80
    fee_rate = 0.0006
    cooldown_bars = 16  # 4 hours on 15m

    cash = capital
    position = None
    trades = []
    wins = 0
    peak_cash = cash
    max_dd = 0.0
    bars_since_exit = cooldown_bars + 1

    # Build 1h close lookup by timestamp (hour-aligned)
    h1_closes = {}
    for b in bars_1h:
        h1_closes[b[0]] = b[4]

    for i in range(50, len(bars_15m)):
        price = bars_15m[i][4]

        # Track drawdown
        current_val = cash
        if position:
            if position["dir"] == "long":
                pnl_pct = (price - position["entry"]) / position["entry"]
            else:
                pnl_pct = (position["entry"] - price) / position["entry"]
            current_val = cash + position["margin"] * pnl_pct
        peak_cash = max(peak_cash, current_val)
        dd = (peak_cash - current_val) / peak_cash if peak_cash > 0 else 0
        max_dd = max(max_dd, dd)

        # Position management
        if position:
            if position["dir"] == "long":
                pnl_pct = (price - position["entry"]) / position["entry"]
            else:
                pnl_pct = (position["entry"] - price) / position["entry"]

            if pnl_pct >= tp_pct:
                profit = position["margin"] * pnl_pct - position["margin"] * fee_rate * 2
                cash += position["margin"] + profit
                trades.append(profit)
                if profit > 0:
                    wins += 1
                position = None
                bars_since_exit = 0
                continue

            if pnl_pct <= -sl_pct:
                profit = position["margin"] * pnl_pct - position["margin"] * fee_rate * 2
                cash += position["margin"] + profit
                trades.append(profit)
                if profit > 0:
                    wins += 1
                position = None
                bars_since_exit = 0
                continue

            continue

        bars_since_exit += 1
        if bars_since_exit < cooldown_bars:
            continue

        # Signal generation
        closes = [bars_15m[j][4] for j in range(max(0, i - 99), i + 1)]
        volumes = [bars_15m[j][5] for j in range(max(0, i - 99), i + 1)]

        if len(closes) < 35:
            continue

        stoch = calc_stoch_rsi(closes)
        bb_upper, bb_mid, bb_lower = calc_bollinger(closes)
        vol_ratio = calc_volume_ratio(volumes)
        momentum = calc_momentum(closes, momentum_candles)

        # 1h trend (approximate — find nearest 1h bar)
        bar_ts = bars_15m[i][0]
        hour_ts = bar_ts - (bar_ts % 3600000)
        trend = "neutral"
        h1_slice = [h1_closes[t] for t in sorted(h1_closes.keys()) if t <= bar_ts]
        if len(h1_slice) >= 21:
            ema_f = calc_ema(h1_slice[-30:], 8)
            ema_s = calc_ema(h1_slice[-30:], 21)
            if ema_f > ema_s * 1.003:
                trend = "up"
            elif ema_f < ema_s * 0.997:
                trend = "down"

        # Long: momentum breakout
        long_ok = (stoch > stoch_long_thresh and
                   price >= bb_upper and
                   vol_ratio >= vol_mult and
                   trend != "down" and
                   momentum >= -momentum_block)

        # Short: momentum breakdown
        short_ok = (stoch < stoch_short_thresh and
                    price <= bb_lower and
                    vol_ratio >= vol_mult and
                    trend != "up" and
                    momentum <= momentum_block)

        direction = None
        if long_ok:
            direction = "long"
        elif short_ok:
            direction = "short"

        if direction and cash > 10:
            margin = cash * position_pct
            cash -= margin
            position = {"dir": direction, "entry": price, "margin": margin}

    # Close any open position at last price
    if position:
        price = bars_15m[-1][4]
        if position["dir"] == "long":
            pnl_pct = (price - position["entry"]) / position["entry"]
        else:
            pnl_pct = (position["entry"] - price) / position["entry"]
        profit = position["margin"] * pnl_pct - position["margin"] * fee_rate * 2
        cash += position["margin"] + profit
        trades.append(profit)
        if profit > 0:
            wins += 1

    total_pnl = cash - capital
    n_trades = len(trades)
    win_rate = wins / n_trades if n_trades > 0 else 0

    return {
        "pnl": round(total_pnl, 2),
        "trades": n_trades,
        "wins": wins,
        "win_rate": round(win_rate * 100, 1),
        "max_dd": round(max_dd * 100, 1),
        "final_balance": round(cash, 2),
    }


# ══════════════════════════════════════
#  Parameter Grid
# ══════════════════════════════════════

PARAM_GRID = {
    "stoch_long":  [0.75, 0.80, 0.85, 0.90],      # Long when stoch > X
    "stoch_short": [0.10, 0.15, 0.20, 0.25],       # Short when stoch < X
    "vol_mult":    [0.8, 1.0, 1.2],                 # Volume multiplier
    "tp_pct":      [0.015, 0.020, 0.025, 0.030],    # Take profit %
    "sl_pct":      [0.015, 0.020, 0.025, 0.035],    # Stop loss %
}


def main():
    days = 30
    if "--days" in sys.argv:
        idx = sys.argv.index("--days")
        days = int(sys.argv[idx + 1])

    exchange = ccxt.coinbase({
        "enableRateLimit": True,
        "options": {"defaultType": "swap", "defaultSubType": "linear"},
    })

    bars_15m = fetch_ohlcv(exchange, "SOL/USD", "15m", days)
    bars_1h = fetch_ohlcv(exchange, "SOL/USD", "1h", days + 10)

    if len(bars_15m) < 100:
        print("Not enough data")
        sys.exit(1)

    # Generate all parameter combinations
    keys = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    combos = list(product(*values))
    print(f"\nTesting {len(combos)} parameter combinations on {days} days of data...\n")

    results = []
    best_pnl = -9999
    best_params = None

    for idx, combo in enumerate(combos):
        params = dict(zip(keys, combo))

        # Skip nonsensical combos
        if params["tp_pct"] < params["sl_pct"] * 0.3:
            continue  # TP way too small vs SL

        result = backtest(bars_15m, bars_1h, params)
        result["params"] = params
        results.append(result)

        if result["pnl"] > best_pnl:
            best_pnl = result["pnl"]
            best_params = result

        if (idx + 1) % 50 == 0:
            print(f"  Tested {idx + 1}/{len(combos)}... best so far: ${best_pnl:+.2f}")

    # Sort by PnL
    results.sort(key=lambda x: x["pnl"], reverse=True)

    print("\n" + "=" * 70)
    print(f"  TOP 10 PARAMETER COMBINATIONS ({days}-day backtest)")
    print("=" * 70)

    for i, r in enumerate(results[:10]):
        p = r["params"]
        print(f"\n  #{i+1}: PnL ${r['pnl']:+.2f} | {r['trades']} trades | "
              f"WR {r['win_rate']}% | MaxDD {r['max_dd']}%")
        print(f"      StochRSI Long>{p['stoch_long']} Short<{p['stoch_short']} | "
              f"Vol>{p['vol_mult']}x | TP {p['tp_pct']:.1%} SL {p['sl_pct']:.1%}")

    print("\n" + "=" * 70)
    print(f"  WORST 3")
    print("=" * 70)
    for r in results[-3:]:
        p = r["params"]
        print(f"  PnL ${r['pnl']:+.2f} | {r['trades']} trades | WR {r['win_rate']}%")
        print(f"      StochRSI L>{p['stoch_long']} S<{p['stoch_short']} | "
              f"Vol>{p['vol_mult']}x | TP {p['tp_pct']:.1%} SL {p['sl_pct']:.1%}")

    # Save results
    out_file = f"optimizer_results_{days}d.json"
    with open(out_file, "w") as f:
        json.dump({
            "date": datetime.now().isoformat(),
            "days": days,
            "combos_tested": len(results),
            "best": results[0] if results else None,
            "top10": results[:10],
        }, f, indent=2)
    print(f"\nResults saved to {out_file}")

    # Recommendation
    if results:
        best = results[0]
        p = best["params"]
        print(f"\n{'='*70}")
        print(f"  RECOMMENDED CONFIG UPDATE:")
        print(f"{'='*70}")
        print(f"  stoch_rsi_short = {p['stoch_long']}  # Long entry threshold")
        print(f"  stoch_rsi_long  = {p['stoch_short']}  # Short entry threshold")
        print(f"  volume_mult     = {p['vol_mult']}")
        print(f"  tp_pct          = {p['tp_pct']}")
        print(f"  sl_pct          = {p['sl_pct']}")
        print(f"\n  Expected: ${best['pnl']:+.2f} PnL | {best['win_rate']}% WR | "
              f"{best['trades']} trades | {best['max_dd']}% max drawdown")


if __name__ == "__main__":
    main()
