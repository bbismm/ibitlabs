"""
Whale Flow Agent — Order book wall detection + wall-bounded grid range.
Scans for large resting orders to find support/resistance, then defines
the optimal grid range between the two strongest walls.
TTL: 30s
"""

import logging
import sys
sys.path.insert(0, "..")
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class WhaleFlowAgent(BaseAgent):
    def __init__(self, exchange):
        super().__init__("WhaleAgent", ttl_seconds=15)  # Check walls more frequently
        self.exchange = exchange
        self.prev_buy_wall = None   # Track previous walls
        self.prev_sell_wall = None
        self.wall_stable_count = 0  # How many consecutive checks walls stayed

    def fetch(self) -> dict:
        data = {
            "whale_bias": "neutral",
            "large_buys": 0,
            "large_sells": 0,
            "large_buy_volume": 0,
            "large_sell_volume": 0,
            "buy_wall": None,
            "sell_wall": None,
            "support_level": 0,
            "resistance_level": 0,
            # Wall-bounded grid
            "wall_range_valid": False,
            "wall_low": 0,
            "wall_high": 0,
            "wall_range_pct": 0,
            "wall_buy_strength": 0,   # USD value of buy wall
            "wall_sell_strength": 0,  # USD value of sell wall
            "all_buy_walls": [],
            "all_sell_walls": [],
        }

        current_price = 0
        try:
            ticker = self.exchange.fetch_ticker("SOL/USDC")
            current_price = ticker.get("last", 0) or 0
        except Exception:
            return data

        # Recent trades — whale bias
        try:
            trades = self.exchange.fetch_trades("SOL/USDC", limit=100)
            large_threshold = 500

            for t in trades:
                value = (t.get("price", 0) or 0) * (t.get("amount", 0) or 0)
                if value >= large_threshold:
                    side = t.get("side", "")
                    if side == "buy":
                        data["large_buys"] += 1
                        data["large_buy_volume"] += value
                    elif side == "sell":
                        data["large_sells"] += 1
                        data["large_sell_volume"] += value

            if data["large_buy_volume"] > data["large_sell_volume"] * 1.5:
                data["whale_bias"] = "buy_heavy"
            elif data["large_sell_volume"] > data["large_buy_volume"] * 1.5:
                data["whale_bias"] = "sell_heavy"
        except Exception as e:
            logger.warning(f"[Whale] Trade fetch failed: {e}")

        # Deep order book scan — find ALL walls within 3%
        try:
            ob = self.exchange.fetch_order_book("SOL/USDC", limit=100)

            # Buy walls (support)
            if ob["bids"]:
                avg_bid = sum(b[1] for b in ob["bids"][:30]) / 30
                for price, size in ob["bids"]:
                    dist_pct = (current_price - price) / current_price * 100
                    if dist_pct > 3:
                        break
                    if size > avg_bid * 2.5:
                        usd_val = price * size
                        wall = {"price": round(price, 2), "size": round(size, 1), "usd": round(usd_val)}
                        data["all_buy_walls"].append(wall)

                # Strongest buy wall = largest USD value
                if data["all_buy_walls"]:
                    strongest = max(data["all_buy_walls"], key=lambda w: w["usd"])
                    data["buy_wall"] = {"price": strongest["price"], "size": strongest["size"]}
                    data["support_level"] = strongest["price"]
                    data["wall_buy_strength"] = strongest["usd"]

            # Sell walls (resistance)
            if ob["asks"]:
                avg_ask = sum(a[1] for a in ob["asks"][:30]) / 30
                for price, size in ob["asks"]:
                    dist_pct = (price - current_price) / current_price * 100
                    if dist_pct > 3:
                        break
                    if size > avg_ask * 2.5:
                        usd_val = price * size
                        wall = {"price": round(price, 2), "size": round(size, 1), "usd": round(usd_val)}
                        data["all_sell_walls"].append(wall)

                if data["all_sell_walls"]:
                    strongest = max(data["all_sell_walls"], key=lambda w: w["usd"])
                    data["sell_wall"] = {"price": strongest["price"], "size": strongest["size"]}
                    data["resistance_level"] = strongest["price"]
                    data["wall_sell_strength"] = strongest["usd"]

            # Wall-bounded range: valid if both walls exist and range > 0.3%
            if data["support_level"] > 0 and data["resistance_level"] > 0:
                low = data["support_level"]
                high = data["resistance_level"]
                range_pct = (high - low) / current_price * 100
                if range_pct > 0.3:
                    data["wall_range_valid"] = True
                    data["wall_low"] = low
                    data["wall_high"] = high
                    data["wall_range_pct"] = round(range_pct, 2)
                    logger.info(
                        f"[Whale] Wall range: ${low:.2f} - ${high:.2f} "
                        f"({range_pct:.2f}%) | "
                        f"Buy wall ${data['wall_buy_strength']:,} | "
                        f"Sell wall ${data['wall_sell_strength']:,}"
                    )

        except Exception as e:
            logger.warning(f"[Whale] Order book failed: {e}")

        # Wall stability tracking
        cur_buy = data["support_level"]
        cur_sell = data["resistance_level"]

        data["wall_disappeared"] = None
        data["wall_eaten"] = False     # Wall consumed by market orders = strong directional signal
        data["wall_pulled"] = False    # Wall withdrawn = possible spoofing
        data["wall_stable"] = False

        if self.prev_buy_wall and cur_buy == 0:
            # Buy wall gone — was it eaten or pulled?
            if current_price < self.prev_buy_wall:
                # Price broke BELOW the wall → wall was eaten by sellers = bearish
                data["wall_disappeared"] = "buy_eaten"
                data["wall_eaten"] = True
                logger.warning(f"[Whale] BUY WALL EATEN @${self.prev_buy_wall:.2f} — strong sell pressure!")
            else:
                # Price still above wall → wall was pulled = possible spoofing
                data["wall_disappeared"] = "buy_pulled"
                data["wall_pulled"] = True
                logger.info(f"[Whale] Buy wall pulled @${self.prev_buy_wall:.2f} — possible spoof")
            self.wall_stable_count = 0
        elif self.prev_sell_wall and cur_sell == 0:
            if current_price > self.prev_sell_wall:
                # Price broke ABOVE the wall → wall was eaten by buyers = bullish
                data["wall_disappeared"] = "sell_eaten"
                data["wall_eaten"] = True
                logger.warning(f"[Whale] SELL WALL EATEN @${self.prev_sell_wall:.2f} — strong buy pressure!")
            else:
                data["wall_disappeared"] = "sell_pulled"
                data["wall_pulled"] = True
                logger.info(f"[Whale] Sell wall pulled @${self.prev_sell_wall:.2f} — possible spoof")
            self.wall_stable_count = 0
        elif self.prev_buy_wall and cur_buy > 0 and abs(cur_buy - self.prev_buy_wall) / self.prev_buy_wall > 0.005:
            data["wall_disappeared"] = "buy_moved"
            logger.info(f"[Whale] Buy wall moved: ${self.prev_buy_wall:.2f} -> ${cur_buy:.2f}")
            self.wall_stable_count = 0
        elif self.prev_sell_wall and cur_sell > 0 and abs(cur_sell - self.prev_sell_wall) / self.prev_sell_wall > 0.005:
            data["wall_disappeared"] = "sell_moved"
            logger.info(f"[Whale] Sell wall moved: ${self.prev_sell_wall:.2f} -> ${cur_sell:.2f}")
            self.wall_stable_count = 0
        else:
            self.wall_stable_count += 1

        # Wall is "stable" if it stayed for 4+ checks (1 minute at 15s TTL)
        data["wall_stable"] = self.wall_stable_count >= 4
        data["wall_stable_count"] = self.wall_stable_count

        self.prev_buy_wall = cur_buy if cur_buy > 0 else None
        self.prev_sell_wall = cur_sell if cur_sell > 0 else None

        return data
