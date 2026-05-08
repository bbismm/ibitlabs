#!/usr/bin/env python3
"""
System Doctor — 自动监控 + 自动修复
每60秒巡检一次，发现问题自动修复并发送通知

检查项:
  1. 进程存活 (scalper, monitor, dashboard, security)
  2. 挂单数量 (太少=网格被打穿, 太多=堆积)
  3. 库存偏移 (持仓方向性过大)
  4. API 连通性 (exchange是否能请求)
  5. 日志异常 (连续error, 进程卡死)
  6. 余额安全 (buying power 过低)
"""

import os
import sys
import time
import json
import logging
import subprocess
import ccxt

DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(DIR)

# Load .env file directly (launchd can't source bash)
env_path = os.path.join(DIR, ".env")
if os.path.exists(env_path):
    raw = open(env_path).read()
    # Parse: export KEY="value" (supports multiline values in double quotes)
    import re
    for m in re.finditer(r'export\s+(\w+)="((?:[^"\\]|\\.)*)"', raw, re.DOTALL):
        os.environ[m.group(1)] = m.group(2)

from config import Config
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DOCTOR] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("doctor.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Config ──
CHECK_INTERVAL = 60        # seconds between checks
PROCESS_MAP = {
    "scalper":   {"grep": "scalper.py",          "start": "start_scalper.sh"},
    "monitor":   {"grep": "monitor_harness.py",  "start": "start_monitor.sh"},
    "dashboard": {"grep": "owner_harness.py",    "start": "start_owner.sh"},
    "security":  {"grep": "security_harness.py", "start": "start_security.sh"},
}
MIN_ORDERS = 4             # fewer than this = grid dead
MAX_INVENTORY = 6          # absolute inventory above this = danger
MIN_BUYING_POWER = 50.0    # below this = can't place new orders
STALE_LOG_SECONDS = 300    # no log update in 5min = process stuck
MAX_CONSECUTIVE_ERRORS = 5 # restart after this many errors in log tail


def is_process_alive(grep_pattern):
    """Check if a process matching the pattern is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", grep_pattern],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split("\n")
        # Filter out our own PID and empty lines
        pids = [p for p in pids if p and int(p) != os.getpid()]
        return len(pids) > 0
    except Exception:
        return False


def restart_process(name, start_script, notifier):
    """Restart a dead process."""
    script_path = os.path.join(DIR, start_script)
    if not os.path.exists(script_path):
        log.warning(f"Start script not found: {script_path}")
        return False
    try:
        subprocess.Popen(
            ["bash", script_path],
            stdout=open(f"logs/{name}_doctor.log", "a"),
            stderr=subprocess.STDOUT,
            cwd=DIR,
            start_new_session=True,
        )
        log.info(f"RESTARTED {name} via {start_script}")
        notifier._send("Doctor: Restart", f"{name} was dead — restarted")
        return True
    except Exception as e:
        log.error(f"Failed to restart {name}: {e}")
        return False


def create_exchange():
    """Create exchange connection for health checks."""
    return ccxt.coinbase({
        "apiKey": os.environ.get("CB_API_KEY", ""),
        "secret": os.environ.get("CB_API_SECRET", ""),
        "enableRateLimit": True,
    })


def check_orders(exchange):
    """Check open order count (spot + futures)."""
    try:
        total = 0
        for pt in ("SPOT", "FUTURE"):
            resp = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                "order_status": "OPEN",
                "product_type": pt,
                "limit": "100",
            })
            total += len(resp.get("orders", []))
        return total
    except Exception as e:
        log.warning(f"Order check failed: {e}")
        return -1


def check_positions(exchange):
    """Check position inventory."""
    try:
        resp = exchange.v3PrivateGetBrokerageCfmPositions()
        positions = {}
        for pos in resp.get("positions", []):
            qty = float(pos.get("number_of_contracts", 0) or 0)
            if qty == 0:
                continue
            product = pos.get("product_id", "")
            side = pos.get("side", "LONG")
            unrealized = float(pos.get("unrealized_pnl", 0) or 0)
            inv = abs(qty) if side == "LONG" else -abs(qty)
            positions[product] = {"inventory": inv, "unrealized": unrealized}
        return positions
    except Exception as e:
        log.warning(f"Position check failed: {e}")
        return {}


def check_buying_power(exchange):
    """Check available buying power."""
    try:
        bal = exchange.v3PrivateGetBrokerageCfmBalanceSummary()
        bp = float(bal.get("balance_summary", {}).get("futures_buying_power", {}).get("value", "0"))
        return bp
    except Exception:
        return -1


def check_margin_ratio(exchange):
    """Returns (initial_margin, total_balance, ratio) or (0, 0, 0) on error."""
    try:
        bal = exchange.v3PrivateGetBrokerageCfmBalanceSummary()
        bs = bal.get("balance_summary", {})
        initial_margin = float(bs.get("initial_margin", {}).get("value", 0) or 0)
        buying_power = float(bs.get("futures_buying_power", {}).get("value", 0) or 0)
        orders_hold = abs(float(bs.get("total_open_orders_hold_amount", {}).get("value", 0) or 0))
        total = buying_power + orders_hold + initial_margin
        ratio = initial_margin / total if total > 0 else 0
        return initial_margin, total, ratio
    except Exception as e:
        log.warning(f"Margin ratio check failed: {e}")
        return 0, 0, 0


def check_log_health(logfile, stale_seconds=STALE_LOG_SECONDS):
    """Check if a log file has been updated recently and count recent errors."""
    path = os.path.join(DIR, logfile)
    if not os.path.exists(path):
        return {"stale": True, "errors": 0}

    mtime = os.path.getmtime(path)
    age = time.time() - mtime
    stale = age > stale_seconds

    # Count recent errors in last 50 lines
    errors = 0
    try:
        result = subprocess.run(
            ["tail", "-50", path],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.split("\n"):
            if "[ERROR]" in line or "Traceback" in line:
                errors += 1
    except Exception:
        pass

    return {"stale": stale, "age_seconds": int(age), "errors": errors}


def main():
    config = Config()
    notifier = Notifier()
    notifier.enabled = True

    # Ensure logs dir exists
    os.makedirs(os.path.join(DIR, "logs"), exist_ok=True)

    log.info("=" * 50)
    log.info("  System Doctor — Online")
    log.info(f"  Check interval: {CHECK_INTERVAL}s")
    log.info(f"  Monitoring: {', '.join(PROCESS_MAP.keys())}")
    log.info("=" * 50)
    notifier._send("Doctor Online", "System doctor is monitoring all processes")

    exchange = None
    consecutive_api_fails = 0
    restart_cooldown = {}  # name → last restart timestamp

    while True:
        try:
            issues = []
            fixes = []

            # ── 1. Process health ──
            for name, info in PROCESS_MAP.items():
                alive = is_process_alive(info["grep"])
                if not alive:
                    issues.append(f"{name} is DOWN")
                    # Cooldown: don't restart same process within 120s
                    last_restart = restart_cooldown.get(name, 0)
                    if time.time() - last_restart > 120:
                        if restart_process(name, info["start"], notifier):
                            fixes.append(f"restarted {name}")
                            restart_cooldown[name] = time.time()
                    else:
                        wait = int(120 - (time.time() - last_restart))
                        log.info(f"{name} still in restart cooldown ({wait}s left)")

            # ── 2. Exchange checks (only if scalper is running) ──
            if is_process_alive("scalper.py"):
                try:
                    if exchange is None:
                        exchange = create_exchange()
                        exchange.load_markets()
                    consecutive_api_fails = 0

                    # Order count
                    order_count = check_orders(exchange)
                    if order_count == 0:
                        issues.append(f"NO open orders — grid is empty!")
                        notifier._send("Doctor: No Orders", "Grid is empty — scalper may need restart")
                        # Force restart scalper
                        last_restart = restart_cooldown.get("scalper", 0)
                        if time.time() - last_restart > 300:  # 5分钟冷却，避免反复重启
                            subprocess.run(["pkill", "-f", "scalper.py"], timeout=5)
                            time.sleep(3)
                            restart_process("scalper", "start_scalper.sh", notifier)
                            restart_cooldown["scalper"] = time.time()
                            fixes.append("restarted scalper (empty grid)")
                    elif 0 < order_count < MIN_ORDERS:
                        issues.append(f"Only {order_count} orders — grid is thin")
                        notifier._send("Doctor: Low Orders", f"Only {order_count} orders — grid might need rebuild")

                    # Positions
                    positions = check_positions(exchange)
                    for product, data in positions.items():
                        inv = data["inventory"]
                        unr = data["unrealized"]
                        if abs(inv) > MAX_INVENTORY:
                            issues.append(f"{product} inventory={inv:+.0f} exceeds limit")
                            notifier._send("Doctor: High Inventory", f"{product} inv={inv:+.0f} — check scalper")

                    # Buying power
                    bp = check_buying_power(exchange)
                    if 0 < bp < MIN_BUYING_POWER:
                        issues.append(f"Buying power ${bp:.0f} critically low")
                        notifier._send("Doctor: Low Balance", f"Buying power only ${bp:.0f}")

                    # Margin ratio
                    im, total_bal, margin_ratio = check_margin_ratio(exchange)
                    if margin_ratio > 0.90:
                        issues.append(f"CRITICAL: margin ratio {margin_ratio*100:.0f}% — near liquidation!")
                        notifier._send("MARGIN CRITICAL", f"Margin {margin_ratio*100:.0f}% of ${total_bal:.0f} — cancelling all orders")
                        try:
                            resp = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                                "order_status": "OPEN", "product_type": "FUTURE", "limit": "100"
                            })
                            order_ids = [o["order_id"] for o in resp.get("orders", [])]
                            if order_ids:
                                exchange.v3PrivatePostBrokerageOrdersBatchCancel({"order_ids": order_ids})
                                fixes.append(f"cancelled {len(order_ids)} orders (margin critical {margin_ratio*100:.0f}%)")
                                log.warning(f"MARGIN CRITICAL: cancelled {len(order_ids)} orders to free margin")
                        except Exception as e:
                            log.error(f"Emergency cancel failed: {e}")
                    elif margin_ratio > 0.80:
                        issues.append(f"WARNING: margin ratio {margin_ratio*100:.0f}% — getting crowded")
                        notifier._send("MARGIN WARNING", f"Margin {margin_ratio*100:.0f}% of ${total_bal:.0f} — cancelling half orders")
                        try:
                            resp = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
                                "order_status": "OPEN", "product_type": "FUTURE", "limit": "100"
                            })
                            orders = resp.get("orders", [])
                            half = orders[:len(orders) // 2]
                            if half:
                                exchange.v3PrivatePostBrokerageOrdersBatchCancel({"order_ids": [o["order_id"] for o in half]})
                                fixes.append(f"cancelled {len(half)} orders (margin warning {margin_ratio*100:.0f}%)")
                                log.warning(f"MARGIN WARNING: cancelled {len(half)} orders to ease margin")
                        except Exception as e:
                            log.warning(f"Margin order cancel failed: {e}")
                    elif im > 0:
                        log.info(f"Margin ratio: {margin_ratio*100:.0f}% (${im:.0f} / ${total_bal:.0f})")

                except ccxt.NetworkError as e:
                    consecutive_api_fails += 1
                    log.warning(f"API network error ({consecutive_api_fails}): {e}")
                    if consecutive_api_fails >= 3:
                        exchange = None  # Force reconnect
                        issues.append("API connection lost — reconnecting")
                except Exception as e:
                    consecutive_api_fails += 1
                    log.warning(f"Exchange check failed ({consecutive_api_fails}): {e}")
                    if consecutive_api_fails >= 5:
                        exchange = None

            # ── 3. Log health ──
            log_checks = {
                "scalper": "scalper.log",
                "monitor": "monitor.log",
            }
            for name, logfile in log_checks.items():
                health = check_log_health(logfile)
                if health.get("stale") and is_process_alive(PROCESS_MAP.get(name, {}).get("grep", "")):
                    issues.append(f"{name} log stale ({health.get('age_seconds', '?')}s)")
                    # Process alive but not logging = stuck
                    last_restart = restart_cooldown.get(name, 0)
                    if time.time() - last_restart > 300:
                        grep_pat = PROCESS_MAP[name]["grep"]
                        subprocess.run(["pkill", "-f", grep_pat], timeout=5)
                        time.sleep(3)
                        restart_process(name, PROCESS_MAP[name]["start"], notifier)
                        restart_cooldown[name] = time.time()
                        fixes.append(f"restarted stuck {name}")
                if health.get("errors", 0) > MAX_CONSECUTIVE_ERRORS:
                    issues.append(f"{name} has {health['errors']} recent errors")

            # ── Summary ──
            if issues:
                log.warning(f"Issues: {'; '.join(issues)}")
                if fixes:
                    log.info(f"Fixes applied: {'; '.join(fixes)}")
            else:
                # Quiet heartbeat every 5 minutes
                if int(time.time()) % 300 < CHECK_INTERVAL:
                    bp_str = f"${bp:.0f}" if 'bp' in dir() and bp > 0 else "?"
                    oc_str = str(order_count) if 'order_count' in dir() and order_count >= 0 else "?"
                    mr_str = f"{margin_ratio*100:.0f}%" if 'margin_ratio' in dir() and margin_ratio > 0 else "?"
                    log.info(f"All clear | orders={oc_str} | buying_power={bp_str} | margin={mr_str}")

        except Exception as e:
            log.error(f"Doctor cycle failed: {e}", exc_info=True)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
