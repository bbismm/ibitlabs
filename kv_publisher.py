"""
KV Publisher — Pushes Sniper state to Cloudflare KV for the public dashboard.

Called periodically by the Sniper main loop. Reads local state files
and writes a combined status to Cloudflare KV via the API.

Required env vars:
  CF_ACCOUNT_ID — Cloudflare account ID
  CF_KV_NAMESPACE_ID — KV namespace ID (same as REPLOT_REPORTS)
  CF_API_TOKEN — Cloudflare API token with KV write permissions
"""

import json
import os
import logging
import time
from pathlib import Path
from twitter_poster import tweet_signal_open, tweet_signal_close, tweet_grid_trade
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

SNIPER_STATE = Path(__file__).parent / "sol_sniper_state.json"
MONITOR_STATE = Path(__file__).parent / "monitor_state.json"
SNIPER_DB = Path(__file__).parent / "sol_sniper.db"

CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID", "")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")

KV_API_BASE = "https://api.cloudflare.com/client/v4"

_last_publish = 0
PUBLISH_INTERVAL = 10  # seconds ($5/mo Workers paid plan — 1M writes/mo, ~518k/mo used)


def publish_to_kv():
    """Disabled — frontend now reads from trade.ibitlabs.com (Cloudflare Tunnel → localhost:8086).
    KV writes no longer needed. Keep function signature so callers don't break."""
    return


def _publish_to_kv_legacy():
    """Legacy KV publisher — kept for reference, not called."""
    global _last_publish

    now = time.time()

    if now - _last_publish < PUBLISH_INTERVAL:
        return

    _last_publish = now

    if not all([CF_ACCOUNT_ID, CF_KV_NAMESPACE_ID, CF_API_TOKEN]):
        return  # silently skip if not configured

    # Read local state
    sniper = {}
    try:
        if SNIPER_STATE.exists():
            sniper = json.loads(SNIPER_STATE.read_text())
    except Exception:
        pass

    monitor = {}

    try:
        if MONITOR_STATE.exists():
            monitor = json.loads(MONITOR_STATE.read_text())
    except Exception:
        pass

    # Calculate balance = cash + margin (if position open)
    cash = sniper.get("cash", 1000)
    pos = sniper.get("position")
    balance = cash + pos.get("margin", 0) if pos else cash

    # Read summary stats for free dashboard (show results, hide the how)
    trades = _read_recent_trades(50)
    total_pnl = round(sum(t["pnl"] for t in trades), 2)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = round(wins / len(trades) * 100, 1) if trades else 0
    # Last 3 completed trades (no entry conditions, just results)
    recent_trades = trades[:3]

    # Fetch live price from Coinbase Futures (same source as Sniper + Signals)
    indicators = _fetch_live_indicators()

    # Build combined status for FREE dashboard
    status = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": sniper.get("mode", "offline"),
        "price": indicators.get("price", 0),
        "balance": round(balance, 2),
        "starting_capital": 1000,
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "trade_count": len(trades),
        "recent_trades": recent_trades,
        "has_position": pos is not None,
        "position_direction": pos.get("direction") if pos else None,
        "grid": sniper.get("grid", {}),
        "regime": monitor.get("regime", "unknown"),
        "regime_detail": f"vol={monitor.get('regime_vol_percentile', 0)}% trend={monitor.get('regime_trend_strength', 0)}",
        "fear_greed_index": monitor.get("fear_greed_index", 50),
        "fear_greed_label": monitor.get("fear_greed_label", "Neutral"),
        "whale_bias": monitor.get("whale_bias", "neutral"),
        "sentiment": monitor.get("sentiment", "neutral"),
        "social_mood": monitor.get("social_mood", "neutral"),
        "action": monitor.get("action", "offline"),
    }

    _write_kv("sniper:status", json.dumps(status))

    # Build FULL status for PAID dashboard (reuse same indicators)
    _publish_paid_data(sniper, monitor, indicators)


def _publish_paid_data(sniper: dict, monitor: dict, indicators: dict):
    """Push full signal data for paid dashboard users."""

    conditions = _build_conditions(indicators)

    # Read trade history from DB
    trades = _read_recent_trades()

    # Calculate balance = cash + margin (if position open)
    cash = sniper.get("cash", 1000)
    pos = sniper.get("position")
    balance = cash + pos.get("margin", 0) if pos else cash

    # Enrich position with live PnL
    raw_pos = sniper.get("position")
    position = None
    if raw_pos:
        cur_price = indicators.get("price", raw_pos.get("entry_price", 0))
        ep = raw_pos.get("entry_price", 0)
        direction = raw_pos.get("direction", "long")
        margin = raw_pos.get("margin", 0)
        if direction == "long":
            pnl_pct = (cur_price - ep) / ep if ep > 0 else 0
        else:
            pnl_pct = (ep - cur_price) / ep if ep > 0 else 0
        pnl_usd = pnl_pct * margin
        elapsed = time.time() - raw_pos.get("timestamp", time.time())
        position = {
            "active": True,
            "direction": direction,
            "entry_price": ep,
            "current_price": cur_price,
            "margin": margin,
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 4),
            "elapsed_mins": int(elapsed / 60),
            "tp_price": round(ep * (1 + 0.020) if direction == "long" else ep * (1 - 0.020), 2),
            "sl_price": round(ep * (1 - 0.035) if direction == "long" else ep * (1 + 0.035), 2),
            "highest_pnl": sniper.get("highest_pnl_pct", 0),
            "trailing_active": sniper.get("trailing_active", False),
            "reasons": raw_pos.get("reasons", []),
        }

    paid_data = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": sniper.get("mode", "offline"),
        "price": indicators.get("price", 0),
        "balance": balance,
        "starting_capital": 1000,
        "position": position,
        "grid": sniper.get("grid", {}),

        # Signal indicators (paid only)
        "indicators": {
            "stoch_rsi": indicators.get("stoch_rsi", 0.5),
            "bb_upper": indicators.get("bb_upper", 0),
            "bb_mid": indicators.get("bb_mid", 0),
            "bb_lower": indicators.get("bb_lower", 0),
            "vol_ratio": indicators.get("vol_ratio", 1.0),
            "trend": indicators.get("trend", "neutral"),
            "price": indicators.get("price", 0),
        },
        "conditions": conditions,

        # Monitor data
        "regime": monitor.get("regime", "unknown"),
        "regime_detail": f"vol={monitor.get('regime_vol_percentile', 0)}% trend={monitor.get('regime_trend_strength', 0)}",
        "fear_greed_index": monitor.get("fear_greed_index", 50),
        "fear_greed_label": monitor.get("fear_greed_label", "Neutral"),
        "whale_bias": monitor.get("whale_bias", "neutral"),
        "sentiment": monitor.get("sentiment", "neutral"),
        "sentiment_confidence": monitor.get("sentiment_confidence", 0),
        "social_mood": monitor.get("social_mood", "neutral"),
        "social_score": monitor.get("social_score", 0),
        "funding_pressure": monitor.get("funding_pressure", 0),
        "action": monitor.get("action", "offline"),
        "alerts": monitor.get("alerts", []),

        # Trade history
        "trades": trades,
    }

    _write_kv("sniper:paid_status", json.dumps(paid_data))

    # Check for new signal → trigger notifications
    if conditions and conditions.get("signal"):
        sig = conditions["signal"]
        _write_kv("sniper:latest_signal", json.dumps(sig))
        _broadcast_signal(sig)


def _get_futures_exchange():
    """Create Coinbase exchange for public data (candles/ticker)."""
    if not hasattr(_get_futures_exchange, "_instance"):
        from coinbase_exchange import CoinbaseExchange
        import os
        _get_futures_exchange._instance = CoinbaseExchange(
            api_key=os.environ.get("CB_API_KEY", ""),
            api_secret=os.environ.get("CB_API_SECRET", "").replace("\\n", "\n"),
        )
        _get_futures_exchange._instance.load_markets()
    return _get_futures_exchange._instance


def _fetch_live_indicators() -> dict:
    """Fetch StochRSI, Bollinger Bands, volume from Coinbase Futures (same source as Sniper)."""
    import math

    try:
        exchange = _get_futures_exchange()

        # 15m candles — same as Sniper signal_timeframe
        ohlcv_15m = exchange.fetch_ohlcv("SLP-20DEC30-CDE", "15m", limit=100)
        if not ohlcv_15m or len(ohlcv_15m) < 35:
            return {}

        closes = [c[4] for c in ohlcv_15m]
        volumes = [c[5] for c in ohlcv_15m]
        price = closes[-1]

        stoch = _calc_stoch_rsi(closes)
        bb_upper, bb_mid, bb_lower = _calc_bollinger(closes)

        # Volume ratio
        lookback = 20
        if len(volumes) >= lookback + 1:
            avg_vol = sum(volumes[-lookback - 1:-1]) / lookback
            vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0
        else:
            vol_ratio = 1.0

        # 1h trend from EMA 20/50 — same as Sniper trend_timeframe
        trend = "neutral"
        try:
            ohlcv_1h = exchange.fetch_ohlcv("SLP-20DEC30-CDE", "1h", limit=60)
            if ohlcv_1h and len(ohlcv_1h) >= 52:
                closes_1h = [c[4] for c in ohlcv_1h]
                ema_f = _calc_ema(closes_1h, 20)
                ema_s = _calc_ema(closes_1h, 50)
                tol = 0.002
                if ema_f > ema_s * (1 + tol):
                    trend = "up"
                elif ema_f < ema_s * (1 - tol):
                    trend = "down"
        except Exception:
            pass

        return {
            "price": price,
            "stoch_rsi": round(stoch, 4),
            "bb_upper": round(bb_upper, 2),
            "bb_mid": round(bb_mid, 2),
            "bb_lower": round(bb_lower, 2),
            "vol_ratio": round(vol_ratio, 2),
            "trend": trend,
        }
    except Exception as e:
        logger.debug(f"Indicator fetch failed: {e}")
        return {}


def _calc_stoch_rsi(closes, rsi_period=14, stoch_period=14, k_smooth=3):
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


def _calc_ema(data, period):
    if len(data) < period:
        return data[-1] if data else 0
    ema = sum(data[:period]) / period
    k = 2 / (period + 1)
    for v in data[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _calc_bollinger(closes, period=20, std_mult=2.0):
    import math
    if len(closes) < period:
        c = closes[-1]
        return c * 1.02, c, c * 0.98
    window = closes[-period:]
    mid = sum(window) / period
    std = math.sqrt(sum((x - mid) ** 2 for x in window) / period)
    return mid + std_mult * std, mid, mid - std_mult * std


def _build_conditions(indicators: dict) -> dict:
    """Build long/short signal conditions from indicators."""
    if not indicators or "stoch_rsi" not in indicators:
        return {}

    stoch = indicators["stoch_rsi"]
    price = indicators.get("price", 0)
    bb_upper = indicators.get("bb_upper", 0)
    bb_lower = indicators.get("bb_lower", 0)
    vol_ratio = indicators.get("vol_ratio", 1.0)
    trend = indicators.get("trend", "neutral")

    # Momentum breakout logic (reversed from mean reversion):
    # Long = breakout up (StochRSI overbought + price above BB upper)
    # Short = breakdown (StochRSI oversold + price below BB lower)
    l_stoch = stoch > 0.88
    l_bb = price >= bb_upper if bb_upper else False
    l_vol = vol_ratio >= 1.2
    l_trend = trend != "down"  # trend not against long
    l_met = sum([l_stoch, l_bb, l_vol, l_trend])

    s_stoch = stoch < 0.12
    s_bb = price <= bb_lower if bb_lower else False
    s_vol = vol_ratio >= 1.2
    s_trend = trend != "up"  # trend not against short
    s_met = sum([s_stoch, s_bb, s_vol, s_trend])

    signal = None
    if l_stoch and l_bb and l_vol and l_trend:
        signal = {"direction": "long", "price": price, "stoch_rsi": stoch, "time": time.strftime("%H:%M:%S")}
    elif s_stoch and s_bb and s_vol and s_trend:
        signal = {"direction": "short", "price": price, "stoch_rsi": stoch, "time": time.strftime("%H:%M:%S")}

    return {
        "long": {"stoch_rsi": {"met": l_stoch, "value": stoch}, "bb_upper": {"met": l_bb, "value": price}, "volume": {"met": l_vol, "value": vol_ratio}, "trend": {"met": l_trend, "value": trend}, "total_met": l_met},
        "short": {"stoch_rsi": {"met": s_stoch, "value": stoch}, "bb_lower": {"met": s_bb, "value": price}, "volume": {"met": s_vol, "value": vol_ratio}, "trend": {"met": s_trend, "value": trend}, "total_met": s_met},
        "signal": signal,
    }


def _read_recent_trades(limit=20) -> list:
    """Read recent trades from sol_sniper.db."""
    try:
        if not SNIPER_DB.exists():
            return []
        import sqlite3
        conn = sqlite3.connect(str(SNIPER_DB), timeout=3)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM trade_log ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        trades = []
        for r in rows:
            pnl = float(r["pnl"] or 0)
            if pnl == 0:
                continue  # skip open entries
            side = (r["side"] or "").upper()
            is_grid = "GRID" in side
            row_keys = r.keys()

            # Direction: prefer the first-class column, fall back to side-inference
            direction = r["direction"] if "direction" in row_keys and r["direction"] else None
            if not direction:
                if is_grid:
                    direction = "long" if "BUY" in side else "short"
                else:
                    direction = "long" if side == "SELL" else "short"

            # Entry / exit price: prefer first-class columns
            entry_price = (
                float(r["entry_price"]) if "entry_price" in row_keys and r["entry_price"] is not None
                else float(r["price"] or 0)
            )
            exit_price = (
                float(r["exit_price"]) if "exit_price" in row_keys and r["exit_price"] is not None
                else round(float(r["price"] or 0) + (pnl / float(r["quantity"] or 1)), 2)
            )

            # Exit reason: prefer recorded value; only fall back to sign(pnl) for legacy rows
            exit_reason = r["exit_reason"] if "exit_reason" in row_keys and r["exit_reason"] else None
            if not exit_reason:
                exit_reason = "tp" if pnl > 0 else "sl"

            usdt_val = float(r["usdt_value"] or 0) if "usdt_value" in row_keys else 0
            pnl_pct = pnl / usdt_val if usdt_val > 0 else 0

            trades.append({
                "time": time.strftime("%m-%d %H:%M", time.localtime(float(r["timestamp"] or 0))),
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "exit_reason": exit_reason,
                "is_grid": is_grid,
                "instance_name": r["instance_name"] if "instance_name" in row_keys else None,
                "strategy_version": r["strategy_version"] if "strategy_version" in row_keys else None,
            })
        return trades
    except Exception:
        return []


_last_broadcast_dir = None

def _broadcast_signal(sig: dict):
    """Call the signal-broadcast endpoint to notify all paid users."""
    global _last_broadcast_dir
    direction = sig.get("direction")
    if direction == _last_broadcast_dir:
        return  # Don't spam same signal
    _last_broadcast_dir = direction

    broadcast_url = os.environ.get("BROADCAST_URL", "")
    broadcast_secret = os.environ.get("BROADCAST_SECRET", "")
    if not broadcast_url or not broadcast_secret:
        return

    try:
        payload = json.dumps({"signal": sig, "secret": broadcast_secret}).encode()
        req = Request(broadcast_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "iBitLabs-Sniper/3.2")
        with urlopen(req, timeout=10) as resp:
            logger.info(f"[BROADCAST] Signal sent: {direction} — {resp.status}")
    except Exception as e:
        logger.warning(f"[BROADCAST] Failed: {e}")


def broadcast_signal(signal: dict):
    """Public wrapper — broadcast open signal to all paid users via Telegram + Twitter."""
    sig = {
        "direction": signal.get("direction", "unknown"),
        "price": signal.get("entry_price", signal.get("price", 0)),
        "stoch_rsi": signal.get("stoch_rsi", 0),
        "time": time.strftime("%H:%M:%S"),
    }
    _broadcast_signal(sig)
    try:
        tweet_signal_open(sig["direction"], sig["price"], sig["stoch_rsi"])
    except Exception as e:
        logger.debug(f"[TWITTER] Signal tweet error: {e}")


def broadcast_grid_event(event_type: str, details: dict):
    """Broadcast grid events (fill, tp, mode switch) to all paid users."""
    broadcast_url = os.environ.get("BROADCAST_URL", "")
    broadcast_secret = os.environ.get("BROADCAST_SECRET", "")
    if not broadcast_url or not broadcast_secret:
        return

    try:
        payload = json.dumps({
            "grid_event": {"type": event_type, **details},
            "secret": broadcast_secret,
        }).encode()
        req = Request(broadcast_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "iBitLabs-Sniper/3.2")
        with urlopen(req, timeout=10) as resp:
            logger.info(f"[BROADCAST] Grid {event_type} — {resp.status}")
    except Exception as e:
        logger.warning(f"[BROADCAST] Grid failed: {e}")
    if event_type == "trade":
        try:
            tweet_grid_trade(details.get("side",""), details.get("entry",0),
                           details.get("exit",0), details.get("pnl",0),
                           details.get("total_pnl",0))
        except Exception as e:
            logger.debug(f"[TWITTER] Grid tweet error: {e}")


def broadcast_close(direction: str, entry_price: float, exit_price: float, pnl_usd: float, pnl_pct: float, reason: str):
    """Broadcast position close to all paid users via Telegram + Email."""
    broadcast_url = os.environ.get("BROADCAST_URL", "")
    broadcast_secret = os.environ.get("BROADCAST_SECRET", "")
    if not broadcast_url or not broadcast_secret:
        return

    try:
        payload = json.dumps({
            "close": {
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "reason": reason,
                "time": time.strftime("%H:%M:%S"),
            },
            "secret": broadcast_secret,
        }).encode()
        req = Request(broadcast_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "iBitLabs-Sniper/3.2")
        with urlopen(req, timeout=10) as resp:
            logger.info(f"[BROADCAST] Close sent: {direction} {reason} — {resp.status}")
    except Exception as e:
        logger.warning(f"[BROADCAST] Close failed: {e}")
    try:
        tweet_signal_close(direction, entry_price, exit_price, pnl_usd, pnl_pct, reason)
    except Exception as e:
        logger.debug(f"[TWITTER] Close tweet error: {e}")


def _write_kv(key: str, value: str):
    """Write a key-value pair to Cloudflare KV."""
    url = (
        f"{KV_API_BASE}/accounts/{CF_ACCOUNT_ID}"
        f"/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}"
        f"/values/{key}"
    )
    try:
        req = Request(url, data=value.encode(), method="PUT")
        req.add_header("Authorization", f"Bearer {CF_API_TOKEN}")
        req.add_header("Content-Type", "text/plain")
        with urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.debug(f"[KV] Published {key}")
            else:
                logger.warning(f"[KV] Publish {key} failed: {resp.status}")
    except URLError as e:
        logger.warning(f"[KV] Publish failed: {e}")
    except Exception as e:
        logger.warning(f"[KV] Publish error: {e}")
