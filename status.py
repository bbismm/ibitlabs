#!/usr/bin/env python3
"""
状态查看器 — 随时查看当前挂单、持仓、PnL
用法: python3 status.py
"""

import os
import sys
import ccxt

from config import Config
from state_db import StateDB


def main():
    config = Config()
    try:
        config.validate()
    except ValueError as e:
        print(e)
        sys.exit(1)

    exchange_class = getattr(ccxt, config.exchange_id)
    exchange = exchange_class({
        "apiKey": config.api_key,
        "secret": config.api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })

    db = StateDB(config.db_path)

    print("=" * 60)
    print("  Grid Trader 状态面板")
    print("=" * 60)

    # 余额
    print("\n── 账户余额 ──")
    balance = exchange.fetch_balance()
    for asset in ["USDT", "UNI", "BTC", "ETH", "SOL"]:
        bal = balance.get(asset, {})
        free = float(bal.get("free", 0)) if isinstance(bal, dict) else 0
        used = float(bal.get("used", 0)) if isinstance(bal, dict) else 0
        if free > 0 or used > 0:
            print(f"  {asset}: 可用 {free:.4f} | 冻结 {used:.4f} | 合计 {free + used:.4f}")

    # 当前价格
    print("\n── 当前价格 ──")
    symbols = config.forced_symbols if config.forced_symbols else db.get_active_symbols()
    for sym in symbols:
        try:
            ticker = exchange.fetch_ticker(sym)
            price = ticker.get("last", 0)
            change = ticker.get("percentage", 0)
            print(f"  {sym}: {price:.4f} ({change:+.2f}%)")
        except Exception:
            pass

    # 交易所挂单
    print("\n── 当前挂单 ──")
    total_orders = 0
    for sym in symbols:
        try:
            orders = exchange.fetch_open_orders(sym)
            if orders:
                for o in orders:
                    side = o.get("side", "").upper()
                    price = float(o.get("price", 0))
                    amount = float(o.get("amount", 0))
                    filled = float(o.get("filled", 0))
                    remaining = amount - filled
                    marker = "BUY " if side == "BUY" else "SELL"
                    print(f"  {marker} {sym} @ {price:.4f} x {remaining:.4f} (${price * remaining:.2f})")
                    total_orders += 1
        except Exception as e:
            print(f"  {sym}: 查询失败 - {e}")

    if total_orders == 0:
        print("  无挂单")
    else:
        print(f"  共 {total_orders} 个挂单")

    # 冷却状态
    cooling = db.get_all_cooling()
    if cooling:
        print("\n── 冷却中 ──")
        import time
        for c in cooling:
            remaining = (c["end_time"] - time.time()) / 3600
            print(f"  {c['symbol']}: 剩余 {remaining:.1f}h")

    # PnL
    total_pnl = db.get_total_pnl()
    print(f"\n── 累计 PnL: {total_pnl:.4f} USDT ──")
    print("=" * 60)


if __name__ == "__main__":
    main()
