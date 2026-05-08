#!/usr/bin/env python3
"""Probe Coinbase endpoints for cumulative funding data."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from coinbase_exchange import CoinbaseExchange


def clean(o, depth=0):
    if depth > 6:
        return "..."
    if isinstance(o, dict):
        return {k: clean(v, depth + 1) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v, depth + 1) for v in o[:5]]
    if hasattr(o, '__dict__'):
        return clean(vars(o), depth + 1)
    return o


def dump(label, fn):
    print(f"\n== {label} ==")
    try:
        resp = fn()
        raw = resp if isinstance(resp, dict) else vars(resp)
        print(json.dumps(clean(raw), indent=2, default=str)[:4000])
    except Exception as e:
        print(f"ERR: {e}")


cfg = Config()
ex = CoinbaseExchange(cfg.cb_api_key, cfg.cb_api_secret)

resp = ex.client.get_portfolios()
raw = resp if isinstance(resp, dict) else vars(resp)
portfolios = raw.get("portfolios", [])
if not portfolios:
    print("no portfolios"); sys.exit(1)
p = portfolios[0]
pd = p if isinstance(p, dict) else vars(p)
uuid = pd.get("uuid")
print(f"portfolio uuid: {uuid}")

dump("get_portfolio_breakdown", lambda: ex.client.get_portfolio_breakdown(portfolio_uuid=uuid))
dump("get_futures_balance_summary", lambda: ex.client.get_futures_balance_summary())

from datetime import datetime, timedelta, timezone
end = datetime.now(timezone.utc)
start = end - timedelta(days=30)
dump("get_transaction_summary", lambda: ex.client.get_transaction_summary(
    start_date=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
    end_date=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
))

# list_futures_sweeps may contain funding-related events
if 'list_futures_sweeps' in dir(ex.client):
    dump("list_futures_sweeps", lambda: ex.client.list_futures_sweeps())

# list_perps_positions (unlikely to have cumulative, but check)
dump("list_perps_positions", lambda: ex.client.list_perps_positions(portfolio_uuid=uuid))

# get_perps_position for SLP-20DEC30-CDE — may have funding_pnl
dump("get_perps_position (SLP)", lambda: ex.client.get_perps_position(
    portfolio_uuid=uuid, symbol="SLP-20DEC30-CDE"))
