#!/usr/bin/env python3
"""
BIBSUS Growth Harness — Autonomous business operations engine.

Orchestrates 6 AI agents that run the entire business:
  - MarketingAgent: Auto-tweets trading results (every 4h)
  - ContentAgent: Generates reports & education (every 6h)
  - SalesAgent: Email drip & conversion tracking (every 1h)
  - AnalyticsAgent: MRR/churn/KPI tracking (every 2h)
  - CommunityAgent: Discord management (every 2h)
  - SupportAgent: Auto customer support (every 30m)

CEO Dashboard: Daily briefing via iMessage + web dashboard on port 8090.

Usage:
  export TWITTER_API_KEY='...'     # optional: enables auto-tweeting
  export DISCORD_BOT_TOKEN='...'   # optional: enables Discord bot
  export STRIPE_SECRET_KEY='...'   # optional: enables revenue tracking
  export SENDGRID_API_KEY='...'    # optional: enables email automation
  python3 growth_harness.py

All agents degrade gracefully — if API keys are missing, they log/queue
actions instead of failing. Start with zero keys and add them as you go.
"""

import json
import os
import sys
import time
import logging
import signal
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread


def load_dotenv(path=None):
    """Load .env file into os.environ. No dependencies needed."""
    if path is None:
        path = Path(__file__).parent / ".env"
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Only set if not already in environment (real env takes priority)
            if key and value and not os.environ.get(key):
                os.environ[key] = value


load_dotenv()


from growth import (
    MarketingAgent, ContentAgent, SalesAgent,
    AnalyticsAgent, CommunityAgent, SupportAgent,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("growth.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

running = True


def signal_handler(sig, frame):
    global running
    logger.info("[Growth] Shutting down...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class GrowthHarness:
    """
    Master orchestrator for all growth agents.
    Each agent has its own interval and runs independently.
    """

    def __init__(self):
        self.agents = {
            "marketing": MarketingAgent(),
            "content": ContentAgent(),
            "sales": SalesAgent(),
            "analytics": AnalyticsAgent(),
            "community": CommunityAgent(),
            "support": SupportAgent(),
        }
        self.cycle = 0
        self.start_time = datetime.now()
        logger.info(f"Growth Harness initialized: {len(self.agents)} agents")
        for name, agent in self.agents.items():
            logger.info(f"  [{name}] interval={agent.interval}s")

    def run_cycle(self) -> dict:
        """Run all agents that are due. Returns summary."""
        self.cycle += 1
        results = {}

        for name, agent in self.agents.items():
            if agent.should_run():
                try:
                    result = agent.run()
                    results[name] = result
                    if not result.get("skipped"):
                        logger.info(f"[{name}] Executed: {json.dumps(result)[:120]}")
                except Exception as e:
                    results[name] = {"error": str(e)}
                    logger.error(f"[{name}] Failed: {e}")

        return results

    def get_dashboard_data(self) -> dict:
        """Full status for CEO dashboard."""
        return {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "uptime": str(datetime.now() - self.start_time).split(".")[0],
            "cycle": self.cycle,
            "agents": {
                name: agent.get_status()
                for name, agent in self.agents.items()
            },
            "analytics": self.agents["analytics"].state.get("stats", {}),
            "marketing": {
                "tweets_today": len(self.agents["marketing"].state.get("tweets_today", [])),
                "total_tweets": self.agents["marketing"].state.get("total_tweets", 0),
            },
            "sales": self.agents["sales"].state.get("stats", {}),
            "support": self.agents["support"].state.get("stats", {}),
            "community": self.agents["community"].state.get("latest_engagement", {}),
        }

    def send_daily_briefing(self):
        """Send CEO briefing via iMessage (reuses existing Notifier)."""
        try:
            from notifier import Notifier
            notifier = Notifier()

            analytics = self.agents["analytics"]
            kpi = analytics.state.get("stats", {})
            marketing = self.agents["marketing"].state

            msg_lines = [
                "BIBSUS Growth Daily Brief",
                f"Uptime: {str(datetime.now() - self.start_time).split('.')[0]}",
                f"Tweets today: {len(marketing.get('tweets_today', []))}",
                f"Total tweets: {marketing.get('total_tweets', 0)}",
            ]

            # Add analytics if available
            if kpi:
                msg_lines.append(f"MRR: ${kpi.get('mrr', 0):,.0f}")
                msg_lines.append(f"Active subs: {kpi.get('active_subscriptions', 0)}")

            support_stats = self.agents["support"].state.get("stats", {})
            if support_stats:
                msg_lines.append(f"Tickets: {support_stats.get('total_tickets', 0)} (auto: {support_stats.get('auto_resolve_rate', 0)}%)")

            notifier._send("Growth Brief", "\n".join(msg_lines))
            logger.info("[Growth] CEO briefing sent via iMessage")
        except Exception as e:
            logger.warning(f"[Growth] Briefing send failed: {e}")


# ── CEO Dashboard Web Server (port 8090) ──

harness = GrowthHarness()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BIBSUS Growth — CEO Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0a0f; color: #e0e0e0; font-family: 'SF Mono', monospace; padding: 20px; }
  h1 { color: #a855f7; margin-bottom: 20px; font-size: 1.4em; }
  h2 { color: #7c3aed; margin: 20px 0 10px; font-size: 1.1em; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
  .card { background: #1a1a2e; border: 1px solid #2d2d4e; border-radius: 12px; padding: 16px; }
  .card h3 { color: #a855f7; font-size: 0.9em; margin-bottom: 8px; }
  .stat { font-size: 1.8em; font-weight: bold; color: #fff; }
  .stat.green { color: #22c55e; }
  .stat.red { color: #ef4444; }
  .stat.purple { color: #a855f7; }
  .label { font-size: 0.75em; color: #888; margin-top: 4px; }
  .agent-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #1a1a2e; }
  .agent-name { color: #a855f7; }
  .agent-stat { color: #888; font-size: 0.85em; }
  .status-ok { color: #22c55e; }
  .status-warn { color: #f59e0b; }
  .footer { margin-top: 30px; text-align: center; color: #444; font-size: 0.75em; }
  #refresh { color: #666; font-size: 0.8em; }
</style>
</head>
<body>
<h1>BIBSUS Growth Engine</h1>
<p id="refresh">Loading...</p>

<div class="grid" id="kpis"></div>

<h2>Agent Status</h2>
<div id="agents"></div>

<div class="footer">BIBSUS Alpha — Fully Autonomous Growth Engine</div>

<script>
async function refresh() {
  try {
    const r = await fetch('/api/dashboard');
    const d = await r.json();
    document.getElementById('refresh').textContent = `Last update: ${d.ts} | Uptime: ${d.uptime} | Cycle: ${d.cycle}`;

    const a = d.analytics || {};
    const m = d.marketing || {};
    const s = d.sales || {};
    const sup = d.support || {};
    const com = d.community || {};

    document.getElementById('kpis').innerHTML = `
      <div class="card"><h3>MRR</h3><div class="stat purple">$${(a.mrr||0).toLocaleString()}</div><div class="label">Monthly Recurring Revenue</div></div>
      <div class="card"><h3>Active Subs</h3><div class="stat">${a.active_subscriptions||0}</div><div class="label">Signals: ${a.signals_count||0} | Autopilot: ${a.autopilot_count||0}</div></div>
      <div class="card"><h3>Churn</h3><div class="stat ${(a.churn_rate_pct||0)>10?'red':'green'}">${a.churn_rate_pct||0}%</div><div class="label">30-day cancellation rate</div></div>
      <div class="card"><h3>Tweets Today</h3><div class="stat">${m.tweets_today||0}</div><div class="label">Total: ${m.total_tweets||0}</div></div>
      <div class="card"><h3>Leads</h3><div class="stat">${s.total_leads||0}</div><div class="label">Free: ${s.free||0} | Paid: ${(s.signals||0)+(s.autopilot||0)}</div></div>
      <div class="card"><h3>Support</h3><div class="stat">${sup.total_tickets||0}</div><div class="label">Auto-resolve: ${sup.auto_resolve_rate||0}% | Pending: ${sup.pending||0}</div></div>
      <div class="card"><h3>Discord</h3><div class="stat">${com.members||0}</div><div class="label">Online: ${com.online||0}</div></div>
    `;

    const agents = d.agents || {};
    let html = '';
    for (const [name, info] of Object.entries(agents)) {
      const stats = info.stats || {};
      const cls = stats.errors > 0 ? 'status-warn' : 'status-ok';
      html += `<div class="agent-row">
        <span class="agent-name">${name}</span>
        <span class="agent-stat">Actions: ${stats.actions_taken||0} | Errors: <span class="${cls}">${stats.errors||0}</span> | Last: ${stats.last_action||'never'}</span>
      </div>`;
    }
    document.getElementById('agents').innerHTML = html;
  } catch(e) {
    document.getElementById('refresh').textContent = 'Error: ' + e.message;
  }
}
refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/dashboard":
            data = harness.get_dashboard_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())

    def log_message(self, format, *args):
        pass


def main():
    port = int(os.environ.get("GROWTH_PORT", 8090))

    # Start dashboard server in background thread
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    logger.info("=" * 60)
    logger.info("  BIBSUS Growth Engine — Autonomous Operations")
    logger.info(f"  CEO Dashboard: http://localhost:{port}")
    logger.info(f"  Agents: {len(harness.agents)}")
    logger.info("  Mode: FULLY AUTONOMOUS")
    logger.info("=" * 60)

    # Check which APIs are configured
    apis = {
        "Twitter": bool(os.environ.get("TWITTER_API_KEY")),
        "Discord": bool(os.environ.get("DISCORD_BOT_TOKEN")),
        "Stripe": bool(os.environ.get("STRIPE_SECRET_KEY")),
        "SendGrid": bool(os.environ.get("SENDGRID_API_KEY")),
    }
    for name, configured in apis.items():
        status = "CONNECTED" if configured else "OFFLINE (will queue)"
        logger.info(f"  {name}: {status}")
    logger.info("=" * 60)

    last_briefing_date = ""

    while running:
        try:
            results = harness.run_cycle()

            if results:
                active = [k for k, v in results.items() if not v.get("skipped")]
                if active:
                    logger.info(f"[Growth] Cycle #{harness.cycle} — active: {', '.join(active)}")

            # Daily CEO briefing at 9 PM
            now = datetime.now()
            if now.hour == 21 and now.strftime("%Y-%m-%d") != last_briefing_date:
                harness.send_daily_briefing()
                last_briefing_date = now.strftime("%Y-%m-%d")

            time.sleep(60)  # check every minute (agents have own intervals)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"[Growth] Error: {e}", exc_info=True)
            time.sleep(30)

    logger.info("[Growth] Engine stopped.")
    server.shutdown()


if __name__ == "__main__":
    main()
