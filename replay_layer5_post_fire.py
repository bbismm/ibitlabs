#!/usr/bin/env python3
"""
Layer 5 post-fire replay (2026-05-06 follow-up): for each of the 3 hybrid_v5.1
SL fires, ask "what if we had held past -5% with a -10% structure-gated SL?"

For each trade, replay from entry forward bar-by-bar with these alternative
exit rules (replaces fixed -5%):

  Existing rules that stay:
    - Trailing: arm at MFE ≥ +1.5%; close at 0.5% pullback from peak
    - Other exits (manual, breakeven, timeout): keep as-is

  NEW Layer 5 SL (replaces -5%):
    - Doom floor: profit_pct < -10% → close (hard ceiling)
    - Structure SL: profit_pct < -2.5% AND structure broken → close
      (structure broken per NFI u_e pattern, mirrored for SHORT)

LONG structure-broken (price recovering against entry, sellers in control):
    close < EMA_200_15m AND distance(close, EMA_200) < 1% AND RSI_14 rising

SHORT structure-broken (price recovering against entry, buyers in control):
    close > EMA_200_15m AND distance(close, EMA_200) < 1% AND RSI_14 falling

Output per trade:
  actual exit (-5% SL, $-X)  vs  Layer-5 exit (when, why, $±Y)  → Δ
"""

import json, time, urllib.request, sqlite3, statistics
from pathlib import Path

# Load merged bars + extend if needed
def load_bars():
    bars = []
    for p in ['/Users/bonnyagent/ibitlabs/_backtest_cache/sol_15m_120d.json',
              '/tmp/sol_15m_recent.json']:
        if Path(p).exists():
            with open(p) as f:
                bars.extend(json.load(f))
    seen, out = set(), []
    for b in bars:
        if b['ts'] not in seen:
            seen.add(b['ts']); out.append(b)
    out.sort(key=lambda b: b['ts'])
    return out

def fetch_post_fire_bars(after_ts, n=200):
    """Fetch n 15m bars starting around after_ts via Coinbase public API."""
    import urllib.request
    url = f"https://api.coinbase.com/api/v3/brokerage/market/products/SOL-USD/candles"
    # We can't easily paginate without ccxt, but we just need ~50 bars post-fire
    # for SL fire 339. Use ccxt for ease.
    import ccxt
    ex = ccxt.coinbase()
    bars = ex.fetch_ohlcv('SOL/USD', '15m', since=int(after_ts*1000), limit=n)
    return [{'ts': int(b[0]/1000), 'open': b[1], 'high': b[2], 'low': b[3],
             'close': b[4], 'volume': b[5]} for b in bars]

def ema_series(values, period):
    k = 2 / (period + 1)
    out = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period-1] = seed
    for i in range(period, len(values)):
        out[i] = values[i] * k + out[i-1] * (1-k)
    return out

def rsi_series(closes, period=14):
    out = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[:period])/period; al = sum(losses[:period])/period
    out[period] = 100 - (100/(1 + (ag/al if al else 1e9)))
    for i in range(period+1, len(closes)):
        ag = (ag*(period-1) + gains[i-1])/period
        al = (al*(period-1) + losses[i-1])/period
        out[i] = 100 - (100/(1 + (ag/al if al else 1e9)))
    return out


def replay(trade, bars, ema200, rsi14, scale):
    """Replay one trade with Layer 5 SL rules. Return {action, when_ts, exit_pct, exit_pnl, reason}."""
    ep = trade['entry_price']
    entry_ts = trade['entry_ts']
    direction = trade['direction']
    trail_arm_pct = 0.015
    trail_stop_pct = 0.005
    doom_floor = -0.10
    structure_floor = -0.025

    # Find entry bar idx
    eidx = None
    for i, b in enumerate(bars):
        if b['ts'] >= entry_ts:
            eidx = i; break
    if eidx is None:
        return {'action': 'NO_ENTRY_BAR'}

    mfe = 0.0
    armed = False
    bar_count = 0
    for i in range(eidx, len(bars)):
        bar = bars[i]
        cp = bar['close']
        # Profit pct (close-based)
        if direction == 'long':
            pct = (cp - ep) / ep
        else:
            pct = (ep - cp) / ep

        if pct > mfe:
            mfe = pct

        # ── Trailing arm + close ──
        if pct >= trail_arm_pct:
            armed = True
        if armed and (mfe - pct) >= trail_stop_pct:
            return {'action': 'trailing_close', 'when_ts': bar['ts'],
                    'when_h': (bar['ts']-entry_ts)/3600,
                    'exit_pct': pct, 'exit_pnl': pct*scale,
                    'reason': f'Trailing | peak {mfe:+.2%}, dropped to {pct:+.2%}',
                    'mfe': mfe, 'bars': bar_count}

        # ── Layer 5 SL ──
        if pct <= doom_floor:
            return {'action': 'doom_sl', 'when_ts': bar['ts'],
                    'when_h': (bar['ts']-entry_ts)/3600,
                    'exit_pct': pct, 'exit_pnl': pct*scale,
                    'reason': f'Doom floor at {pct:+.2%} (mfe was {mfe:+.2%})',
                    'mfe': mfe, 'bars': bar_count}

        if pct <= structure_floor:
            # Check structure
            if i >= 200 and ema200[i] is not None and rsi14[i] is not None and rsi14[i-1] is not None:
                e200 = ema200[i]
                dist_pct = abs(cp - e200) / e200
                rsi_rising = rsi14[i] > rsi14[i-1]
                rsi_falling = rsi14[i] < rsi14[i-1]
                if direction == 'long':
                    broken = (cp < e200) and (dist_pct < 0.01) and rsi_rising
                else:
                    broken = (cp > e200) and (dist_pct < 0.01) and rsi_falling
                if broken:
                    return {'action': 'structure_sl', 'when_ts': bar['ts'],
                            'when_h': (bar['ts']-entry_ts)/3600,
                            'exit_pct': pct, 'exit_pnl': pct*scale,
                            'reason': f'Structure broken at {pct:+.2%} (dist_ema200={dist_pct*100:.2f}%, mfe={mfe:+.2%})',
                            'mfe': mfe, 'bars': bar_count}

        bar_count += 1
        # Soft cap to prevent runaway
        if bar_count > 1000:  # ~10 days
            return {'action': 'NO_EXIT_IN_WINDOW', 'when_ts': bar['ts'],
                    'when_h': (bar['ts']-entry_ts)/3600,
                    'exit_pct': pct, 'exit_pnl': pct*scale,
                    'reason': f'Cap hit ({bar_count} bars, last pct={pct:+.2%}, mfe={mfe:+.2%})',
                    'mfe': mfe, 'bars': bar_count}

    # Reached end of data without exiting
    last = bars[-1]
    cp = last['close']
    pct = (cp - ep)/ep if direction == 'long' else (ep - cp)/ep
    return {'action': 'NO_DATA_AFTER', 'when_ts': last['ts'],
            'when_h': (last['ts']-entry_ts)/3600,
            'exit_pct': pct, 'exit_pnl': pct*scale,
            'reason': f'Ran out of bars (pct {pct:+.2%}, mfe {mfe:+.2%})',
            'mfe': mfe, 'bars': bar_count}


def main():
    print("Loading bars...")
    bars = load_bars()
    print(f"  Initial: {len(bars)} bars, last ts {bars[-1]['ts']}")

    # Trade 339 SL fired at 1778052175 UTC. Cache last is 1778087700 = ~9.9h after.
    # For Layer 5 replay, we need bars AFTER the SL fire if the alt-exit hadn't
    # already fired by then. Fetch more recent.
    print("Fetching post-cache bars to cover trade 339 fully...")
    try:
        recent = fetch_post_fire_bars(bars[-1]['ts'] + 900, n=300)
        seen = set(b['ts'] for b in bars)
        added = 0
        for b in recent:
            if b['ts'] not in seen:
                bars.append(b); seen.add(b['ts']); added += 1
        bars.sort(key=lambda b: b['ts'])
        print(f"  Added {added} fresh bars, last ts now {bars[-1]['ts']}")
    except Exception as e:
        print(f"  fetch failed: {e}")

    closes = [b['close'] for b in bars]
    ema200 = ema_series(closes, 200)
    rsi14 = rsi_series(closes, 14)

    # Pull trade pairs (entry + matching SL exit) from DB
    con = sqlite3.connect('/Users/bonnyagent/ibitlabs/sol_sniper.db')
    con.row_factory = sqlite3.Row

    # SL exits
    sl_exits = con.execute("""
        SELECT id, timestamp AS exit_ts, direction, entry_price, exit_price, pnl, trigger_rule
        FROM trade_log
        WHERE strategy_version='hybrid_v5.1' AND exit_reason='sl' AND pnl IS NOT NULL
        ORDER BY timestamp
    """).fetchall()

    # Find entry timestamp for each (open row of same direction + trigger_rule + entry_price, prior in time)
    opens = con.execute("""
        SELECT id, timestamp AS entry_ts, direction, entry_price, trigger_rule
        FROM trade_log
        WHERE strategy_version='hybrid_v5.1' AND (exit_reason IS NULL OR exit_reason='')
        ORDER BY timestamp
    """).fetchall()

    trades = []
    for sl in sl_exits:
        match = None
        for op in opens:
            if (op['direction'] == sl['direction']
                and op['trigger_rule'] == sl['trigger_rule']
                and abs(float(op['entry_price'] or 0) - float(sl['entry_price'])) < 0.01
                and op['entry_ts'] < sl['exit_ts']):
                if match is None or op['entry_ts'] > match['entry_ts']:
                    match = op
        if match:
            trades.append({
                'id': sl['id'],
                'direction': sl['direction'],
                'entry_price': float(sl['entry_price']),
                'entry_ts': match['entry_ts'],
                'exit_ts': sl['exit_ts'],
                'actual_pnl': float(sl['pnl']),
                'actual_exit_price': float(sl['exit_price']),
            })

    print(f"\nMatched {len(trades)} SL trades to entries\n")

    print("="*120)
    print(f"{'id':<5} {'dir':<6} {'entry→exit':<26} {'hold':<7} {'actual':<14} {'L5 alt action':<18} {'L5 alt P&L':<14} {'Δ vs actual'}")
    print("="*120)

    for t in trades:
        # Compute scale: actual_pnl / actual_pct gives notional-equiv
        actual_pct = (t['actual_exit_price'] - t['entry_price'])/t['entry_price'] if t['direction']=='long' \
                     else (t['entry_price'] - t['actual_exit_price'])/t['entry_price']
        scale = t['actual_pnl'] / actual_pct if actual_pct else 0
        actual_hold_h = (t['exit_ts'] - t['entry_ts']) / 3600

        result = replay(t, bars, ema200, rsi14, scale)

        from datetime import datetime
        e_str = datetime.utcfromtimestamp(t['entry_ts']).strftime('%m-%d %H:%M')
        x_str = datetime.utcfromtimestamp(t['exit_ts']).strftime('%m-%d %H:%M')
        ew_str = f"{e_str}→{x_str}"
        actual_str = f"{actual_pct*100:+5.2f}% ${t['actual_pnl']:+6.2f}"

        if result['action'] in ('NO_EXIT_IN_WINDOW', 'NO_DATA_AFTER', 'NO_ENTRY_BAR'):
            alt_str = result['action']
            alt_pnl_str = f"{result.get('exit_pct',0)*100:+.2f}% ${result.get('exit_pnl',0):+.2f}*"
            delta_str = f"{result.get('exit_pnl',0) - t['actual_pnl']:+.2f}*"
        else:
            alt_str = result['action']
            alt_pnl_str = f"{result['exit_pct']*100:+.2f}% ${result['exit_pnl']:+.2f}"
            delta_str = f"{result['exit_pnl'] - t['actual_pnl']:+.2f}"

        print(f"{t['id']:<5} {t['direction']:<6} {ew_str:<26} {actual_hold_h:>5.1f}h "
              f"{actual_str:<14} {alt_str:<18} {alt_pnl_str:<14} {delta_str}")
        if result.get('reason'):
            print(f"      └─ alt: hold {result.get('when_h',0):.1f}h | mfe {result.get('mfe',0)*100:+.2f}% | {result['reason']}")
        print()

    # Aggregate
    actuals = sum(t['actual_pnl'] for t in trades)
    print("="*120)
    print(f"Actual SL P&L total:  ${actuals:+.2f}")


if __name__ == '__main__':
    main()
