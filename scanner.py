"""
活跃币种扫描器 — Scanner Agent
1. 按24h成交量筛选活跃币种
2. 通过信号过滤器(RSI+EMA+成交量+多时间框架)确认入场
只有通过信号确认的币种才允许建网格
"""

import logging
import ccxt
from config import Config
from signals import SignalFilter

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(self, exchange: ccxt.Exchange, config: Config):
        self.exchange = exchange
        self.config = config
        self.signal_filter = SignalFilter(exchange, config)

    def scan(self, cooling_symbols: set = None) -> list:
        """
        扫描最活跃币种 + 信号确认
        返回: 通过信号确认的币种列表（按信号强度排序）
        """
        cooling_symbols = cooling_symbols or set()

        # 如果指定了币种，直接使用（跳过扫描）
        if self.config.forced_symbols:
            candidates = []
            for symbol in self.config.forced_symbols:
                if symbol in cooling_symbols:
                    continue
                try:
                    ticker = self.exchange.fetch_ticker(symbol)
                    candidates.append({
                        "symbol": symbol,
                        "price": ticker.get("last", 0),
                        "volume_usdt": ticker.get("quoteVolume", 0),
                        "change_pct": ticker.get("percentage", 0),
                        "signal_score": 100,
                        "signal_reasons": ["指定币种"],
                    })
                    logger.info(f"[扫描] 指定币种 {symbol} | 价格: {ticker.get('last', 0):.4f}")
                except ccxt.BaseError as e:
                    logger.error(f"[扫描] 获取 {symbol} 行情失败: {e}")
            return candidates

        tickers = self.exchange.fetch_tickers()

        # 第一步: 按成交量筛选候选币种
        candidates = []
        for symbol, t in tickers.items():
            if not symbol.endswith("/{0}".format(self.config.quote_currency)):
                continue

            base = symbol.split("/")[0]
            if base in self.config.excluded_bases:
                continue

            if symbol in cooling_symbols:
                continue

            volume_usdt = t.get("quoteVolume") or 0
            if volume_usdt < self.config.min_volume_usdt:
                continue

            price = t.get("last") or t.get("close") or 0
            if price <= 0:
                continue

            change_pct = t.get("percentage") or 0

            candidates.append({
                "symbol": symbol,
                "price": price,
                "volume_usdt": volume_usdt,
                "change_pct": change_pct,
            })

        # 按成交额排序，取前10名做信号分析（避免API调用过多）
        candidates.sort(key=lambda x: x["volume_usdt"], reverse=True)
        top_by_volume = candidates[:10]

        logger.info(f"[扫描] 成交量筛选出 {len(top_by_volume)} 个候选币种，开始信号确认...")

        # 第二步: 信号过滤 — 只有确认的才能建网格
        confirmed = self.signal_filter.rank_by_signal(top_by_volume)

        if confirmed:
            logger.info(f"[扫描] {len(confirmed)} 个币种通过信号确认:")
            for c in confirmed:
                logger.info(
                    f"  {c['symbol']} | "
                    f"价格: {c['price']:.4f} | "
                    f"24h量: {c['volume_usdt']/1e6:.1f}M | "
                    f"信号分: {c['signal_score']}/100 | "
                    f"{', '.join(c['signal_reasons'])}"
                )
        else:
            logger.info("[扫描] 无币种通过信号确认，等待下一轮扫描")

        return confirmed
