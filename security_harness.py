#!/usr/bin/env python3
"""
Security Team — System health + Trading safety monitoring.
Runs every 30s, writes security_state.json, sends iMessage on alerts.

Usage:
  export CB_API_KEY='...'
  export CB_API_SECRET='...'
  python3 security_harness.py
"""

import json
import os
import time
import logging
import signal as sig

import ccxt

from security import HealthAgent, TradingSafetyAgent
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("security.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

running = True
STATE_FILE = os.path.join(os.path.dirname(__file__), "security_state.json")


def signal_handler(s, frame):
    global running
    running = False


sig.signal(sig.SIGINT, signal_handler)
sig.signal(sig.SIGTERM, signal_handler)


def main():
    exchange = ccxt.coinbase({"enableRateLimit": True})
    exchange.load_markets()

    # Authenticated exchange for balance/position checks
    auth_exchange = None
    if os.environ.get("CB_API_KEY"):
        auth_exchange = ccxt.coinbaseadvanced({
            "apiKey": os.environ.get("CB_API_KEY", ""),
            "secret": os.environ.get("CB_API_SECRET", ""),
            "enableRateLimit": True,
        })
        auth_exchange.load_markets()

    health = HealthAgent(exchange)
    safety = TradingSafetyAgent(auth_exchange) if auth_exchange else None
    notifier = Notifier()

    logger.info("=" * 60)
    logger.info("  Security Team — System Monitor")
    logger.info("  Agents: Health, Trading Safety")
    logger.info(f"  Output: {STATE_FILE}")
    logger.info("  Refresh: 30s")
    logger.info("=" * 60)

    # Track alert cooldown to avoid spam
    last_alert_time = {}

    cycle = 0
    while running:
        try:
            cycle += 1
            health_data = health.get()
            safety_data = safety.get() if safety else {
                "status": "N/A", "alerts": [], "issues": [],
                "current_balance": 0, "position_count": 0, "order_count": 0,
            }

            all_alerts = health_data.get("issues", []) + safety_data.get("alerts", [])
            all_actions = health_data.get("actions_taken", [])

            state = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "ALL CLEAR" if not all_alerts else "ALERT",
                "health": {
                    "scalper": health_data.get("scalper_alive", False),
                    "monitor": health_data.get("monitor_alive", False),
                    "dashboard": health_data.get("dashboard_alive", False),
                    "api_connected": health_data.get("api_connected", False),
                    "api_latency_ms": health_data.get("api_latency_ms", 0),
                },
                "trading": {
                    "balance": safety_data.get("current_balance", 0),
                    "balance_change": safety_data.get("balance_change", 0),
                    "balance_change_pct": safety_data.get("balance_change_pct", 0),
                    "positions": safety_data.get("position_count", 0),
                    "exposure": safety_data.get("position_exposure", 0),
                    "orders": safety_data.get("order_count", 0),
                    "balance_ok": safety_data.get("balance_ok", True),
                    "positions_ok": safety_data.get("positions_ok", True),
                    "orders_ok": safety_data.get("orders_ok", True),
                },
                "alerts": all_alerts,
                "actions": all_actions,
            }

            # Write state file
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

            # Log
            status_icon = "OK" if not all_alerts else "ALERT"
            h = state["health"]
            t = state["trading"]
            logger.info(
                f"[Security] #{cycle} {status_icon} | "
                f"Procs: S={'Y' if h['scalper'] else 'N'} M={'Y' if h['monitor'] else 'N'} D={'Y' if h['dashboard'] else 'N'} | "
                f"API: {h['api_latency_ms']}ms | "
                f"Balance: ${t['balance']:.0f} ({t['balance_change_pct']:+.1f}%) | "
                f"Pos: {t['positions']} Orders: {t['orders']}"
            )

            # AUTO ACTION — Security can kill scalper or flatten positions
            auto_action = safety_data.get("auto_action")
            if auto_action == "pause_scalper":
                logger.warning("[Security] AUTO ACTION: Pausing scalper")
                try:
                    import subprocess
                    subprocess.run(["pkill", "-f", "scalper.py"], timeout=5)
                    state["actions"].append("AUTO: Scalper paused")
                    notifier._send("SECURITY AUTO", "Scalper paused — manual review required")
                except Exception as e:
                    logger.error(f"[Security] Failed to pause scalper: {e}")
            elif auto_action == "emergency_flat":
                logger.warning("[Security] AUTO ACTION: Emergency flatten")
                try:
                    import subprocess
                    # Kill scalper first
                    subprocess.run(["pkill", "-9", "-f", "scalper.py"], timeout=5)
                    # Cancel all orders
                    resp = auth_exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                        "order_status": "OPEN", "product_type": "FUTURE", "limit": "100",
                    })
                    order_ids = [o["order_id"] for o in resp.get("orders", [])]
                    if order_ids:
                        auth_exchange.v3PrivatePostBrokerageOrdersBatchCancel({"order_ids": order_ids})
                        logger.info(f"[Security] Canceled {len(order_ids)} orders")
                    # Close positions
                    import uuid as _uuid
                    resp = auth_exchange.v3PrivateGetBrokerageCfmPositions()
                    for pos in resp.get("positions", []):
                        qty = float(pos.get("number_of_contracts", 0) or 0)
                        if qty == 0:
                            continue
                        pos_side = pos.get("side", "LONG")
                        close_side = "SELL" if pos_side == "LONG" else "BUY"
                        price = float(pos.get("current_price", 0))
                        close_price = round(price * (0.98 if close_side == "SELL" else 1.02), 2)
                        auth_exchange.v3PrivatePostBrokerageOrders({
                            "client_order_id": str(_uuid.uuid4()),
                            "product_id": pos.get("product_id", ""),
                            "side": close_side,
                            "order_configuration": {"limit_limit_gtc": {
                                "base_size": str(int(abs(qty))),
                                "limit_price": str(close_price),
                            }},
                        })
                        logger.info(f"[Security] Closing {pos.get('product_id')} {close_side} {abs(qty)}x")
                    state["actions"].append("AUTO: Emergency flatten executed")
                    notifier._send("EMERGENCY FLAT", "Security auto-flattened all positions — review immediately")
                except Exception as e:
                    logger.error(f"[Security] Emergency flatten failed: {e}")
                    notifier._send("EMERGENCY FAILED", f"Auto-flatten failed: {str(e)[:50]}")

            # Send iMessage for new alerts (5 min cooldown per alert)
            now = time.time()
            for alert in all_alerts:
                alert_key = alert[:30]
                if now - last_alert_time.get(alert_key, 0) > 300:
                    notifier._send("SECURITY", alert)
                    last_alert_time[alert_key] = now
                    logger.warning(f"  ALERT sent: {alert}")

            for action in all_actions:
                logger.info(f"  ACTION: {action}")

            time.sleep(30)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"[Security] Error: {e}", exc_info=True)
            time.sleep(10)

    logger.info("[Security] Stopped")


if __name__ == "__main__":
    main()
