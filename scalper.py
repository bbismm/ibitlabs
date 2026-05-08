#!/usr/bin/env python3
"""
网格刷单器 — Scalper Agent (Coinbase 现货版)
用 Coinbase Advanced Trade API 下 SOL-USDC 现货限价单
手续费 ~0.12% vs 期货 0.59% — 现货网格更赚钱

用法: bash start_scalper.sh
"""

import sys
import os
import json
import time
import signal
import logging
import math
import uuid
import ccxt

from config import Config
from state_db import StateDB
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scalper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

running = True
active_grids = {}
daily_pnl = 0.0
daily_trades = 0
day_start = time.strftime("%Y-%m-%d")
net_inventory = {}  # base → SOL holdings (spot: always >= 0)
btc_prices_15m = []  # BTC价格记录 (用于联动监控)

# 现货产品映射 (Coinbase Advanced Trade)
SPOT_PRODUCTS = {
    "SOL": {"id": "SOL-USD", "price_decimals": 2, "tick_size": 0.01, "min_size": 0.01},
    "BTC": {"id": "BTC-USD", "price_decimals": 2, "tick_size": 0.01, "min_size": 0.0001},
    "ETH": {"id": "ETH-USD", "price_decimals": 2, "tick_size": 0.01, "min_size": 0.001},
}

# Keep CFM_PRODUCTS for reference (futures position closing)
CFM_PRODUCTS = {
    "SOL": {"id": "SLP-20DEC30-CDE", "price_decimals": 2, "tick_size": 0.01},
}


def signal_handler(sig, frame):
    global running
    logger.info("[Scalper] 收到终止信号...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def create_exchange(config):
    import os
    exchange = ccxt.coinbase({
        "apiKey": os.environ.get("CB_API_KEY", ""),
        "secret": os.environ.get("CB_API_SECRET", ""),
        "enableRateLimit": True,
    })
    return exchange


def get_spot_info(symbol):
    """从交易对获取现货产品信息"""
    base = symbol.split("/")[0]
    return SPOT_PRODUCTS.get(base)


def get_current_price(exchange, symbol):
    """获取当前价格"""
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker.get("last", 0)
    except Exception:
        # 备选: 用现货价格
        spot_sym = symbol.replace(":USDC", "").replace("/USDC", "/USDC")
        try:
            ticker = exchange.fetch_ticker(spot_sym)
            return ticker.get("last", 0)
        except Exception:
            return 0


def format_price(price, decimals):
    """格式化价格，确保精度正确"""
    if decimals <= 0:
        return str(int(price))
    return f"{price:.{decimals}f}"


def place_order(exchange, product_id, side, size, price, price_decimals=2):
    """用 Coinbase Advanced Trade API 下现货限价单"""
    try:
        price_str = format_price(price, price_decimals)
        # 现货: base_size 用小数 (如 "0.99" SOL)
        size_str = f"{size:.8f}".rstrip('0').rstrip('.')
        resp = exchange.v3PrivatePostBrokerageOrders({
            "client_order_id": str(uuid.uuid4()),
            "product_id": product_id,
            "side": side.upper(),
            "order_configuration": {
                "limit_limit_gtc": {
                    "base_size": size_str,
                    "limit_price": price_str,
                    "post_only": True,
                }
            },
        })
        success = resp.get("success_response", {})
        order_id = success.get("order_id", "")
        if order_id:
            return order_id
        error = resp.get("error_response", {})
        if error:
            logger.warning(f"[Scalper] 下单被拒: {error.get('error', '')} {error.get('message', '')}")
        return None
    except Exception as e:
        logger.warning(f"[Scalper] 下单失败 {product_id} {side} @ {price}: {e}")
        return None


def cancel_order(exchange, order_id):
    """撤单 (现货/期货通用)"""
    try:
        exchange.v3PrivatePostBrokerageOrdersBatchCancel({"order_ids": [order_id]})
    except Exception:
        pass


def get_cfm_order_status(exchange, order_id):
    """查询订单状态"""
    try:
        resp = exchange.v3PrivateGetBrokerageOrdersHistorical({"order_id": order_id})
        order = resp.get("order", {})
        return order.get("status", "UNKNOWN")
    except Exception:
        return "UNKNOWN"


def snap_to_tick(price, tick_size):
    """Align price to tick size (round, not truncate)"""
    return round(round(price / tick_size) * tick_size, 10)


def check_btc_crash(exchange, config):
    """P4: BTC联动监控 — BTC 15分钟跌超阈值则暂停"""
    global btc_prices_15m
    try:
        btc_price = get_current_price(exchange, "BTC/USDC")
        if btc_price <= 0:
            return False
        now = time.time()
        btc_prices_15m.append((now, btc_price))
        # 只保留15分钟内的数据
        btc_prices_15m = [(t, p) for t, p in btc_prices_15m if now - t < 900]
        if len(btc_prices_15m) < 2:
            return False
        oldest_price = btc_prices_15m[0][1]
        change_pct = (btc_price - oldest_price) / oldest_price
        if change_pct < -config.scalper_btc_crash_pct:
            logger.warning(
                f"[Scalper] BTC联动暂停! BTC 15分钟跌 {change_pct*100:.2f}% "
                f"({oldest_price:.0f} → {btc_price:.0f})"
            )
            return True
    except Exception:
        pass
    return False


def check_volatility_pause(exchange, symbol):
    """P3: 波动率过滤器 — 替代4因子信号系统
    5分钟realized vol超过24h中位数2倍则暂停新挂单"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, "5m", limit=300)  # ~25h
        if len(ohlcv) < 50:
            return False
        closes = [c[4] for c in ohlcv]
        # 5分钟收益率
        returns = [abs(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
        # 最近6根(30分钟)的平均波动
        recent_vol = sum(returns[-6:]) / 6
        # 24h中位数波动
        sorted_returns = sorted(returns[:-6]) if len(returns) > 6 else sorted(returns)
        median_vol = sorted_returns[len(sorted_returns) // 2] if sorted_returns else 0
        if median_vol > 0 and recent_vol > median_vol * 2:
            logger.info(
                f"[Scalper] 高波动暂停 | 近30分钟vol={recent_vol*100:.3f}% "
                f"vs 中位数={median_vol*100:.3f}% (>{2}x)"
            )
            return True
    except Exception:
        pass
    return False


def build_skewed_grid(exchange, config, base_symbol, current_price, spot_info, inventory, trend=None):
    """现货网格 — 只做多(买低卖高)
    inventory = 我们持有的SOL数量 (>=0, 现货不能做空)
    有SOL才能放卖单"""
    tick = spot_info["tick_size"]
    pd = spot_info["price_decimals"]
    center = snap_to_tick(current_price, tick)

    raw_spacing = current_price * config.scalper_grid_pct
    base_spacing = max(tick, snap_to_tick(raw_spacing, tick))

    n = config.scalper_levels
    qty_per_grid = round(config.scalper_position_usdt / current_price, 4)

    buy_levels = []
    sell_levels = []

    # 现货: SELL上限 = 持有SOL可以卖多少格
    max_sell_by_inv = int(inventory / qty_per_grid) if qty_per_grid > 0 else 0
    max_buy = n
    max_sell = min(n, max_sell_by_inv)

    for i in range(1, max_buy + 1):
        buy_price = center - base_spacing * i
        if buy_price > 0:
            buy_levels.append({"price": round(buy_price, pd), "qty": qty_per_grid, "index": -i})

    for i in range(1, max_sell + 1):
        sell_price = center + base_spacing * i
        sell_levels.append({"price": round(sell_price, pd), "qty": qty_per_grid, "index": i})

    logger.info(
        f"[Scalper] Grid | SOL={inventory:.4f} | "
        f"BUY {max_buy} levels | SELL {max_sell} levels | spacing=${base_spacing:.2f}"
    )

    return {
        "base": base_symbol,
        "product_id": spot_info["id"],
        "price_decimals": pd,
        "tick_size": tick,
        "center_price": center,
        "spacing": base_spacing,
        "qty_per_grid": qty_per_grid,
        "buy_levels": buy_levels,
        "sell_levels": sell_levels,
    }


MONITOR_STATE_FILE = os.path.join(os.path.dirname(__file__), "monitor_state.json")
seen_fill_ids = set()  # Track fills we've already processed


def check_exchange_fills(exchange, db, notifier_inst, config, monitor=None, local_trend=None):
    """Detect new spot fills from exchange API and place reverse orders."""
    global daily_pnl, daily_trades, net_inventory, seen_fill_ids, active_grids
    if local_trend is None:
        local_trend = {}
    new_fills = []
    try:
        resp = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
            "order_status": "FILLED",
            "product_type": "SPOT",
            "limit": "20",
        })
        for o in resp.get("orders", []):
            oid = o.get("order_id", "")
            if oid in seen_fill_ids:
                continue
            seen_fill_ids.add(oid)

            price = float(o.get("average_filled_price", 0) or 0)
            qty = float(o.get("filled_size", 0) or 0)
            side = o.get("side", "")
            product = o.get("product_id", "")
            fee = float(o.get("total_fees", 0) or 0)

            if price == 0 or qty == 0:
                continue

            # Update inventory (spot: base from product_id like "SOL-USDC")
            base = product.split("-")[0]
            if side == "BUY":
                net_inventory[base] = net_inventory.get(base, 0) + qty
            elif side == "SELL":
                net_inventory[base] = max(0, net_inventory.get(base, 0) - qty)

            # Log to DB
            db.log_trade(product, side, price, qty, price * qty, 0)
            daily_trades += 1

            # Place reverse order
            grid = active_grids.get(base)
            if grid:
                pd_r = grid.get("price_decimals", 2)
                tick = grid.get("tick_size", 0.01)
                spacing = grid.get("spacing", price * config.scalper_grid_pct)
                inv = net_inventory.get(base, 0)

                if side == "BUY":
                    # BUY filled → place SELL above (we now have SOL to sell)
                    sell_price = snap_to_tick(price + spacing, tick)
                    oid_new = place_order(exchange, product, "SELL", qty, sell_price, pd_r)
                    if oid_new:
                        db.save_order(oid_new, product, "SELL", sell_price, qty, 0)
                        logger.info(f"[Scalper] Reverse SELL @ ${sell_price:.2f}")
                elif side == "SELL":
                    # SELL filled → place BUY below (profit realized!)
                    buy_price = snap_to_tick(price - spacing, tick)
                    oid_new = place_order(exchange, product, "BUY", qty, buy_price, pd_r)
                    if oid_new:
                        db.save_order(oid_new, product, "BUY", buy_price, qty, 0)
                        logger.info(f"[Scalper] Reverse BUY @ ${buy_price:.2f}")
                    # Estimate realized PnL (sold higher than bought)
                    est_pnl = spacing * qty - fee
                    daily_pnl += est_pnl

            new_fills.append({
                "side": side, "product": product,
                "price": price, "qty": qty, "fee": fee,
            })
            logger.info(
                f"[Scalper] FILL {side} {product} @ ${price:,.2f} x {qty:.4f} "
                f"| fee=${fee:.4f} | SOL={net_inventory.get(base, 0):.4f}"
            )
            notifier_inst._send(
                f"Scalper {side}",
                f"{product} @ ${price:,.2f} x {qty:.4f} | SOL={net_inventory.get(base, 0):.4f}"
            )

    except Exception as e:
        logger.warning(f"[Scalper] Fill check failed: {e}")

    return new_fills


def read_monitor_state():
    """读取操盘团队的决策信号"""
    try:
        if os.path.exists(MONITOR_STATE_FILE):
            with open(MONITOR_STATE_FILE, "r") as f:
                state = json.load(f)
            # 检查是否过期 (>5分钟视为无效)
            ts = state.get("ts", "")
            if ts:
                from datetime import datetime
                state_time = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                age = (datetime.now() - state_time).total_seconds()
                if age > 300:
                    return None  # 数据过期
            return state
    except Exception:
        pass
    return None


def detect_trend_early(exchange, symbol):
    """早期趋势检测 — 比Monitor更快，用SOL自身信号
    Returns: 'trending_up', 'trending_down', or None (ranging)
    任意一个触发即返回:
      1. 1min连续3根同方向K线
      2. 价格偏离VWAP > 0.8%
      3. 5min EMA斜率 > 0.2%
    """
    try:
        # Signal 1: 1min连续3根同方向K线
        ohlcv_1m = exchange.fetch_ohlcv(symbol, "1m", limit=10)
        if len(ohlcv_1m) >= 4:
            closes_1m = [c[4] for c in ohlcv_1m[-4:]]
            up_count = sum(1 for i in range(1, 4) if closes_1m[i] > closes_1m[i-1])
            dn_count = sum(1 for i in range(1, 4) if closes_1m[i] < closes_1m[i-1])
            if up_count == 3:
                logger.info(f"[Trend] {symbol} EARLY UP — 3 green 1min candles")
                return "trending_up"
            if dn_count == 3:
                logger.info(f"[Trend] {symbol} EARLY DOWN — 3 red 1min candles")
                return "trending_down"

        # Signal 2 & 3: VWAP deviation + 5min EMA slope (same data fetch)
        ohlcv_5m = exchange.fetch_ohlcv(symbol, "5m", limit=50)
        if len(ohlcv_5m) >= 12:
            # VWAP (typical price × volume weighted)
            tp_vol = sum((c[2] + c[3] + c[4]) / 3 * c[5] for c in ohlcv_5m)
            vol_sum = sum(c[5] for c in ohlcv_5m)
            vwap = tp_vol / vol_sum if vol_sum > 0 else 0
            current_price = ohlcv_5m[-1][4]
            if vwap > 0:
                dev = (current_price - vwap) / vwap
                if dev > 0.008:
                    logger.info(f"[Trend] {symbol} EARLY UP — {dev*100:.2f}% above VWAP ${vwap:.2f}")
                    return "trending_up"
                if dev < -0.008:
                    logger.info(f"[Trend] {symbol} EARLY DOWN — {dev*100:.2f}% below VWAP ${vwap:.2f}")
                    return "trending_down"

            # EMA-9 slope (last 2 periods)
            closes_5m = [c[4] for c in ohlcv_5m]
            k = 2 / (9 + 1)
            ema_cur = closes_5m[0]
            for p in closes_5m[1:]:
                ema_cur = p * k + ema_cur * (1 - k)
            ema_prev = closes_5m[0]
            for p in closes_5m[1:-1]:
                ema_prev = p * k + ema_prev * (1 - k)
            slope = (ema_cur - ema_prev) / ema_prev if ema_prev > 0 else 0
            if slope > 0.002:
                logger.info(f"[Trend] {symbol} EARLY UP — EMA slope +{slope*100:.3f}%")
                return "trending_up"
            if slope < -0.002:
                logger.info(f"[Trend] {symbol} EARLY DOWN — EMA slope {slope*100:.3f}%")
                return "trending_down"

    except Exception as e:
        logger.warning(f"[Trend] detect_trend_early failed: {e}")
    return None


def calc_dynamic_spacing(exchange, symbol, base_pct=0.008):
    """动态间距 — Advanced Trade maker fee 0.35%, 来回0.70%, 间距必须>0.70%
    低波动 → 0.8% | 正常 → 1.0% | 高波动 → 1.5% | 极高 → 2.0%
    """
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, "5m", limit=50)
        if len(ohlcv) < 20:
            return base_pct
        closes = [c[4] for c in ohlcv]
        returns = [abs(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
        recent_vol = sum(returns[-6:]) / 6
        median_vol = sorted(returns)[len(returns) // 2]
        ratio = recent_vol / median_vol if median_vol > 0 else 1.0
        if ratio < 0.7:
            spacing = 0.008   # 0.8% — low vol, minimum profitable
        elif ratio < 1.5:
            spacing = 0.010   # 1.0% — normal vol
        elif ratio < 2.5:
            spacing = 0.015   # 1.5% — high vol
        else:
            spacing = 0.020   # 2.0% — extreme vol
        if abs(spacing - base_pct) > 0.0005:
            logger.info(f"[DynSpacing] {symbol} vol_ratio={ratio:.2f} → {spacing*100:.1f}%")
        return spacing
    except Exception:
        return base_pct


def reduce_inventory_active(exchange, db, base, grid, net_inv, current_price, reduce_pct=1.0):
    """主动减仓 — 现货只能卖出SOL (不能做空)
    reduce_pct: 1.0=全卖, 0.5=卖一半
    """
    if net_inv <= 0:
        return
    product_id = grid["product_id"]
    pd_r = grid.get("price_decimals", 2)
    tick = grid.get("tick_size", 0.01)
    qty_to_sell = round(net_inv * reduce_pct, 4)
    if qty_to_sell < 0.01:
        return
    sell_price = snap_to_tick(current_price * 0.999, tick)  # 略低于市价，确保成交
    oid = place_order(exchange, product_id, "SELL", qty_to_sell, sell_price, pd_r)
    if oid:
        logger.warning(
            f"[Scalper] ACTIVE REDUCE SELL {qty_to_sell:.4f} {product_id} @ ${sell_price:.2f} "
            f"(SOL {net_inv:.4f} → {net_inv - qty_to_sell:.4f})"
        )


def build_micro_grid(exchange, config, base_symbol, current_price, spot_info):
    """构建微型网格，价格对齐到tick size"""
    tick = spot_info["tick_size"]
    pd = spot_info["price_decimals"]

    # 中心价格对齐到 tick
    center = snap_to_tick(current_price, tick)

    # 间距至少1个tick
    raw_spacing = current_price * config.scalper_grid_pct
    spacing = max(tick, snap_to_tick(raw_spacing, tick))

    n = config.scalper_levels
    qty_per_grid = max(1, math.ceil(config.scalper_position_usdt / current_price))

    buy_levels = []
    sell_levels = []

    for i in range(1, n + 1):
        buy_price = center - spacing * i
        if buy_price > 0:
            buy_levels.append({"price": int(buy_price) if pd == 0 else buy_price, "qty": qty_per_grid, "index": -i})

        sell_price = center + spacing * i
        sell_levels.append({"price": int(sell_price) if pd == 0 else sell_price, "qty": qty_per_grid, "index": i})

    return {
        "base": base_symbol,
        "product_id": spot_info["id"],
        "price_decimals": pd,
        "tick_size": tick,
        "center_price": center,
        "spacing": spacing,
        "qty_per_grid": qty_per_grid,
        "buy_levels": buy_levels,
        "sell_levels": sell_levels,
    }


def main():
    global daily_pnl, daily_trades, day_start

    config = Config()
    try:
        config.validate_futures()  # same Coinbase API keys
    except ValueError as e:
        logger.error(e)
        sys.exit(1)

    # 现货产品
    scalper_bases = []
    for sym in config.scalper_symbols:
        base = sym.split("/")[0]
        info = get_spot_info(base)
        if info:
            scalper_bases.append({"base": base, "symbol": sym, "product_id": info["id"], "spot_info": info})

    logger.info("=" * 60)
    logger.info("  网格刷单器 V4 — Coinbase 现货")
    logger.info(f"  交易对: {', '.join(b['product_id'] for b in scalper_bases)}")
    logger.info(f"  网格间距: {config.scalper_grid_pct * 100:.1f}%")
    logger.info(f"  每格仓位: ${config.scalper_position_usdt}")
    logger.info(f"  网格层数: {config.scalper_levels} (买低卖高)")
    logger.info(f"  日亏损上限: ${config.scalper_max_daily_loss}")
    logger.info(f"  检查间隔: {config.scalper_interval_seconds}s")
    logger.info("=" * 60)

    exchange = create_exchange(config)
    db = StateDB(config.scalper_db_path)
    notifier = Notifier()

    # 验证连接 + 查USDC余额
    cash_balance = 0
    try:
        exchange.load_markets()
        accounts = exchange.v3PrivateGetBrokerageAccounts({"limit": "100"})
        for acc in accounts.get("accounts", []):
            currency = acc.get("currency", "")
            avail = float(acc.get("available_balance", {}).get("value", 0) or 0)
            if currency in ("USD", "USDC"):
                cash_balance += avail
            elif currency == "SOL":
                net_inventory["SOL"] = avail
        logger.info(f"[Scalper] 连接成功 | 现金=${cash_balance:.2f} | SOL={net_inventory.get('SOL', 0):.4f}")
        notifier.on_startup("Coinbase Spot Scalper (0 fee)", cash_balance, [b["product_id"] for b in scalper_bases])
    except Exception as e:
        logger.error(f"[Scalper] 连接失败: {e}")
        sys.exit(1)

    # Pre-load existing spot fills
    try:
        resp = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
            "order_status": "FILLED",
            "product_type": "SPOT",
            "limit": "50",
        })
        for o in resp.get("orders", []):
            seen_fill_ids.add(o.get("order_id", ""))
        logger.info(f"[Scalper] Pre-loaded {len(seen_fill_ids)} existing fills")
    except Exception:
        pass

    # 清理旧现货挂单
    try:
        resp = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
            "order_status": "OPEN",
            "product_type": "SPOT",
            "limit": "100",
        })
        old_orders = resp.get("orders", [])
        if old_orders:
            old_ids = [o["order_id"] for o in old_orders]
            exchange.v3PrivatePostBrokerageOrdersBatchCancel({"order_ids": old_ids})
            logger.info(f"[Scalper] 启动清理: 撤销 {len(old_ids)} 个旧挂单")
            for b in scalper_bases:
                db.clear_orders(b["product_id"])
            time.sleep(2)
    except Exception as e:
        logger.warning(f"[Scalper] 清理旧挂单失败: {e}")

    # 建初始网格
    for b in scalper_bases:
        price = get_current_price(exchange, b["symbol"])
        if price <= 0:
            continue

        inv = net_inventory.get(b["base"], 0)
        grid = build_skewed_grid(exchange, config, b["base"], price, b["spot_info"], inv)
        placed = 0

        for level in grid["buy_levels"]:
            oid = place_order(exchange, b["product_id"], "BUY", level["qty"], level["price"], b["spot_info"]["price_decimals"])
            if oid:
                db.save_order(oid, b["product_id"], "BUY", level["price"], level["qty"], level["index"])
                placed += 1

        for level in grid["sell_levels"]:
            oid = place_order(exchange, b["product_id"], "SELL", level["qty"], level["price"], b["spot_info"]["price_decimals"])
            if oid:
                db.save_order(oid, b["product_id"], "SELL", level["price"], level["qty"], level["index"])
                placed += 1

        if placed > 0:
            active_grids[b["base"]] = grid
            logger.info(
                f"[Scalper] {b['product_id']} 网格就绪 | 中心: {price} | "
                f"间距: {grid['spacing']} | {placed}个挂单"
            )
            notifier.on_grid_created(b["product_id"], placed, "高频期货")

    # ── 主循环 ──
    rebalance_counter = 0
    local_trend = {}  # base → 'trending_up'/'trending_down'/None

    while running:
        try:
            today = time.strftime("%Y-%m-%d")
            if today != day_start:
                logger.info(f"[Scalper] New day | Yesterday PnL: ${daily_pnl:.4f} | Trades: {daily_trades}")
                daily_pnl = 0.0
                daily_trades = 0
                day_start = today
            # PnL tracked from fills (spot has no daily_realized_pnl API)

            if daily_pnl < -config.scalper_max_daily_loss:
                logger.warning(f"[Scalper] 每日亏损保护！PnL: ${daily_pnl:.4f}")
                notifier._send("Scalper 暂停", f"日亏损 ${daily_pnl:.4f} 超限")
                time.sleep(60)
                continue

            if daily_trades >= config.scalper_max_daily_trades:
                time.sleep(60)
                continue

            # P4: BTC联动监控
            if check_btc_crash(exchange, config):
                notifier._send("BTC联动暂停", "BTC 15分钟跌幅过大，网格暂停15分钟")
                time.sleep(900)  # 暂停15分钟
                btc_prices_15m.clear()
                continue

            # 早期趋势检测 (每次循环，用SOL自身信号)
            for b in scalper_bases:
                sym = f"{b['base']}/USDC"
                detected = detect_trend_early(exchange, sym)
                prev_trend = local_trend.get(b["base"])
                local_trend[b["base"]] = detected
                # 趋势反转时主动减仓 (现货只能卖出SOL)
                if b["base"] in active_grids and detected != prev_trend and detected is not None:
                    inv = net_inventory.get(b["base"], 0)
                    price = get_current_price(exchange, sym)
                    if price > 0 and detected == "trending_down" and inv > 0:
                        logger.warning(f"[Trend] {b['base']} trend→DOWN with SOL={inv:.4f} — sell 50%")
                        reduce_inventory_active(exchange, db, b["base"], active_grids[b["base"]], inv, price, reduce_pct=0.5)

            # 操盘团队信号
            monitor = read_monitor_state()
            if monitor:
                mon_action = monitor.get("action", "run")
                mon_alerts = monitor.get("alerts", [])

                # BLACK SWAN — widen grid instead of full shutdown
                # (Drift hack is on Drift, not SOL itself)
                if False and any("BLACK_SWAN" in a for a in mon_alerts):
                    logger.warning(f"[Scalper] BLACK SWAN — EMERGENCY SHUTDOWN")
                    logger.warning(f"  Reasons: {'; '.join(monitor.get('reasons', []))}")
                    notifier._send("BLACK SWAN", "Emergency shutdown — canceling all orders, closing all positions")

                    # Cancel all open orders
                    try:
                        resp = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                            "order_status": "OPEN", "product_type": "SPOT", "limit": "100",
                        })
                        order_ids = [o["order_id"] for o in resp.get("orders", [])]
                        if order_ids:
                            exchange.v3PrivatePostBrokerageOrdersBatchCancel({"order_ids": order_ids})
                            logger.info(f"[Scalper] Canceled {len(order_ids)} orders")
                    except Exception as e:
                        logger.error(f"[Scalper] Cancel orders failed: {e}")

                    # 现货: 卖出所有SOL持仓
                    try:
                        for base_key, inv_qty in net_inventory.items():
                            if inv_qty > 0:
                                price = get_current_price(exchange, f"{base_key}/USDC")
                                sell_price = snap_to_tick(price * 0.99, 0.01)
                                product = f"{base_key}-USDC"
                                place_order(exchange, product, "SELL", inv_qty, sell_price, 2)
                                logger.info(f"[Scalper] Emergency SELL {inv_qty:.4f} {product} @ ${sell_price:.2f}")
                    except Exception as e:
                        logger.error(f"[Scalper] Emergency sell failed: {e}")

                    # Clear local state
                    for base in list(active_grids.keys()):
                        db.clear_orders(active_grids[base]["product_id"])
                    active_grids.clear()
                    net_inventory.clear()
                    notifier._send("SHUTDOWN COMPLETE", "All orders canceled, positions closing. Waiting for all-clear.")

                    # Wait until black swan clears (check every 60s)
                    while running:
                        time.sleep(60)
                        m = read_monitor_state()
                        if m and not any("BLACK_SWAN" in a for a in m.get("alerts", [])):
                            logger.info("[Scalper] Black swan cleared — resuming")
                            notifier._send("RESUMING", "Black swan cleared, rebuilding grid")
                            break
                        logger.info("[Scalper] Black swan still active — staying flat")
                    continue

                if mon_action == "pause":
                    logger.info(f"[Scalper] Monitor: PAUSE | {'; '.join(monitor.get('reasons', []))}")
                    time.sleep(30)
                    continue

                # Wall gone — emergency rebuild to normal wide grid
                if any("WALL_GONE" in a for a in mon_alerts):
                    logger.warning(f"[Scalper] WALL GONE — emergency rebuild to wide grid")
                    config.scalper_grid_pct = 0.008  # Reset to default 0.8%
                    config.scalper_levels = 8
                    for base, grid in list(active_grids.items()):
                        product_id = grid["product_id"]
                        for o in db.get_active_orders(product_id):
                            cancel_order(exchange, o["order_id"])
                        db.clear_orders(product_id)
                        sym = f"{base}/USDC"
                        price = get_current_price(exchange, sym)
                        if price > 0:
                            inv = net_inventory.get(base, 0)
                            spot_info = SPOT_PRODUCTS.get(base)
                            mon_regime = monitor.get("regime") if monitor else None
                            effective_trend_r = local_trend.get(base) or mon_regime
                            config.scalper_grid_pct = calc_dynamic_spacing(exchange, f"{base}/USDC", config.scalper_grid_pct)
                            new_grid = build_skewed_grid(exchange, config, base, price, spot_info, inv, trend=effective_trend_r)
                            placed = 0
                            pd_r = spot_info.get("price_decimals", 0)
                            for level in new_grid["buy_levels"]:
                                oid = place_order(exchange, product_id, "BUY", level["qty"], level["price"], pd_r)
                                if oid:
                                    db.save_order(oid, product_id, "BUY", level["price"], level["qty"], level["index"])
                                    placed += 1
                            for level in new_grid["sell_levels"]:
                                oid = place_order(exchange, product_id, "SELL", level["qty"], level["price"], pd_r)
                                if oid:
                                    db.save_order(oid, product_id, "SELL", level["price"], level["qty"], level["index"])
                                    placed += 1
                            if placed > 0:
                                active_grids[base] = new_grid
                                logger.info(f"[Scalper] Emergency rebuild: {placed} orders, spacing={config.scalper_grid_pct*100:.1f}%")
                    notifier._send("WALL GONE", "Wall disappeared — grid reset to 0.8% wide mode")
                    continue

                # wall_grid — build grid between whale walls
                if mon_action == "wall_grid" and rebalance_counter % 30 == 0:
                    wall_low = monitor.get("wall_low", 0)
                    wall_high = monitor.get("wall_high", 0)
                    wall_range_pct = (wall_high - wall_low) / wall_low * 100 if wall_low > 0 else 0
                    # Only use wall grid if range > 1.5%
                    if wall_low > 0 and wall_high > wall_low and wall_range_pct >= 1.5:
                        for base, grid in list(active_grids.items()):
                            product_id = grid["product_id"]
                            sym = f"{base}/USDC"
                            price = get_current_price(exchange, sym)
                            if price <= 0:
                                continue
                            # Only rebuild if walls changed significantly
                            old_center = grid.get("center_price", 0)
                            new_center = (wall_low + wall_high) / 2
                            if abs(new_center - old_center) / old_center < 0.002 if old_center > 0 else False:
                                continue

                            logger.info(
                                f"[Scalper] WALL GRID | "
                                f"${wall_low:.2f} - ${wall_high:.2f} | "
                                f"range={monitor.get('wall_range_pct', 0):.1f}%"
                            )
                            # Cancel existing
                            for o in db.get_active_orders(product_id):
                                cancel_order(exchange, o["order_id"])
                            db.clear_orders(product_id)

                            spot_info = SPOT_PRODUCTS.get(base)
                            pd_r = spot_info.get("price_decimals", 0)
                            tick = spot_info.get("tick_size", 0.01)
                            n_levels = monitor.get("suggested_levels", 4)
                            qty = round(config.scalper_position_usdt / price, 4)

                            # Spread levels evenly between walls and current price
                            buy_spacing = (price - wall_low) / (n_levels + 1)
                            sell_spacing = (wall_high - price) / (n_levels + 1)

                            placed = 0
                            buy_levels = []
                            sell_levels = []
                            for i in range(1, n_levels + 1):
                                bp = snap_to_tick(price - buy_spacing * i, tick)
                                if bp >= wall_low:
                                    oid = place_order(exchange, product_id, "BUY", qty, bp, pd_r)
                                    if oid:
                                        db.save_order(oid, product_id, "BUY", bp, qty, -i)
                                        buy_levels.append({"price": bp, "qty": qty, "index": -i})
                                        placed += 1

                                sp = snap_to_tick(price + sell_spacing * i, tick)
                                if sp <= wall_high:
                                    oid = place_order(exchange, product_id, "SELL", qty, sp, pd_r)
                                    if oid:
                                        db.save_order(oid, product_id, "SELL", sp, qty, i)
                                        sell_levels.append({"price": sp, "qty": qty, "index": i})
                                        placed += 1

                            if placed > 0:
                                active_grids[base] = {
                                    "base": base, "product_id": product_id,
                                    "price_decimals": pd_r, "tick_size": tick,
                                    "center_price": price,
                                    "spacing": buy_spacing,
                                    "buy_spacing": buy_spacing, "sell_spacing": sell_spacing,
                                    "qty_per_grid": qty,
                                    "buy_levels": buy_levels, "sell_levels": sell_levels,
                                }
                                logger.info(
                                    f"[Scalper] Wall grid built: {placed} orders | "
                                    f"${wall_low:.2f} < grid < ${wall_high:.2f}"
                                )
                                notifier._send(
                                    "Wall Grid",
                                    f"${wall_low:.2f}-${wall_high:.2f}, {placed} orders"
                                )

                # widen/tighten — monitor can suggest wider spacing but NEVER narrower than config baseline
                # Config baseline (3.0%) is the minimum profitable spacing for our fee structure
                if mon_action in ("widen", "tighten") and rebalance_counter % 30 == 0:
                    MIN_SPACING = 0.008  # 0.8% — minimum profitable (maker fee 0.35% × 2 = 0.70%)
                    MAX_LEVELS = 12
                    new_spacing = max(MIN_SPACING, monitor.get("suggested_spacing_pct", config.scalper_grid_pct))
                    new_levels = min(MAX_LEVELS, monitor.get("suggested_levels", config.scalper_levels))
                    if abs(new_spacing - config.scalper_grid_pct) / config.scalper_grid_pct > 0.05:
                        logger.info(
                            f"[Scalper] Monitor: {mon_action.upper()} | "
                            f"spacing {config.scalper_grid_pct*100:.2f}% -> {new_spacing*100:.2f}% | "
                            f"levels {config.scalper_levels} -> {new_levels}"
                        )
                        config.scalper_grid_pct = new_spacing
                        config.scalper_levels = new_levels
                        # 撤单重建所有网格
                        for base, grid in list(active_grids.items()):
                            product_id = grid["product_id"]
                            for o in db.get_active_orders(product_id):
                                cancel_order(exchange, o["order_id"])
                            db.clear_orders(product_id)
                            sym = f"{base}/USDC"
                            price = get_current_price(exchange, sym)
                            if price > 0:
                                inv = net_inventory.get(base, 0)
                                spot_info = SPOT_PRODUCTS.get(base)
                                mon_regime = monitor.get("regime") if monitor else None
                                effective_trend_w = local_trend.get(base) or mon_regime
                                config.scalper_grid_pct = calc_dynamic_spacing(exchange, f"{base}/USDC", new_spacing)
                                new_grid = build_skewed_grid(exchange, config, base, price, spot_info, inv, trend=effective_trend_w)
                                placed = 0
                                pd_r = spot_info.get("price_decimals", 0)
                                for level in new_grid["buy_levels"]:
                                    oid = place_order(exchange, product_id, "BUY", level["qty"], level["price"], pd_r)
                                    if oid:
                                        db.save_order(oid, product_id, "BUY", level["price"], level["qty"], level["index"])
                                        placed += 1
                                for level in new_grid["sell_levels"]:
                                    oid = place_order(exchange, product_id, "SELL", level["qty"], level["price"], pd_r)
                                    if oid:
                                        db.save_order(oid, product_id, "SELL", level["price"], level["qty"], level["index"])
                                        placed += 1
                                if placed > 0:
                                    active_grids[base] = new_grid
                                    logger.info(f"[Scalper] Grid rebuilt: {placed} orders, spacing={config.scalper_grid_pct*100:.2f}%")
                                    notifier._send("Grid Adjusted", f"{mon_action.upper()} → {config.scalper_grid_pct*100:.1f}% spacing, {placed} orders")

            rebalance_counter += 1

            # Check for new fills from exchange API (every 20s)
            if rebalance_counter % 2 == 0:
                fills = check_exchange_fills(exchange, db, notifier, config, monitor, local_trend)
                # Risk 1: Multi-level penetration — if 3+ fills in one batch, emergency action
                if len(fills) >= 3:
                    same_side = {}
                    for f in fills:
                        same_side[f["side"]] = same_side.get(f["side"], 0) + 1
                    for side, count in same_side.items():
                        if count >= 3:
                            logger.warning(
                                f"[Scalper] MULTI-LEVEL PENETRATION: {count} {side} fills in one batch!"
                            )
                            notifier._send("PENETRATION", f"{count}x {side} fills — possible rapid move")
                            # Cancel all orders on opposite side to prevent further accumulation
                            for base, grid in list(active_grids.items()):
                                cancel_side = "SELL" if side == "SELL" else "BUY"
                                for o in db.get_active_orders(grid["product_id"]):
                                    if o["side"] == side:
                                        cancel_order(exchange, o["order_id"])
                                        db.update_order_status(o["order_id"], "CANCELLED")
                                logger.info(f"[Scalper] Canceled remaining {side} orders to stop bleeding")

            # 每分钟心跳 (6次 × 10秒)
            if rebalance_counter % 6 == 0:
                parts = []
                for base in active_grids:
                    p = get_current_price(exchange, f"{base}/USDC")
                    inv = net_inventory.get(base, 0)
                    parts.append(f"{base}=${p:.2f}(inv={inv})")
                btc_p = get_current_price(exchange, "BTC/USDC")
                mon_str = ""
                if monitor:
                    mon_str = f" | 团队: {monitor.get('action','?')}/{monitor.get('regime','?')}"
                logger.info(f"[Scalper] 心跳 | {' '.join(parts)} | BTC=${btc_p:.0f} | PnL: ${daily_pnl:.2f} | 交易: {daily_trades}笔{mon_str}")

            for base, grid in list(active_grids.items()):
                product_id = grid["product_id"]

                # ── 现货止损: 价格偏离中心>5% 且持有SOL → 卖出减仓 ──
                HARD_DRIFT_PCT = 0.05
                try:
                    sym_check = f"{base}/USDC"
                    cur_p_check = get_current_price(exchange, sym_check)
                    center_check = grid.get("center_price", cur_p_check)
                    drift_check = abs(cur_p_check - center_check) / center_check if center_check > 0 else 0
                    inv_check = net_inventory.get(base, 0)

                    # 价格大跌且持有SOL → 卖出50%止损
                    if drift_check > HARD_DRIFT_PCT and cur_p_check < center_check and inv_check > 0:
                        logger.warning(
                            f"[Scalper] HARD STOP drift={drift_check*100:.1f}% down, SOL={inv_check:.4f} → sell 50%"
                        )
                        notifier._send("HARD STOP", f"{base} dropped {drift_check*100:.1f}%, selling 50%")
                        reduce_inventory_active(exchange, db, base, grid, inv_check, cur_p_check, reduce_pct=0.5)
                except Exception as e:
                    logger.warning(f"[Scalper] 止损检查失败: {e}")

                if base not in active_grids:
                    continue

                # Legacy per-order fill check REMOVED (C1+C2 fix)
                # All fill detection now via check_exchange_fills() — single source of truth

                # 每5分钟重平衡 (改为40%触发，专家建议)
                if rebalance_counter % 30 == 0:
                    sym = f"{base}/USDC"
                    price = get_current_price(exchange, sym)
                    if price > 0:
                        center = grid["center_price"]
                        total_range = grid["spacing"] * config.scalper_levels
                        drift_pct = abs(price - center) / center if center > 0 else 0
                        if abs(price - center) > total_range * 0.4:
                            # Volatility check — but force rebuild if drift > 60% (deadlock breaker)
                            if drift_pct < 0.6 and check_volatility_pause(exchange, sym):
                                logger.info(f"[Scalper] {product_id} High vol, skip rebuild (drift={drift_pct*100:.1f}%)")
                            else:
                                inv = net_inventory.get(base, 0)
                                logger.info(f"[Scalper] {product_id} 重平衡 → {price} | 净持仓={inv}")
                                # 撤所有单
                                for o in db.get_active_orders(product_id):
                                    cancel_order(exchange, o["order_id"])
                                db.clear_orders(product_id)

                                spot_info = SPOT_PRODUCTS.get(base, {"id": product_id, "price_decimals": 0})
                                # P2: 重建时使用偏斜网格 + 动态间距
                                mon_regime = monitor.get("regime") if monitor else None
                                effective_trend_rb = local_trend.get(base) or mon_regime
                                config.scalper_grid_pct = calc_dynamic_spacing(exchange, f"{base}/USDC", config.scalper_grid_pct)
                                new_grid = build_skewed_grid(exchange, config, base, price, spot_info, inv, trend=effective_trend_rb)
                                placed = 0
                                pd_r = spot_info.get("price_decimals", 0)
                                for level in new_grid["buy_levels"]:
                                    oid = place_order(exchange, product_id, "BUY", level["qty"], level["price"], pd_r)
                                    if oid:
                                        db.save_order(oid, product_id, "BUY", level["price"], level["qty"], level["index"])
                                        placed += 1
                                for level in new_grid["sell_levels"]:
                                    oid = place_order(exchange, product_id, "SELL", level["qty"], level["price"], pd_r)
                                    if oid:
                                        db.save_order(oid, product_id, "SELL", level["price"], level["qty"], level["index"])
                                        placed += 1
                                if placed > 0:
                                    active_grids[base] = new_grid

            time.sleep(config.scalper_interval_seconds)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"[Scalper] 异常: {e}", exc_info=True)
            time.sleep(10)

    # 退出
    logger.info("[Scalper] 正在清理...")
    for base, grid in active_grids.items():
        product_id = grid["product_id"]
        for o in db.get_active_orders(product_id):
            cancel_order(exchange, o["order_id"])
        db.clear_orders(product_id)
        logger.info(f"[Scalper] {product_id} 挂单已撤销")

    logger.info(f"[Scalper] 已退出 | 今日 PnL: ${daily_pnl:.4f} | 交易: {daily_trades}笔")
    notifier.on_shutdown(daily_pnl)


if __name__ == "__main__":
    main()
