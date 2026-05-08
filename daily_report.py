#!/usr/bin/env python3
"""
Daily PnL Report — generates daily summary, saves to JSON, sends iMessage.
Runs at end of day or on-demand.

Usage:
  python3 daily_report.py          # Generate today's report
  python3 daily_report.py --cron   # Run as scheduled job (11:55 PM daily)
"""

import json
import os
import sys
import time
import logging
import signal as sig
from datetime import datetime, timedelta

import ccxt

from config import Config
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("daily_report.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
REPORT_STATE = os.path.join(os.path.dirname(__file__), "report_state.json")

running = True


def signal_handler(s, frame):
    global running
    running = False


sig.signal(sig.SIGINT, signal_handler)
sig.signal(sig.SIGTERM, signal_handler)


def generate_report(exchange):
    """Generate daily PnL report from exchange data."""
    today = datetime.now().strftime("%Y-%m-%d")

    # CFM Balance
    bal = exchange.v3PrivateGetBrokerageCfmBalanceSummary()
    bs = bal.get("balance_summary", {})
    daily_realized = float(bs.get("daily_realized_pnl", {}).get("value", 0))
    unrealized = float(bs.get("unrealized_pnl", {}).get("value", 0))
    funding = float(bs.get("funding_pnl", {}).get("value", 0))
    cfm_cash = float(bs.get("cfm_usd_balance", {}).get("value", 0))

    # Total balance — use portfolio API (exact match with Coinbase page)
    total_balance = 0
    try:
        portfolio = exchange.v3PrivateGetBrokeragePortfolios()
        portfolio_id = portfolio.get("portfolios", [{}])[0].get("uuid", "")
        if portfolio_id:
            detail = exchange.v3PrivateGetBrokeragePortfoliosPortfolioUuid({"portfolio_uuid": portfolio_id})
            total_balance = float(
                detail.get("breakdown", {})
                .get("portfolio_balances", {})
                .get("total_balance", {})
                .get("value", 0)
            )
    except Exception:
        total_balance = 0

    # Positions
    positions = []
    try:
        resp = exchange.v3PrivateGetBrokerageCfmPositions()
        for pos in resp.get("positions", []):
            qty = float(pos.get("number_of_contracts", 0) or 0)
            if qty != 0:
                positions.append({
                    "product": pos.get("product_id", ""),
                    "side": pos.get("side", ""),
                    "contracts": abs(qty),
                    "entry": float(pos.get("avg_entry_price", 0) or 0),
                    "current": float(pos.get("current_price", 0) or 0),
                    "pnl": float(pos.get("unrealized_pnl", 0) or 0),
                })
    except Exception:
        pass

    # Today's fills
    fills = []
    total_fees = 0
    try:
        resp = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch({
            "order_status": "FILLED",
            "product_type": "FUTURE",
            "limit": "50",
        })
        for o in resp.get("orders", []):
            created = o.get("created_time", "")
            # Convert UTC to local date for comparison
            try:
                utc_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                local_dt = utc_dt.astimezone()
                fill_date = local_dt.strftime("%Y-%m-%d")
            except Exception:
                fill_date = created[:10]
            if fill_date == today:
                price = float(o.get("average_filled_price", 0) or 0)
                qty = float(o.get("filled_size", 0) or 0)
                fee = float(o.get("total_fees", 0) or 0)
                total_fees += fee
                fills.append({
                    "side": o.get("side", ""),
                    "product": o.get("product_id", ""),
                    "price": price,
                    "qty": qty,
                    "fee": fee,
                    "time": o.get("created_time", "")[:19],
                })
    except Exception:
        pass

    # SOL price
    sol_price = 0
    try:
        ticker = exchange.fetch_ticker("SOL/USDC")
        sol_price = ticker.get("last", 0) or 0
    except Exception:
        pass

    total_pnl = daily_realized + unrealized + funding

    report = {
        "date": today,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_balance": round(total_balance, 2),
        "daily_pnl": {
            "total": round(total_pnl, 2),
            "realized": round(daily_realized, 2),
            "unrealized": round(unrealized, 2),
            "funding": round(funding, 2),
            "fees": round(total_fees, 4),
        },
        "positions": positions,
        "fills_today": len(fills),
        "fills": fills,
        "sol_price": round(sol_price, 2),
    }

    return report


def save_report(report):
    """Save report to file and update state."""
    os.makedirs(REPORT_DIR, exist_ok=True)
    filepath = os.path.join(REPORT_DIR, f"{report['date']}.json")
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Update state with all reports for dashboard
    all_reports = []
    for fname in sorted(os.listdir(REPORT_DIR), reverse=True)[:30]:
        if fname.endswith(".json"):
            with open(os.path.join(REPORT_DIR, fname)) as f:
                all_reports.append(json.load(f))

    with open(REPORT_STATE, "w") as f:
        json.dump({"reports": all_reports}, f, indent=2, ensure_ascii=False)

    return filepath


def format_imessage(report):
    """Format report for iMessage."""
    pnl = report["daily_pnl"]
    sign = "+" if pnl["total"] >= 0 else ""
    lines = [
        f"Daily Report {report['date']}",
        f"Balance: ${report['total_balance']:,.2f}",
        f"PnL: {sign}${pnl['total']:.2f}",
        f"  Realized: ${pnl['realized']:+.2f}",
        f"  Unrealized: ${pnl['unrealized']:+.2f}",
        f"  Funding: ${pnl['funding']:+.2f}",
        f"  Fees: -${pnl['fees']:.2f}",
        f"Trades: {report['fills_today']}",
        f"SOL: ${report['sol_price']:.2f}",
    ]
    if report["positions"]:
        for p in report["positions"]:
            lines.append(f"{p['product']} {p['side']} {p['contracts']}x @ ${p['entry']:.2f} PnL: ${p['pnl']:+.2f}")
    return "\n".join(lines)


def main():
    config = Config()
    exchange = ccxt.coinbase({
        "apiKey": os.environ.get("CB_API_KEY", ""),
        "secret": os.environ.get("CB_API_SECRET", ""),
        "enableRateLimit": True,
    })
    exchange.load_markets()
    notifier = Notifier()

    if "--cron" in sys.argv:
        # Run as scheduled job — generate report at 11:55 PM daily
        logger.info("Daily Report running in cron mode (11:55 PM daily)")
        while running:
            now = datetime.now()
            if now.hour == 23 and now.minute == 55:
                report = generate_report(exchange)
                filepath = save_report(report)
                msg = format_imessage(report)
                notifier._send("Daily Report", msg)
                logger.info(f"Report saved: {filepath}")
                logger.info(msg)
                time.sleep(120)  # Skip next minute
            time.sleep(30)
    else:
        # One-shot — generate now
        report = generate_report(exchange)
        filepath = save_report(report)
        msg = format_imessage(report)
        notifier._send("Daily Report", msg)
        logger.info(f"Report saved: {filepath}")
        print(msg)


if __name__ == "__main__":
    main()
