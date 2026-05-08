"""
Analytics Agent — The brain. Tracks MRR, churn, CAC, LTV, and all KPIs.

Aggregates data from Stripe + trading reports + leads.
Generates daily/weekly CEO briefing with actionable insights.
Triggers alerts: churn spike, revenue milestone, anomalies.

Required env vars:
  STRIPE_SECRET_KEY — for revenue data
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .base_growth_agent import BaseGrowthAgent

logger = logging.getLogger(__name__)

REPORT_STATE = Path(__file__).parent.parent / "report_state.json"
LEADS_FILE = Path(__file__).parent.parent / "growth_state" / "leads.json"
ANALYTICS_DIR = Path(__file__).parent.parent / "growth_state" / "analytics"
ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)


class AnalyticsAgent(BaseGrowthAgent):
    """
    CEO intelligence agent. Runs every 2 hours.

    Tracks:
    - MRR (Monthly Recurring Revenue) from Stripe
    - Churn rate (cancellations / active subs)
    - Conversion funnel (free → signals → autopilot)
    - Trading performance (cumulative PnL, win days %)
    - CAC (if ad spend tracked) & LTV estimates

    Outputs:
    - analytics/daily_kpi.json — refreshed every cycle
    - analytics/ceo_briefing.md — daily CEO summary
    - Alerts via Notifier for milestones / anomalies
    """

    def __init__(self):
        super().__init__("analytics", interval_seconds=2 * 3600)

    def execute(self) -> dict:
        # Gather all data
        stripe_data = self._fetch_stripe_metrics()
        trading_data = self._fetch_trading_metrics()
        funnel_data = self._fetch_funnel_metrics()

        kpi = {
            "generated_at": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "revenue": stripe_data,
            "trading": trading_data,
            "funnel": funnel_data,
            "health_score": self._calculate_health_score(stripe_data, trading_data, funnel_data),
        }

        # Save KPI
        kpi_path = ANALYTICS_DIR / "daily_kpi.json"
        kpi_path.write_text(json.dumps(kpi, indent=2, ensure_ascii=False))

        # Generate CEO briefing (once per day)
        today = datetime.now().strftime("%Y-%m-%d")
        if self.state.get("last_briefing_date") != today:
            briefing = self._generate_ceo_briefing(kpi)
            briefing_path = ANALYTICS_DIR / f"ceo_briefing_{today}.md"
            briefing_path.write_text(briefing, encoding="utf-8")
            self.state["last_briefing_date"] = today
            self._log_action("CEO_BRIEFING", f"Generated for {today}")

        # Check for alerts
        alerts = self._check_alerts(kpi)
        if alerts:
            self._log_action("ALERTS", f"{len(alerts)} alerts: {', '.join(alerts)}")

        # Track history
        history = self.state.get("kpi_history", [])
        history.append({
            "date": today,
            "mrr": stripe_data.get("mrr", 0),
            "active_subs": stripe_data.get("active_subscriptions", 0),
            "total_leads": funnel_data.get("total_leads", 0),
        })
        self.state["kpi_history"] = history[-90:]  # keep 90 days

        return {"kpi": kpi, "alerts": alerts}

    def _fetch_stripe_metrics(self) -> dict:
        stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if not stripe_key:
            return self._estimate_revenue()

        try:
            # Active subscriptions
            resp = requests.get(
                "https://api.stripe.com/v1/subscriptions",
                headers={"Authorization": f"Bearer {stripe_key}"},
                params={"status": "active", "limit": 100},
                timeout=15,
            )
            subs = resp.json().get("data", []) if resp.status_code == 200 else []

            mrr = 0
            tier_counts = {"signals": 0, "autopilot": 0}
            for sub in subs:
                amount = sub.get("plan", {}).get("amount", 0) / 100  # cents to dollars
                nickname = (sub.get("plan", {}).get("nickname", "") or "").lower()
                mrr += amount
                if "signal" in nickname:
                    tier_counts["signals"] += 1
                elif "autopilot" in nickname:
                    tier_counts["autopilot"] += 1

            # Recent cancellations (last 30 days)
            since_30d = int((datetime.now() - timedelta(days=30)).timestamp())
            resp2 = requests.get(
                "https://api.stripe.com/v1/subscriptions",
                headers={"Authorization": f"Bearer {stripe_key}"},
                params={"status": "canceled", "created[gte]": since_30d, "limit": 100},
                timeout=15,
            )
            canceled = len(resp2.json().get("data", [])) if resp2.status_code == 200 else 0

            active = len(subs)
            churn_rate = canceled / max(active + canceled, 1) * 100

            return {
                "mrr": round(mrr, 2),
                "active_subscriptions": active,
                "signals_count": tier_counts["signals"],
                "autopilot_count": tier_counts["autopilot"],
                "canceled_30d": canceled,
                "churn_rate_pct": round(churn_rate, 1),
                "avg_revenue_per_user": round(mrr / max(active, 1), 2),
                "source": "stripe",
            }
        except Exception as e:
            logger.warning(f"[analytics] Stripe fetch failed: {e}")
            return self._estimate_revenue()

    def _estimate_revenue(self) -> dict:
        """Fallback: estimate from leads data."""
        leads = self._load_leads()
        signals = sum(1 for l in leads if l.get("tier") == "signals")
        autopilot = sum(1 for l in leads if l.get("tier") == "autopilot")
        mrr = signals * 49 + autopilot * 199
        return {
            "mrr": mrr,
            "active_subscriptions": signals + autopilot,
            "signals_count": signals,
            "autopilot_count": autopilot,
            "canceled_30d": 0,
            "churn_rate_pct": 0,
            "avg_revenue_per_user": round(mrr / max(signals + autopilot, 1), 2),
            "source": "estimated",
        }

    def _fetch_trading_metrics(self) -> dict:
        try:
            if REPORT_STATE.exists():
                data = json.loads(REPORT_STATE.read_text())
                reports = data.get("reports", [])
                if not reports:
                    return {}

                total_pnl = sum(r.get("daily_pnl", {}).get("total", 0) for r in reports)
                total_fills = sum(r.get("fills_today", 0) for r in reports)
                win_days = sum(1 for r in reports if r.get("daily_pnl", {}).get("total", 0) > 0)
                latest = reports[0]

                return {
                    "days_tracked": len(reports),
                    "cumulative_pnl": round(total_pnl, 2),
                    "total_trades": total_fills,
                    "win_days_pct": round(win_days / max(len(reports), 1) * 100, 1),
                    "latest_balance": latest.get("total_balance", 0),
                    "latest_sol_price": latest.get("sol_price", 0),
                    "today_pnl": latest.get("daily_pnl", {}).get("total", 0),
                }
        except Exception:
            pass
        return {}

    def _fetch_funnel_metrics(self) -> dict:
        leads = self._load_leads()
        tiers = {}
        for lead in leads:
            tier = lead.get("tier", "free")
            tiers[tier] = tiers.get(tier, 0) + 1

        total = len(leads)
        free = tiers.get("free", 0)
        signals = tiers.get("signals", 0)
        autopilot = tiers.get("autopilot", 0)
        academy = tiers.get("academy", 0)

        return {
            "total_leads": total,
            "free": free,
            "signals": signals,
            "autopilot": autopilot,
            "academy": academy,
            "free_to_signals_pct": round(signals / max(free + signals, 1) * 100, 1),
            "signals_to_autopilot_pct": round(autopilot / max(signals + autopilot, 1) * 100, 1),
        }

    def _calculate_health_score(self, revenue: dict, trading: dict, funnel: dict) -> dict:
        """0-100 business health score."""
        score = 50  # baseline
        reasons = []

        # MRR component (0-30 points)
        mrr = revenue.get("mrr", 0)
        if mrr >= 5000:
            score += 30
            reasons.append("MRR above $5K target")
        elif mrr >= 1000:
            score += 20
            reasons.append(f"MRR ${mrr} — growing")
        elif mrr > 0:
            score += 10
            reasons.append(f"MRR ${mrr} — early stage")
        else:
            reasons.append("No revenue yet")

        # Churn component (-20 to +10)
        churn = revenue.get("churn_rate_pct", 0)
        if churn == 0:
            score += 10
        elif churn < 5:
            score += 5
        elif churn > 15:
            score -= 20
            reasons.append(f"High churn: {churn}%")
        elif churn > 10:
            score -= 10
            reasons.append(f"Elevated churn: {churn}%")

        # Trading performance (-10 to +10)
        win_pct = trading.get("win_days_pct", 0)
        if win_pct > 70:
            score += 10
            reasons.append(f"Strong trading: {win_pct}% win days")
        elif win_pct < 50:
            score -= 10
            reasons.append(f"Weak trading: {win_pct}% win days")

        # Funnel health (0-10)
        conversion = funnel.get("free_to_signals_pct", 0)
        if conversion > 10:
            score += 10
            reasons.append(f"Great conversion: {conversion}%")
        elif conversion > 5:
            score += 5

        score = max(0, min(100, score))
        grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D" if score >= 20 else "F"

        return {"score": score, "grade": grade, "reasons": reasons}

    def _generate_ceo_briefing(self, kpi: dict) -> str:
        rev = kpi.get("revenue", {})
        trade = kpi.get("trading", {})
        funnel = kpi.get("funnel", {})
        health = kpi.get("health_score", {})

        today = datetime.now().strftime("%Y-%m-%d")

        md = f"""# CEO Daily Briefing — {today}
## Health: {health.get('grade', '?')} ({health.get('score', 0)}/100)
{chr(10).join(f'- {r}' for r in health.get('reasons', []))}

## Revenue
| Metric | Value |
|--------|-------|
| MRR | ${rev.get('mrr', 0):,.2f} |
| Active Subs | {rev.get('active_subscriptions', 0)} |
| Signals | {rev.get('signals_count', 0)} x $49 |
| Autopilot | {rev.get('autopilot_count', 0)} x $199 |
| Churn (30d) | {rev.get('churn_rate_pct', 0)}% |
| ARPU | ${rev.get('avg_revenue_per_user', 0):.2f} |

## Trading
| Metric | Value |
|--------|-------|
| Today PnL | ${trade.get('today_pnl', 0):+.2f} |
| Cumulative | ${trade.get('cumulative_pnl', 0):+.2f} |
| Win Days | {trade.get('win_days_pct', 0)}% |
| Total Trades | {trade.get('total_trades', 0)} |
| Balance | ${trade.get('latest_balance', 0):,.2f} |

## Funnel
| Stage | Count | Conversion |
|-------|-------|------------|
| Free | {funnel.get('free', 0)} | — |
| Signals | {funnel.get('signals', 0)} | {funnel.get('free_to_signals_pct', 0)}% |
| Autopilot | {funnel.get('autopilot', 0)} | {funnel.get('signals_to_autopilot_pct', 0)}% |
| Academy | {funnel.get('academy', 0)} | — |

## Action Items
"""
        # Auto-generated action items
        actions = []
        if rev.get("mrr", 0) == 0:
            actions.append("PRIORITY: Get first paying customer. Focus all marketing on social proof.")
        if rev.get("churn_rate_pct", 0) > 10:
            actions.append("HIGH: Churn above 10%. Survey canceled users. Improve onboarding.")
        if funnel.get("free_to_signals_pct", 0) < 5 and funnel.get("free", 0) > 10:
            actions.append("MEDIUM: Low conversion. A/B test pricing page. Add urgency.")
        if trade.get("win_days_pct", 0) < 60:
            actions.append("MEDIUM: Trading performance dipping. Review grid parameters.")
        if not actions:
            actions.append("All metrics healthy. Continue current strategy.")

        for a in actions:
            md += f"- {a}\n"

        return md

    def _check_alerts(self, kpi: dict) -> list:
        alerts = []
        rev = kpi.get("revenue", {})
        health = kpi.get("health_score", {})

        if rev.get("churn_rate_pct", 0) > 15:
            alerts.append("CHURN_CRITICAL")
        if health.get("score", 50) < 30:
            alerts.append("HEALTH_LOW")

        # Revenue milestones
        mrr = rev.get("mrr", 0)
        milestones = [100, 500, 1000, 5000, 10000]
        last_milestone = self.state.get("last_revenue_milestone", 0)
        for m in milestones:
            if mrr >= m and last_milestone < m:
                alerts.append(f"MILESTONE_MRR_{m}")
                self.state["last_revenue_milestone"] = m

        return alerts

    def _load_leads(self) -> list:
        if LEADS_FILE.exists():
            try:
                return json.loads(LEADS_FILE.read_text())
            except Exception:
                pass
        return []
