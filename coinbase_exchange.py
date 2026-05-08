"""
Coinbase Advanced Trade Exchange Wrapper
Provides ccxt-compatible interface using official coinbase-advanced-py SDK.

Supports SOL PERP (SLP-20DEC30-CDE) futures trading.
"""

import logging
import time
import uuid
from coinbase.rest import RESTClient

logger = logging.getLogger(__name__)

# Granularity map: ccxt timeframe → Coinbase candle granularity
GRANULARITY_MAP = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR",
    "2h": "TWO_HOUR",
    "6h": "SIX_HOUR",
    "1d": "ONE_DAY",
}


class CoinbaseExchange:
    """
    ccxt-compatible wrapper around Coinbase Advanced Trade SDK.
    Drop-in replacement for ccxt.Exchange in the trading system.
    """

    def __init__(self, api_key: str, api_secret: str):
        self.client = RESTClient(api_key=api_key, api_secret=api_secret)
        self.markets = {}
        self.symbols = []
        self.id = "coinbase"

    def load_markets(self):
        """Load futures markets"""
        resp = self.client.get_products(product_type="FUTURE")
        products = resp["products"] if isinstance(resp, dict) else resp.products
        self.markets = {}
        for p in products:
            pid = p["product_id"] if isinstance(p, dict) else p.product_id
            price = p.get("price", "0") if isinstance(p, dict) else getattr(p, "price", "0")
            base_inc = p.get("base_increment", "1") if isinstance(p, dict) else getattr(p, "base_increment", "1")
            quote_inc = p.get("quote_increment", "0.01") if isinstance(p, dict) else getattr(p, "quote_increment", "0.01")

            # Get contract display name
            details = p.get("future_product_details", {}) if isinstance(p, dict) else getattr(p, "future_product_details", {})
            if not isinstance(details, dict):
                details = vars(details) if details else {}
            display = details.get("contract_display_name", pid)
            contract_size = float(details.get("contract_size", "1") or "1")

            self.markets[pid] = {
                "id": pid,
                "symbol": pid,
                "type": "future",
                "linear": True,
                "settle": "USD",
                "display_name": display,
                "contract_size": contract_size,
                "precision": {
                    "price": self._count_decimals(str(quote_inc)),
                    "amount": self._count_decimals(str(base_inc)),
                },
                "limits": {
                    "amount": {"min": float(base_inc) if base_inc else 1},
                },
            }
        self.symbols = list(self.markets.keys())
        logger.info(f"[EXCHANGE] Loaded {len(self.markets)} futures markets")
        return self.markets

    def fetch_ticker(self, symbol: str) -> dict:
        """Fetch current price for a symbol"""
        resp = self.client.get_product(symbol)
        p = resp if isinstance(resp, dict) else vars(resp)
        price = float(p.get("price", 0) or 0)
        bid = float(p.get("bid", 0) or p.get("price", 0) or 0)
        ask = float(p.get("ask", 0) or p.get("price", 0) or 0)
        # If bid/ask are 0, estimate from price
        if bid == 0:
            bid = price * 0.9999
        if ask == 0:
            ask = price * 1.0001
        return {
            "symbol": symbol,
            "last": price,
            "bid": bid,
            "ask": ask,
            "high": price,
            "low": price,
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 96, **kwargs) -> list:
        """Fetch OHLCV candles. Returns list of [timestamp, open, high, low, close, volume]"""
        granularity = GRANULARITY_MAP.get(timeframe, "FIFTEEN_MINUTE")
        end = int(time.time())
        # Calculate start based on timeframe and limit
        tf_seconds = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
                      "1h": 3600, "2h": 7200, "6h": 21600, "1d": 86400}
        interval = tf_seconds.get(timeframe, 900)
        start = end - (interval * limit)

        resp = self.client.get_candles(symbol, str(start), str(end), granularity)
        candles_raw = resp if isinstance(resp, dict) else vars(resp)
        candle_list = candles_raw.get("candles", [])

        result = []
        for c in candle_list:
            if isinstance(c, dict):
                ts = int(c.get("start", 0)) * 1000
                o = float(c.get("open", 0))
                h = float(c.get("high", 0))
                l = float(c.get("low", 0))
                cl = float(c.get("close", 0))
                v = float(c.get("volume", 0))
            else:
                ts = int(getattr(c, "start", 0)) * 1000
                o = float(getattr(c, "open", 0))
                h = float(getattr(c, "high", 0))
                l = float(getattr(c, "low", 0))
                cl = float(getattr(c, "close", 0))
                v = float(getattr(c, "volume", 0))
            result.append([ts, o, h, l, cl, v])

        # Coinbase returns newest first — reverse to oldest first (ccxt standard)
        result.reverse()
        return result

    def fetch_balance(self) -> dict:
        """Fetch futures balance"""
        resp = self.client.get_futures_balance_summary()
        summary = resp if isinstance(resp, dict) else vars(resp)
        bs = summary.get("balance_summary", summary)
        if not isinstance(bs, dict):
            bs = vars(bs)

        buying_power = self._extract_value(bs.get("futures_buying_power", {}))
        total_usd = self._extract_value(bs.get("total_usd_balance", {}))
        unrealized = self._extract_value(bs.get("unrealized_pnl", {}))
        available = self._extract_value(bs.get("available_margin", {}))

        return {
            "free": {"USD": buying_power},
            "total": {"USD": total_usd or buying_power},
            "info": {
                "buying_power": buying_power,
                "unrealized_pnl": unrealized,
                "available_margin": available,
            },
        }

    def fetch_positions(self) -> list:
        """Fetch all open futures positions from Coinbase"""
        try:
            resp = self.client.list_futures_positions()
            raw = resp if isinstance(resp, dict) else vars(resp)
            positions = raw.get("positions", [])
            result = []
            for p in positions:
                if isinstance(p, str):
                    import ast
                    p = ast.literal_eval(p)
                elif not isinstance(p, dict):
                    try:
                        p = {k: p[k] for k in ("product_id", "side", "number_of_contracts",
                             "avg_entry_price", "current_price", "unrealized_pnl")}
                    except Exception:
                        p = vars(p) if hasattr(p, '__dict__') else {}
                contracts = int(p.get("number_of_contracts", 0) or 0)
                if contracts == 0:
                    continue
                symbol = p.get("product_id", "") or p.get("symbol", "")
                result.append({
                    "symbol": symbol,
                    "side": (p.get("side", "") or "").lower(),
                    "contracts": contracts,
                    "entry_price": float(p.get("avg_entry_price", 0) or 0),
                    "current_price": float(p.get("current_price", 0) or 0),
                    "unrealized_pnl": float(p.get("unrealized_pnl", 0) or 0),
                })
            return result
        except Exception as e:
            logger.warning(f"[EXCHANGE] fetch_positions failed: {e}")
            return []

    def create_limit_order(self, symbol: str, side: str, amount: float, price: float) -> dict:
        """Place a limit order"""
        client_oid = str(uuid.uuid4())
        order_side = "BUY" if side.lower() == "buy" else "SELL"

        resp = self.client.create_order(
            client_order_id=client_oid,
            product_id=symbol,
            side=order_side,
            order_configuration={
                "limit_limit_gtc": {
                    "base_size": str(int(amount)),
                    "limit_price": str(round(price, 2)),
                }
            },
        )
        return self._parse_order_response(resp, price)

    def create_market_order(self, symbol: str, side: str, amount: float) -> dict:
        """Place a market order"""
        client_oid = str(uuid.uuid4())
        order_side = "BUY" if side.lower() == "buy" else "SELL"

        resp = self.client.create_order(
            client_order_id=client_oid,
            product_id=symbol,
            side=order_side,
            order_configuration={
                "market_market_ioc": {
                    "base_size": str(int(amount)),
                }
            },
        )
        return self._parse_order_response(resp, 0)

    def close_perp_position(self, symbol: str, size: float = None,
                            direction: str = None) -> dict:
        """Close an open perp position by placing the opposing market order
        with `reduce_only=True`.

        Originally implemented (α fix, 2026-04-20) using the SDK's
        /orders/close_position endpoint. That endpoint started returning
        `404 NOT_FOUND "no positions found for product ..."` on 2026-04-29
        even when `get_futures_position` clearly returned the open position
        (verified across multiple fresh sessions). The bot entered a
        retry loop trying to close at trailing-stop fire, broadcasting
        false "close sent" notifications without ever placing an order.
        Manual close via market_order_buy worked instantly.

        See `SKILL_REFERENCE.md` §R8 for the broader incident pattern.

        Why `reduce_only=True` instead of just market_order_buy/sell:
        the original 2026-04-19 #325 ghost-position bug came from a plain
        market order that got treated as a NEW position instead of a
        close. `reduce_only` flag tells Coinbase "this order can only
        REDUCE my position, never open a new one in the opposite
        direction." That guarantees no ghost.

        Args:
            symbol: product_id (e.g. "SLP-20DEC30-CDE")
            size: contracts to close. Required (no auto-full-close fallback
                  since we're not using the dedicated endpoint anymore).
            direction: "long" or "short". If omitted, fetched from
                  get_futures_position (with the caveat that endpoint can
                  also lag — caller passing direction is preferred).

        Returns:
            Dict via _parse_order_response: id, symbol, side, price,
            average. Caller follows up with get_order_fill_price().
        """
        if size is None:
            raise ValueError("close_perp_position: size is required (no full-close fallback)")

        if direction is None:
            try:
                resp_pos = self.client.get_futures_position(product_id=symbol)
                pos = resp_pos if isinstance(resp_pos, dict) else vars(resp_pos)
                pos = pos.get("position") if isinstance(pos, dict) else pos
                if isinstance(pos, str):
                    import ast
                    try:
                        pos = ast.literal_eval(pos)
                    except Exception:
                        pos = {}
                if isinstance(pos, dict):
                    side = (pos.get("side") or "").upper()
                    direction = "long" if side == "LONG" else ("short" if side == "SHORT" else None)
            except Exception as e:
                logger.warning(f"[EXCHANGE] close_perp_position: get_futures_position failed: {e}")

        if direction not in ("long", "short"):
            raise ValueError(f"close_perp_position: cannot determine direction (got {direction!r})")

        close_side_method = self.client.market_order_buy if direction == "short" else self.client.market_order_sell

        client_oid = f"close-{uuid.uuid4().hex[:16]}"
        # α2 fix (2026-04-30 01:35 incident): the α1 patch passed
        # `reduce_only=True` to the SDK's market_order_buy/sell wrappers,
        # but those wrappers do NOT accept that kwarg — the protobuf
        # serializer rejects it as `unknown field "reduce_only"` (HTTP
        # 400). The flag exists at the API level but the SDK only exposes
        # it via lower-level create_order with hand-built order_configuration.
        # Risk accepted: without reduce_only, a market order on a perp can
        # in principle be treated as a NEW position rather than a close
        # (root of trade #325 / 2026-04-19 ghost). Mitigation: caller
        # passes `direction` from bot's own state (`self.position["direction"]`,
        # not from API), and only invokes close_perp_position when
        # has_position() is True. The 2026-04-29 14:17 manual recovery
        # used this exact call shape (no reduce_only) and closed cleanly.
        resp = close_side_method(
            client_order_id=client_oid,
            product_id=symbol,
            base_size=str(int(size)),
        )
        return self._parse_order_response(resp, 0)

    def fetch_open_orders(self, symbol: str = None) -> list:
        """Fetch all open orders, optionally filtered by symbol"""
        resp = self.client.list_orders(order_status=["OPEN"])
        orders_raw = resp.get("orders", []) if isinstance(resp, dict) else getattr(resp, "orders", [])
        orders = []
        for o in orders_raw:
            o = o if isinstance(o, dict) else vars(o)
            pid = o.get("product_id", "")
            if symbol and pid != symbol:
                continue
            orders.append({
                "id": o.get("order_id", ""),
                "symbol": pid,
                "side": o.get("side", ""),
                "price": float(o.get("average_filled_price", 0) or o.get("price", 0) or 0),
            })
        return orders

    def get_order_fill_price(self, order_id: str, timeout: int = 10):
        """Query order details to get actual average_filled_price after fill."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = self.client.get_order(order_id)
                o = resp if isinstance(resp, dict) else vars(resp)
                order = o.get("order", o)
                if not isinstance(order, dict):
                    order = vars(order) if order else {}
                status = (order.get("status", "") or "").upper()
                avg = order.get("average_filled_price", None)
                if avg and float(avg) > 0:
                    logger.info(f"[EXCHANGE] Order {order_id} fill price: {avg}")
                    return float(avg)
                if status in ("FILLED", "CANCELLED", "EXPIRED", "FAILED"):
                    break
                time.sleep(1)
            except Exception as e:
                logger.warning(f"[EXCHANGE] get_order_fill_price failed: {e}")
                break
        return None

    def cancel_orders(self, order_ids: list) -> dict:
        """Cancel orders by ID"""
        return self.client.cancel_orders(order_ids)

    def list_fills(self, product_id: str = None, start_ts: float = None,
                   end_ts: float = None, limit: int = 250) -> list:
        """
        List historical fills from Coinbase. Used for DB↔exchange reconciliation.

        start_ts/end_ts are Unix seconds. Returns a list of dict with canonical
        fields:
            {fill_id, order_id, ts, side, price, quantity, product_id, fee}
        """
        from datetime import datetime, timezone
        base_kwargs = {"limit": limit}
        if product_id:
            # SDK takes product_ids (plural list)
            base_kwargs["product_ids"] = [product_id]
        if start_ts:
            base_kwargs["start_sequence_timestamp"] = datetime.fromtimestamp(
                start_ts, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_ts:
            base_kwargs["end_sequence_timestamp"] = datetime.fromtimestamp(
                end_ts, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

        out = []
        cursor = None
        pages = 0
        while True:
            kwargs = dict(base_kwargs)
            if cursor:
                kwargs["cursor"] = cursor
            try:
                resp = self.client.get_fills(**kwargs)
                raw = resp if isinstance(resp, dict) else vars(resp)
                fills = raw.get("fills", []) or []
                cursor = raw.get("cursor") or None
            except Exception as e:
                logger.warning(f"[EXCHANGE] get_fills failed: {e}")
                break
            for f in fills:
                if not isinstance(f, dict):
                    f = vars(f) if hasattr(f, "__dict__") else {}
                t_str = f.get("trade_time") or f.get("sequence_timestamp") or ""
                ts_epoch = 0.0
                if t_str:
                    try:
                        t_str_norm = t_str.replace("Z", "+00:00")
                        ts_epoch = datetime.fromisoformat(t_str_norm).timestamp()
                    except Exception:
                        pass
                out.append({
                    "fill_id": f.get("entry_id", "") or f.get("trade_id", ""),
                    "order_id": f.get("order_id", ""),
                    "ts": ts_epoch,
                    "side": (f.get("side", "") or "").upper(),
                    "price": float(f.get("price", 0) or 0),
                    "quantity": float(f.get("size", 0) or 0),
                    "product_id": f.get("product_id", ""),
                    "fee": float(f.get("commission", 0) or 0),
                })
            pages += 1
            if not cursor or not fills or pages >= 20:  # safety cap
                break
        return out

    def market(self, symbol: str) -> dict:
        """Get market info for symbol"""
        return self.markets.get(symbol, {})

    # ── Helpers ──

    def _parse_order_response(self, resp, fallback_price: float) -> dict:
        """Parse order creation response into ccxt-compatible format"""
        if isinstance(resp, dict):
            data = resp
        else:
            data = vars(resp)

        success = data.get("success", False)
        if not success:
            error = data.get("error_response", {})
            if not isinstance(error, dict):
                error = vars(error) if error else {}
            msg = error.get("message", "") or error.get("error", "") or str(error)
            preview = error.get("preview_failure_reason", "") or data.get("order_error", "")
            raise Exception(f"Order failed: {msg} | {preview}" if preview else f"Order failed: {msg}")

        sr = data.get("success_response", {})
        if not isinstance(sr, dict):
            sr = vars(sr) if sr else {}

        return {
            "id": sr.get("order_id", ""),
            "symbol": sr.get("product_id", ""),
            "side": sr.get("side", ""),
            "price": fallback_price,
            "average": None,
        }

    def _extract_value(self, field) -> float:
        """Extract numeric value from Coinbase balance field"""
        if isinstance(field, dict):
            return float(field.get("value", 0) or 0)
        if hasattr(field, "value"):
            return float(field.value or 0)
        return float(field or 0)

    def _count_decimals(self, s: str) -> int:
        """Count decimal places in a string number"""
        if "." in s:
            return len(s.split(".")[-1].rstrip("0")) or 0
        return 0
