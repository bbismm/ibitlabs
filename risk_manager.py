"""
风控模块 V2 — Risk Manager Agent
1. 移动止损 — 价格上涨时止损跟着上移，锁住利润
2. 总亏损保护 — 累计亏损超阈值暂停交易
3. 网格重平衡 — 价格偏离中心过远时重建网格
4. 胜率统计 — 实时追踪表现
"""

import logging
import time
import ccxt
from config import Config
from state_db import StateDB
from executor import Executor

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, exchange: ccxt.Exchange, config: Config, db: StateDB, executor: Executor):
        self.exchange = exchange
        self.config = config
        self.db = db
        self.executor = executor
        # 移动止损: symbol → 当前止损价
        self._trailing_stops = {}
        # 最高价追踪: symbol → 建网格以来的最高价
        self._highest_prices = {}

    def check_stop_loss(self, symbol: str, initial_stop: float) -> bool:
        """
        V2 移动止损
        - 初始止损 = 网格最低价 - ATR * 系数
        - 价格每上涨1个ATR，止损上移0.5个ATR
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker.get("last", 0)
        except ccxt.BaseError as e:
            logger.error(f"[风控] 获取 {symbol} 价格失败: {e}")
            return False

        # 初始化追踪
        if symbol not in self._trailing_stops:
            self._trailing_stops[symbol] = initial_stop
            self._highest_prices[symbol] = current_price

        # 更新最高价
        if current_price > self._highest_prices[symbol]:
            old_high = self._highest_prices[symbol]
            self._highest_prices[symbol] = current_price

            # 价格上涨时，止损跟着上移（上移幅度 = 价格涨幅的50%）
            price_gain = current_price - old_high
            new_stop = self._trailing_stops[symbol] + price_gain * 0.5
            if new_stop > self._trailing_stops[symbol]:
                old_stop = self._trailing_stops[symbol]
                self._trailing_stops[symbol] = new_stop
                logger.info(
                    f"[移动止损] {symbol} 最高价 {current_price:.4f} | "
                    f"止损上移 {old_stop:.4f} → {new_stop:.4f}"
                )

        # 检查是否触及止损
        current_stop = self._trailing_stops[symbol]
        if current_price <= current_stop:
            logger.warning(
                f"[止损触发] {symbol} 当前价 {current_price:.4f} <= "
                f"移动止损 {current_stop:.4f}"
            )
            self._execute_stop_loss(symbol)
            # 清理追踪数据
            self._trailing_stops.pop(symbol, None)
            self._highest_prices.pop(symbol, None)
            return True

        return False

    def check_drawdown_protection(self) -> bool:
        """
        总亏损保护
        累计亏损超过 max_total_position 的 20% 时暂停所有交易
        返回 True = 需要暂停
        """
        total_pnl = self.db.get_total_pnl()
        max_drawdown = self.config.max_total_position * -0.20  # -20%

        if total_pnl < max_drawdown:
            logger.warning(
                f"[风控] 总亏损保护触发！累计 PnL: {total_pnl:.4f} USDT < "
                f"阈值 {max_drawdown:.4f} USDT"
            )
            return True
        return False

    def check_grid_rebalance(self, symbol: str, grid: dict) -> bool:
        """
        网格重平衡检测
        价格偏离中心超过网格范围的 80% 时需要重建
        返回 True = 需要重建网格
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker.get("last", 0)
        except ccxt.BaseError:
            return False

        center = grid["center_price"]
        total_range = grid["grid_spacing"] * self.config.grid_levels
        deviation = abs(current_price - center)
        deviation_pct = deviation / total_range if total_range > 0 else 0

        if deviation_pct > 0.8:
            logger.info(
                f"[重平衡] {symbol} 价格偏离中心 {deviation_pct:.0%} | "
                f"中心: {center:.4f} | 当前: {current_price:.4f} → 需要重建网格"
            )
            return True
        return False

    def _execute_stop_loss(self, symbol: str):
        """执行止损流程: 撤单 → 市价平仓 → 进入冷却"""
        logger.warning(f"[止损] {symbol} 开始执行止损流程...")
        self.executor.cancel_all_orders(symbol)
        self.executor.market_sell_all(symbol)
        self.db.set_cooldown(
            symbol=symbol,
            duration_hours=self.config.cooldown_hours,
            reason=f"stop_loss_at_{time.strftime('%Y%m%d_%H%M%S')}"
        )
        resume_time = time.strftime(
            '%Y-%m-%d %H:%M:%S',
            time.localtime(time.time() + self.config.cooldown_hours * 3600)
        )
        logger.warning(
            f"[止损] {symbol} 止损完成，进入 {self.config.cooldown_hours}h 冷却期，"
            f"预计恢复: {resume_time}"
        )

    def is_symbol_allowed(self, symbol: str) -> bool:
        if self.db.is_cooling(symbol):
            cooling = self.db.get_all_cooling()
            for c in cooling:
                if c["symbol"] == symbol:
                    remaining = (c["end_time"] - time.time()) / 3600
                    logger.info(f"[风控] {symbol} 仍在冷却中，剩余 {remaining:.1f}h")
                    break
            return False
        return True

    def check_position_limits(self, symbol: str, new_position_usdt: float) -> bool:
        active_orders = self.db.get_active_orders(symbol)
        current_position = sum(
            o["price"] * o["quantity"] for o in active_orders if o["side"] == "BUY"
        )
        if current_position + new_position_usdt > self.config.max_position_per_symbol:
            logger.warning(
                f"[风控] {symbol} 超出单币种仓位限制: "
                f"{current_position + new_position_usdt:.2f} > {self.config.max_position_per_symbol}"
            )
            return False

        all_orders = self.db.get_active_orders()
        total_position = sum(
            o["price"] * o["quantity"] for o in all_orders if o["side"] == "BUY"
        )
        if total_position + new_position_usdt > self.config.max_total_position:
            logger.warning(
                f"[风控] 总仓位超限: "
                f"{total_position + new_position_usdt:.2f} > {self.config.max_total_position}"
            )
            return False
        return True

    def get_cooling_symbols(self) -> set:
        cooling = self.db.get_all_cooling()
        return {c["symbol"] for c in cooling}

    def get_performance(self) -> dict:
        """胜率和收益统计"""
        try:
            conn = self.db._connect()
            # 总交易次数
            total = conn.execute("SELECT COUNT(*) as c FROM trade_log").fetchone()["c"]
            # 盈利次数
            wins = conn.execute("SELECT COUNT(*) as c FROM trade_log WHERE pnl > 0").fetchone()["c"]
            # 总PnL
            total_pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) as s FROM trade_log").fetchone()["s"]
            # 平均每笔收益
            avg_pnl = conn.execute("SELECT COALESCE(AVG(pnl), 0) as a FROM trade_log WHERE pnl != 0").fetchone()["a"]
            # 最大单笔亏损
            max_loss = conn.execute("SELECT COALESCE(MIN(pnl), 0) as m FROM trade_log").fetchone()["m"]
            # 最大单笔盈利
            max_win = conn.execute("SELECT COALESCE(MAX(pnl), 0) as m FROM trade_log").fetchone()["m"]
            conn.close()

            win_rate = (wins / total * 100) if total > 0 else 0

            return {
                "total_trades": total,
                "wins": wins,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "max_win": max_win,
                "max_loss": max_loss,
            }
        except Exception:
            return {"total_trades": 0, "wins": 0, "win_rate": 0, "total_pnl": 0,
                    "avg_pnl": 0, "max_win": 0, "max_loss": 0}

    def print_status(self):
        cooling = self.db.get_all_cooling()
        perf = self.get_performance()

        logger.info("=" * 60)
        logger.info(f"[风控状态] 累计 PnL: {perf['total_pnl']:.4f} USDT")
        logger.info(
            f"  交易: {perf['total_trades']}笔 | "
            f"胜率: {perf['win_rate']:.1f}% | "
            f"均盈: {perf['avg_pnl']:.4f}"
        )
        if perf['total_trades'] > 0:
            logger.info(
                f"  最大盈: {perf['max_win']:.4f} | "
                f"最大亏: {perf['max_loss']:.4f}"
            )

        if cooling:
            for c in cooling:
                remaining = (c["end_time"] - time.time()) / 3600
                logger.info(f"  冷却中: {c['symbol']} 剩余 {remaining:.1f}h")
        else:
            logger.info("  无冷却币种")

        # 移动止损状态
        for sym, stop in self._trailing_stops.items():
            high = self._highest_prices.get(sym, 0)
            logger.info(f"  {sym} 移动止损: {stop:.4f} | 最高价: {high:.4f}")

        active = self.db.get_active_symbols()
        logger.info(f"  活跃交易: {', '.join(active) if active else '无'}")
        logger.info("=" * 60)
