"""
交易执行器 — Executor Agent
负责在交易所上挂单、撤单、监听成交（ccxt统一接口）
"""

import logging
import ccxt
from config import Config
from state_db import StateDB

logger = logging.getLogger(__name__)


class Executor:
    def __init__(self, exchange: ccxt.Exchange, config: Config, db: StateDB):
        self.exchange = exchange
        self.config = config
        self.db = db

    def place_grid_orders(self, grid: dict) -> dict:
        """
        根据网格计算结果挂单
        自动检测持仓: 有持仓 → 先挂卖单，无持仓 → 先挂买单
        """
        symbol = grid["symbol"]
        placed = 0
        failed = 0
        orders = []

        # 检测当前持仓
        holding_qty = self._get_holding(symbol)

        if holding_qty > 0:
            # 有持仓模式: 用持仓挂卖单，卖出后自动挂买单
            logger.info(f"[执行] {symbol} 检测到持仓 {holding_qty}，使用卖出模式")
            qty_per_level = holding_qty / len(grid["sell_levels"]) if grid["sell_levels"] else 0
            prec = self._get_precision(symbol)
            qty_per_level = round(qty_per_level, prec["a"])

            for level in grid["sell_levels"]:
                order = self._place_limit_order(
                    symbol=symbol,
                    side="sell",
                    price=level["price"],
                    quantity=qty_per_level,
                    grid_index=level["index"],
                )
                if order:
                    placed += 1
                    orders.append(order)
                else:
                    failed += 1
        else:
            # 无持仓模式: 挂买单，买入后自动挂卖单
            for level in grid["buy_levels"]:
                order = self._place_limit_order(
                    symbol=symbol,
                    side="buy",
                    price=level["price"],
                    quantity=level["quantity"],
                    grid_index=level["index"],
                )
                if order:
                    placed += 1
                    orders.append(order)
                else:
                    failed += 1

        mode = "卖出" if holding_qty > 0 else "买入"
        logger.info(f"[执行] {symbol} {mode}模式挂单完成: 成功{placed} 失败{failed}")
        return {"placed": placed, "failed": failed, "orders": orders}

    def _get_holding(self, symbol: str) -> float:
        """查询某币种的可用持仓数量"""
        try:
            base = symbol.split("/")[0]
            balance = self.exchange.fetch_balance()
            free = float(balance.get(base, {}).get("free", 0))
            return free
        except ccxt.BaseError as e:
            logger.error(f"[持仓查询] {symbol} 失败: {e}")
            return 0

    def _place_limit_order(self, symbol: str, side: str, price: float,
                           quantity: float, grid_index: int):
        """挂一个限价单"""
        prec = self._get_precision(symbol)

        try:
            resp = self.exchange.create_limit_order(
                symbol=symbol,
                side=side,
                amount=quantity,
                price=price,
            )

            order_id = str(resp["id"])
            self.db.save_order(
                order_id=order_id,
                symbol=symbol,
                side=side.upper(),
                price=price,
                quantity=quantity,
                grid_index=grid_index,
            )

            logger.info(
                f"[下单] {side.upper()} {symbol} @ {price:.{prec['p']}f} "
                f"x {quantity:.{prec['a']}f} | ID: {order_id}"
            )
            return {"order_id": order_id, "side": side, "price": price, "quantity": quantity}

        except ccxt.BaseError as e:
            logger.error(f"[下单失败] {side} {symbol} @ {price}: {e}")
            return None

    def cancel_all_orders(self, symbol: str):
        """取消某个币种的所有挂单"""
        try:
            open_orders = self.exchange.fetch_open_orders(symbol=symbol)
            for o in open_orders:
                try:
                    self.exchange.cancel_order(o["id"], symbol=symbol)
                    self.db.update_order_status(str(o["id"]), "CANCELLED")
                    logger.info(f"[撤单] {symbol} orderId={o['id']}")
                except ccxt.BaseError as e:
                    logger.warning(f"[撤单失败] {symbol} orderId={o['id']}: {e}")
        except ccxt.BaseError as e:
            logger.error(f"[撤单] 获取挂单失败 {symbol}: {e}")

        self.db.clear_orders(symbol)

    def handle_fill(self, symbol: str, filled_side: str, filled_price: float,
                    filled_qty: float, grid: dict):
        """
        成交后自动在对面挂反向单
        买成交 → 挂卖（价格 = 成交价 + grid_spacing）
        卖成交 → 挂买（价格 = 成交价 - grid_spacing）
        """
        spacing = grid["grid_spacing"]
        prec = self._get_precision(symbol)

        if filled_side == "BUY":
            sell_price = round(filled_price + spacing, prec["p"])
            self._place_limit_order(
                symbol=symbol,
                side="sell",
                price=sell_price,
                quantity=filled_qty,
                grid_index=0,
            )
            self.db.log_trade(symbol, "BUY", filled_price, filled_qty,
                              filled_price * filled_qty)

        elif filled_side == "SELL":
            buy_price = round(filled_price - spacing, prec["p"])
            buy_qty = round(self.config.position_usdt / buy_price, prec["a"])

            self._place_limit_order(
                symbol=symbol,
                side="buy",
                price=buy_price,
                quantity=buy_qty,
                grid_index=0,
            )
            pnl = spacing * filled_qty
            self.db.log_trade(symbol, "SELL", filled_price, filled_qty,
                              filled_price * filled_qty, pnl)
            logger.info(f"[收益] {symbol} 本次 PnL: {pnl:.4f} USDT")

    def market_sell_all(self, symbol: str):
        """市价卖出所有持仓（止损用）"""
        try:
            balance = self.exchange.fetch_balance()
            base = symbol.split("/")[0]
            free = float(balance.get(base, {}).get("free", 0))

            if free > 0:
                prec = self._get_precision(symbol)
                try:
                    self.exchange.create_market_sell_order(symbol, round(free, prec["a"]))
                    logger.warning(f"[止损] 市价卖出 {symbol} {free:.{prec['a']}f}")
                except ccxt.BaseError as e:
                    logger.error(f"[止损卖出失败] {symbol}: {e}")
        except ccxt.BaseError as e:
            logger.error(f"[止损] 查询余额失败: {e}")

    def check_filled_orders(self, symbol: str) -> list:
        """检查是否有订单成交"""
        db_orders = self.db.get_active_orders(symbol)
        filled = []

        for o in db_orders:
            try:
                resp = self.exchange.fetch_order(o["order_id"], symbol=symbol)
                status = resp.get("status", "")

                if status == "closed":
                    self.db.update_order_status(o["order_id"], "FILLED")
                    filled.append({
                        "order_id": o["order_id"],
                        "side": o["side"],
                        "price": float(resp.get("average") or resp.get("price") or o["price"]),
                        "quantity": float(resp.get("filled") or o["quantity"]),
                    })
                elif status in ("canceled", "cancelled", "expired", "rejected"):
                    self.db.update_order_status(o["order_id"], "CANCELLED")
            except ccxt.BaseError:
                pass

        return filled

    def _get_precision(self, symbol: str) -> dict:
        """获取价格和数量精度"""
        markets = self.exchange.markets or self.exchange.load_markets()
        market = markets.get(symbol, {})
        p = market.get("precision", {})
        return {
            "p": p.get("price", 8) if isinstance(p.get("price"), int) else 8,
            "a": p.get("amount", 8) if isinstance(p.get("amount"), int) else 8,
        }
