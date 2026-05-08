#!/usr/bin/env python3
"""
自适应网格交易系统 — 主循环 Harness
Harness Engineering: Scanner → Signal Filter → Grid Engine → Executor → Risk Manager
集成 TrendRider 策略: 多时间框架确认 + RSI + EMA + 成交量过滤

默认使用火币(HTX)，改 config.exchange_id 即可切换交易所

用法:
  export HTX_API_KEY='your_key'
  export HTX_API_SECRET='your_secret'
  python main.py              # 正常启动
  python main.py --liquidate  # 先清仓再用新策略重建网格
"""

import sys
import time
import signal
import logging
import ccxt

from config import Config
from state_db import StateDB
from scanner import Scanner
from grid_engine import GridEngine
from executor import Executor
from risk_manager import RiskManager
from notifier import Notifier

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("grid_trader.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ── 全局状态 ──
running = True
active_grids: dict = {}  # symbol → grid dict


def signal_handler(sig, frame):
    global running
    logger.info("[Harness] 收到终止信号，正在优雅退出...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def create_exchange(config: Config) -> ccxt.Exchange:
    """根据配置创建ccxt交易所实例"""
    exchange_class = getattr(ccxt, config.exchange_id, None)
    if exchange_class is None:
        raise ValueError(f"不支持的交易所: {config.exchange_id}")

    exchange = exchange_class({
        "apiKey": config.api_key,
        "secret": config.api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "spot",
        },
    })

    return exchange


def main():
    # ── 1. 初始化配置 ──
    config = Config()
    try:
        config.validate()
    except ValueError as e:
        logger.error(e)
        sys.exit(1)

    exchange_name = config.exchange_id.upper()

    logger.info("=" * 60)
    logger.info(f"  自适应网格交易系统 启动 ({exchange_name})")
    logger.info(f"  同时交易币种数: {config.top_n_coins}")
    logger.info(f"  每网格仓位: {config.position_usdt} USDT")
    logger.info(f"  网格层数: {config.grid_levels} (上下各)")
    logger.info(f"  冷却时间: {config.cooldown_hours}h")
    logger.info(f"  扫描间隔: {config.scan_interval_minutes}min")
    logger.info("=" * 60)

    # ── 2. 初始化各 Agent ──
    exchange = create_exchange(config)
    db = StateDB(config.db_path)
    notifier = Notifier()
    scanner = Scanner(exchange, config)
    grid_engine = GridEngine(exchange, config)
    executor = Executor(exchange, config, db)
    risk_manager = RiskManager(exchange, config, db, executor)

    # 验证连接
    try:
        balance = exchange.fetch_balance()
        usdt_free = float(balance.get("USDT", {}).get("free", 0))
        logger.info(f"[连接] {exchange_name} API 连接成功 | USDT余额: {usdt_free:.2f}")
        notifier.on_startup(exchange_name, usdt_free, config.forced_symbols)
    except Exception as e:
        logger.error(f"[连接] {exchange_name} API 连接失败: {e}")
        sys.exit(1)

    # ── 2b. --liquidate 模式: 撤单 + 市价清仓 ──
    if "--liquidate" in sys.argv:
        logger.info("[清仓] --liquidate 模式，开始清仓...")
        liquidate(exchange, executor, config)
        logger.info("[清仓] 清仓完成，等待3秒后用新策略重建网格...")
        time.sleep(3)
        # 重新查余额
        balance = exchange.fetch_balance()
        usdt_free = float(balance.get("USDT", {}).get("free", 0))
        logger.info(f"[清仓] 清仓后 USDT余额: {usdt_free:.2f}")

    # ── 3. 主循环 ──
    last_scan_time = 0

    while running:
        try:
            now = time.time()

            # ── 3a. 定时扫描（每 scan_interval 重新选币）──
            if now - last_scan_time > config.scan_interval_minutes * 60:
                logger.info("[Harness] ── 开始新一轮扫描 ──")
                risk_manager.print_status()

                cooling = risk_manager.get_cooling_symbols()
                candidates = scanner.scan(cooling_symbols=cooling)

                # 找出需要切换的币种
                new_symbols = {c["symbol"] for c in candidates}
                old_symbols = set(active_grids.keys())

                # 撤掉不再活跃的币种
                for sym in old_symbols - new_symbols:
                    logger.info(f"[Harness] {sym} 不再是活跃币种，撤单退出")
                    executor.cancel_all_orders(sym)
                    del active_grids[sym]

                # 为新币种建立网格
                for c in candidates:
                    sym = c["symbol"]

                    if not risk_manager.is_symbol_allowed(sym):
                        continue

                    total_grid_usdt = config.position_usdt * config.grid_levels
                    if not risk_manager.check_position_limits(sym, total_grid_usdt):
                        continue

                    if sym in active_grids:
                        continue

                    grid = grid_engine.build_grid(sym, c["price"])
                    if not grid:
                        continue

                    result = executor.place_grid_orders(grid)
                    if result["placed"] > 0:
                        active_grids[sym] = grid
                        mode = "卖出" if executor._get_holding(sym) > 0 else "买入"
                        logger.info(f"[Harness] {sym} 网格建立成功，{result['placed']}个挂单")
                        notifier.on_grid_created(sym, result["placed"], mode)

                last_scan_time = now

            # ── 3b. 总亏损保护 ──
            if risk_manager.check_drawdown_protection():
                logger.warning("[Harness] 总亏损保护触发，暂停所有交易")
                notifier._send("总亏损保护", "累计亏损超阈值，已暂停交易")
                for sym in list(active_grids.keys()):
                    executor.cancel_all_orders(sym)
                    executor.market_sell_all(sym)
                active_grids.clear()
                time.sleep(300)  # 暂停5分钟
                continue

            # ── 3c. 检查成交 & 止损 & 重平衡 ──
            for sym in list(active_grids.keys()):
                grid = active_grids[sym]

                # 检查移动止损
                if risk_manager.check_stop_loss(sym, grid["stop_loss_price"]):
                    notifier.on_stop_loss(sym, grid["stop_loss_price"], config.cooldown_hours)
                    if sym in active_grids:
                        del active_grids[sym]
                    continue

                # 检查网格重平衡
                if risk_manager.check_grid_rebalance(sym, grid):
                    logger.info(f"[Harness] {sym} 触发重平衡，重建网格")
                    executor.cancel_all_orders(sym)
                    try:
                        ticker = exchange.fetch_ticker(sym)
                        new_price = ticker.get("last", 0)
                        new_grid = grid_engine.build_grid(sym, new_price)
                        if new_grid:
                            result = executor.place_grid_orders(new_grid)
                            if result["placed"] > 0:
                                active_grids[sym] = new_grid
                                notifier._send("网格重平衡", f"{sym} 围绕 {new_price:.4f} 重建")
                    except Exception as e:
                        logger.error(f"[重平衡] {sym} 失败: {e}")
                    continue

                # 检查成交
                filled = executor.check_filled_orders(sym)
                for f in filled:
                    logger.info(
                        f"[成交] {f['side']} {sym} @ {f['price']:.4f} x {f['quantity']}"
                    )
                    executor.handle_fill(sym, f["side"], f["price"], f["quantity"], grid)
                    pnl = grid["grid_spacing"] * f["quantity"] if f["side"] == "SELL" else 0
                    notifier.on_order_filled(f["side"], sym, f["price"], f["quantity"], pnl)

            # ── 3c. 等待 ──
            time.sleep(config.price_check_seconds)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"[Harness] 主循环异常: {e}", exc_info=True)
            time.sleep(10)

    # ── 4. 优雅退出 ──
    logger.info("[Harness] 正在清理...")
    for sym in list(active_grids.keys()):
        logger.info(f"[退出] 撤销 {sym} 所有挂单")
        executor.cancel_all_orders(sym)

    risk_manager.print_status()
    notifier.on_shutdown(db.get_total_pnl())
    logger.info("[Harness] 已退出。挂单已全部撤销。")


def liquidate(exchange: ccxt.Exchange, executor: Executor, config: Config):
    """清仓流程: 撤销所有挂单 → 市价卖出所有持仓"""
    # 1. 撤销所有挂单
    symbols = config.forced_symbols if config.forced_symbols else []

    # 也检查交易所上的所有挂单
    try:
        all_open = exchange.fetch_open_orders()
        for o in all_open:
            sym = o.get("symbol", "")
            if sym not in symbols:
                symbols.append(sym)
    except ccxt.BaseError:
        pass

    for sym in symbols:
        logger.info(f"[清仓] 撤销 {sym} 所有挂单...")
        executor.cancel_all_orders(sym)

    time.sleep(1)

    # 2. 市价卖出所有非USDT持仓
    try:
        balance = exchange.fetch_balance()
        for asset, bal in balance.items():
            if asset in ("USDT", "info", "free", "used", "total", "timestamp", "datetime"):
                continue
            free = float(bal.get("free", 0)) if isinstance(bal, dict) else 0
            if free <= 0:
                continue

            symbol = "{0}/{1}".format(asset, config.quote_currency)
            # 确认交易对存在
            markets = exchange.load_markets()
            if symbol not in markets:
                continue

            prec = markets[symbol].get("precision", {}).get("amount", 8)
            if isinstance(prec, int):
                qty = round(free, prec)
            else:
                qty = free

            try:
                exchange.create_market_sell_order(symbol, qty)
                logger.info(f"[清仓] 市价卖出 {symbol} {qty}")
            except ccxt.BaseError as e:
                logger.warning(f"[清仓] 卖出 {symbol} 失败: {e}")
    except ccxt.BaseError as e:
        logger.error(f"[清仓] 查询余额失败: {e}")


if __name__ == "__main__":
    main()
