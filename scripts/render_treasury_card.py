#!/usr/bin/env python3
"""
render_treasury_card.py — Render Agent Carry's budget card as a self-contained HTML.

Reads state/treasury_cost.json + state/treasury_runway.json and emits a 1080x1080
HTML card suitable for screenshotting with Cmd+Shift+4 on macOS. No external
dependencies, no image libraries — just pure HTML/CSS you open in Safari.

Output: out/publish_bundle/agent_carry_debut/dashboard_card.html (by default)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent
STATE_DIR   = REPO_ROOT / "state"
DEFAULT_OUT = REPO_ROOT / "out" / "publish_bundle" / "agent_carry_debut" / "dashboard_card.html"


STATUS_COLORS = {
    "green":   "#00d47e",
    "yellow":  "#f5c542",
    "orange":  "#ff8a3d",
    "red":     "#ff3d5c",
    "in_debt": "#8a8a8a",
}

STATUS_LABELS = {
    "green":   "HEALTHY",
    "yellow":  "SHORT",
    "orange":  "TIGHT",
    "red":     "CRITICAL",
    "in_debt": "IN DEBT",
}


def render(cost: dict, runway: dict) -> str:
    name = runway.get("agent_name", "Agent Carry")
    profit_pool = runway.get("profit_pool_usd", 0.0)
    daily_burn = runway.get("daily_burn_usd", 0.0)
    runway_days = runway.get("runway_days")
    status = runway.get("status", "red")
    milestone = runway.get("milestone_days", 90)
    progress_pct = runway.get("progress_pct", 0.0)
    rp = runway.get("realized_profit", {})
    trade_count = rp.get("trade_count", 0)

    runway_label = "∞" if runway_days is None else f"{runway_days:.1f}"
    status_color = STATUS_COLORS.get(status, STATUS_COLORS["red"])
    status_label = STATUS_LABELS.get(status, "CRITICAL")

    updated_dt = datetime.fromisoformat(runway["updated_at"].replace("Z", "+00:00"))
    updated_human = updated_dt.strftime("%d %b %Y · %H:%M UTC")

    layers = cost.get("layers", {})
    l1 = layers.get("L1_cloud_api", {}).get("subtotal", 0.0)
    l2 = layers.get("L2_hardware_network", {}).get("subtotal", 0.0)
    l3 = layers.get("L3_claude", {}).get("subtotal", 0.0)
    total_month = cost.get("total_usd_per_month", 0.0)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{name}'s Budget</title>
<style>
  :root {{
    --bg: #0b0d12;
    --card: #12151d;
    --border: #1f2330;
    --text: #e8ecf4;
    --dim: #8a93a6;
    --accent: {status_color};
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    background: #000;
    font-family: -apple-system, "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  .stage {{
    width: 1080px;
    height: 1080px;
    background: linear-gradient(160deg, #0b0d12 0%, #12151d 100%);
    color: var(--text);
    padding: 72px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .brand {{
    font-size: 28px;
    letter-spacing: 0.22em;
    color: var(--dim);
    text-transform: uppercase;
    font-weight: 500;
  }}
  .date {{
    font-size: 22px;
    color: var(--dim);
  }}
  .title-row {{
    display: flex;
    align-items: center;
    gap: 20px;
    margin-top: 28px;
  }}
  .agent-dot {{
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 24px var(--accent);
  }}
  .agent-name {{
    font-size: 54px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }}
  .hero {{
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 24px;
  }}
  .hero-label {{
    font-size: 26px;
    color: var(--dim);
    text-transform: uppercase;
    letter-spacing: 0.18em;
  }}
  .hero-runway {{
    font-size: 220px;
    font-weight: 800;
    line-height: 0.95;
    color: var(--accent);
    letter-spacing: -0.04em;
    font-variant-numeric: tabular-nums;
  }}
  .hero-unit {{
    font-size: 40px;
    font-weight: 500;
    color: var(--dim);
    margin-top: -10px;
  }}
  .hero-quote {{
    font-size: 28px;
    color: var(--text);
    margin-top: 20px;
    max-width: 820px;
    line-height: 1.4;
  }}
  .stats {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 20px;
    margin-top: 32px;
  }}
  .stat {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 26px 28px;
  }}
  .stat-k {{
    font-size: 18px;
    color: var(--dim);
    text-transform: uppercase;
    letter-spacing: 0.14em;
  }}
  .stat-v {{
    font-size: 42px;
    font-weight: 700;
    margin-top: 8px;
    font-variant-numeric: tabular-nums;
  }}
  .stat-sub {{
    font-size: 16px;
    color: var(--dim);
    margin-top: 6px;
  }}
  .progress-wrap {{
    margin-top: 28px;
  }}
  .progress-head {{
    display: flex;
    justify-content: space-between;
    font-size: 18px;
    color: var(--dim);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin-bottom: 12px;
  }}
  .progress-bar {{
    height: 14px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 999px;
    overflow: hidden;
  }}
  .progress-fill {{
    height: 100%;
    background: var(--accent);
    width: {max(1, progress_pct):.1f}%;
    border-radius: 999px;
    transition: width 0.4s ease;
  }}
  .footer {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    font-size: 20px;
    color: var(--dim);
  }}
  .footer-left {{
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .footer-rule {{
    font-size: 18px;
    max-width: 560px;
    line-height: 1.5;
  }}
  .footer-right {{
    text-align: right;
  }}
  .status-pill {{
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 10px 20px;
    border-radius: 999px;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--accent);
    font-size: 18px;
    letter-spacing: 0.14em;
    color: var(--accent);
    text-transform: uppercase;
    font-weight: 600;
  }}
</style>
</head>
<body>
  <div class="stage">
    <div>
      <div class="header">
        <div class="brand">iBitLabs · AI Treasury</div>
        <div class="date">{updated_human}</div>
      </div>
      <div class="title-row">
        <div class="agent-dot"></div>
        <div class="agent-name">{name}</div>
        <div style="flex:1"></div>
        <div class="status-pill">{status_label}</div>
      </div>

      <div class="hero">
        <div class="hero-label">Runway</div>
        <div class="hero-runway">{runway_label}</div>
        <div class="hero-unit">days until she can't afford her own electricity</div>
      </div>

      <div class="stats">
        <div class="stat">
          <div class="stat-k">Profit pool</div>
          <div class="stat-v">${profit_pool:,.2f}</div>
          <div class="stat-sub">above the $1,000 principal floor</div>
        </div>
        <div class="stat">
          <div class="stat-k">Daily burn</div>
          <div class="stat-v">${daily_burn:,.2f}</div>
          <div class="stat-sub">cloud · electricity · Claude rent</div>
        </div>
        <div class="stat">
          <div class="stat-k">Trades</div>
          <div class="stat-v">{trade_count}</div>
          <div class="stat-sub">realized, public, auto-broadcast</div>
        </div>
      </div>

      <div class="progress-wrap">
        <div class="progress-head">
          <span>First milestone · {milestone} days self-sufficient</span>
          <span>{progress_pct:.1f}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill"></div>
        </div>
      </div>
    </div>

    <div class="footer">
      <div class="footer-left">
        <div class="footer-rule">
          Monthly burn: L1 cloud ${l1:.0f} · L2 hardware ${l2:.2f} · L3 Claude ${l3:.0f} = ${total_month:.2f}/mo
        </div>
        <div>The $1,000 principal is untouchable. Only realized profit pays rent.</div>
      </div>
      <div class="footer-right">
        trade.ibitlabs.com
      </div>
    </div>
  </div>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render Agent Carry's budget card as HTML.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output HTML path")
    args = ap.parse_args()

    cost_path = STATE_DIR / "treasury_cost.json"
    runway_path = STATE_DIR / "treasury_runway.json"
    for p in (cost_path, runway_path):
        if not p.exists():
            print(f"[render_card] missing {p} — run the treasury scripts first.")
            return 1

    with cost_path.open("r", encoding="utf-8") as f:
        cost = json.load(f)
    with runway_path.open("r", encoding="utf-8") as f:
        runway = json.load(f)

    html = render(cost, runway)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")

    print(f"[render_card] wrote {args.out}")
    print(f"[render_card] open it:  open {args.out}")
    print(f"[render_card] screenshot with Cmd+Shift+4, crop to the card region")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
