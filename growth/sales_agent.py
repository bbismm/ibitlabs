"""
Sales Agent — Automated conversion funnel & lead nurturing.

Tracks user journey: Free Dashboard → Signals ($49) → Autopilot ($199) → Academy ($299)
Auto-sends nurturing emails via SendGrid/Mailgun.
Monitors Stripe for new subscribers, churned users, and upgrade opportunities.

Required env vars:
  STRIPE_SECRET_KEY — for subscription data
  SENDGRID_API_KEY — for automated emails
  SENDGRID_FROM_EMAIL — sender address
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

LEADS_FILE = Path(__file__).parent.parent / "growth_state" / "leads.json"


class SalesAgent(BaseGrowthAgent):
    """
    Automated sales funnel:
    1. Track leads (email signups, free users)
    2. Drip email sequences (day 1, 3, 7, 14)
    3. Monitor Stripe for churn → win-back emails
    4. Identify upgrade opportunities → targeted offers
    5. Track conversion metrics
    """

    # Email templates for drip sequence
    DRIP_SEQUENCE = [
        {
            "day": 0,
            "subject": "Welcome to iBitLabs",
            "template": "welcome",
            "body": (
                "Welcome to iBitLabs!\n\n"
                "Start with our free Academy course at www.ibitlabs.com/academy — 8 modules on mean reversion trading.\n\n"
                "When you're ready to trade:\n"
                "- Dashboard ($19/mo): Real-time Sniper signals, copy-trade manually\n"
                "- Autopilot ($49/mo): Automated trading on your Coinbase ($5K+ recommended)\n\n"
                "— iBitLabs Team"
            ),
        },
        {
            "day": 3,
            "subject": "How iBitLabs made +$X this week",
            "template": "performance",
            "body": (
                "Quick update on iBitLabs Sniper performance:\n\n"
                "{performance_summary}\n\n"
                "This is what automated mean reversion looks like. No emotions. Just math.\n\n"
                "Dashboard subscribers ($19/mo) see these signals in real-time.\n\n"
                "Upgrade: www.ibitlabs.com\n\n"
                "— iBitLabs Team"
            ),
        },
        {
            "day": 7,
            "subject": "Why 82.5% win rate works",
            "template": "education",
            "body": (
                "You've been watching iBitLabs for a week now.\n\n"
                "Here's the math behind our 82.5% backtest win rate:\n\n"
                "1. SOL/USD ranges 70% of the time\n"
                "2. Grid trading profits from every bounce\n"
                "3. 5 AI monitors pause during trends (protecting capital)\n"
                "4. Mean reversion is the most reliable pattern in crypto\n\n"
                "The question isn't IF the strategy works — it's whether you want to trade it yourself or let us do it.\n\n"
                "Dashboard ($19/mo): See signals in real-time, copy-trade manually.\n"
                "Autopilot ($49/mo): We execute trades in your Coinbase account automatically.\n\n"
                "— iBitLabs Team"
            ),
        },
        {
            "day": 14,
            "subject": "Limited: Alpha Academy now available",
            "template": "academy_pitch",
            "body": (
                "After 2 weeks watching iBitLabs, you've seen the results.\n\n"
                "Ready to let the Sniper trade for you?\n\n"
                "Autopilot ($49/mo) connects to your Coinbase account and executes the same strategy automatically.\n"
                "Recommended for accounts with $5,000+.\n\n"
                "Or save with yearly: $499/year (save $89).\n\n"
                "Start: www.ibitlabs.com\n\n"
                "— iBitLabs Team"
            ),
        },
    ]

    WINBACK_EMAIL = {
        "subject": "We miss you — here's what you've been missing",
        "body": (
            "Hey,\n\n"
            "We noticed you cancelled your iBitLabs subscription.\n\n"
            "Since you left, we've made {pnl_since} in PnL with {trades_since} trades.\n\n"
            "We'd love to have you back. Reply to this email and we'll set you up with a free week.\n\n"
            "— iBitLabs Team"
        ),
    }

    def __init__(self):
        super().__init__("sales", interval_seconds=3600)  # every hour

    def execute(self) -> dict:
        actions = []

        # 1. Check Stripe for new subscribers
        new_subs = self._check_new_subscribers()
        if new_subs:
            actions.append(f"new_subscribers: {len(new_subs)}")
            for sub in new_subs:
                self._add_lead(sub["email"], source="stripe", tier=sub["tier"])

        # 2. Check Stripe for churned users
        churned = self._check_churned()
        if churned:
            actions.append(f"churned: {len(churned)}")
            for user in churned:
                self._send_winback(user)

        # 3. Run drip sequences
        drip_sent = self._process_drip_queue()
        if drip_sent:
            actions.append(f"drip_emails: {drip_sent}")

        # 4. Update conversion stats
        stats = self._update_stats()

        self._log_action("SALES_CYCLE", f"Actions: {', '.join(actions) or 'monitoring'}")

        return {"actions": actions, "stats": stats}

    def _add_lead(self, email: str, source: str = "organic", tier: str = "free"):
        leads = self._load_leads()
        # Check if exists
        for lead in leads:
            if lead["email"] == email:
                lead["tier"] = tier
                lead["updated"] = datetime.now().isoformat()
                self._save_leads(leads)
                return
        # New lead
        leads.append({
            "email": email,
            "source": source,
            "tier": tier,
            "joined": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
            "drip_step": 0,
            "last_drip": None,
        })
        self._save_leads(leads)
        self._log_action("NEW_LEAD", f"{email} ({source}, {tier})")

    def _process_drip_queue(self) -> int:
        leads = self._load_leads()
        sent = 0

        for lead in leads:
            step = lead.get("drip_step", 0)
            if step >= len(self.DRIP_SEQUENCE):
                continue

            drip = self.DRIP_SEQUENCE[step]
            joined = datetime.fromisoformat(lead["joined"])
            target_date = joined + timedelta(days=drip["day"])

            if datetime.now() >= target_date:
                last_drip = lead.get("last_drip")
                if last_drip:
                    last = datetime.fromisoformat(last_drip)
                    if (datetime.now() - last).total_seconds() < 86400:
                        continue  # max 1 email per day

                success = self._send_email(
                    to=lead["email"],
                    subject=drip["subject"],
                    body=drip["body"],
                )
                if success:
                    lead["drip_step"] = step + 1
                    lead["last_drip"] = datetime.now().isoformat()
                    sent += 1

        self._save_leads(leads)
        return sent

    def _send_winback(self, user: dict):
        email = user.get("email", "")
        if not email:
            return

        body = self.WINBACK_EMAIL["body"].format(
            pnl_since=user.get("pnl_since", "$0"),
            trades_since=user.get("trades_since", "0"),
        )
        self._send_email(email, self.WINBACK_EMAIL["subject"], body)
        self._log_action("WINBACK", f"Sent to {email}")

    def _send_email(self, to: str, subject: str, body: str) -> bool:
        """Send email via SendGrid API."""
        api_key = os.environ.get("SENDGRID_API_KEY", "")
        from_email = os.environ.get("SENDGRID_FROM_EMAIL", "alpha@ibitlabs.com")

        if not api_key:
            logger.info(f"[sales] Email queued (no SendGrid key): {to} — {subject}")
            self._queue_email(to, subject, body)
            return True  # queued counts as success

        try:
            resp = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": from_email, "name": "iBitLabs"},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                },
                timeout=15,
            )
            return resp.status_code in (200, 202)
        except Exception as e:
            logger.warning(f"[sales] Email failed: {e}")
            return False

    def _queue_email(self, to: str, subject: str, body: str):
        queue_file = Path(__file__).parent.parent / "growth_state" / "email_queue.json"
        queue = []
        if queue_file.exists():
            try:
                queue = json.loads(queue_file.read_text())
            except Exception:
                pass
        queue.append({
            "to": to,
            "subject": subject,
            "body": body[:200],
            "queued_at": datetime.now().isoformat(),
        })
        queue_file.write_text(json.dumps(queue[-100:], indent=2, ensure_ascii=False))

    def _check_new_subscribers(self) -> list:
        """Check Stripe for new subscriptions in the last hour."""
        stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if not stripe_key:
            return []

        try:
            since = int((datetime.now() - timedelta(hours=1)).timestamp())
            resp = requests.get(
                "https://api.stripe.com/v1/subscriptions",
                headers={"Authorization": f"Bearer {stripe_key}"},
                params={"created[gte]": since, "status": "active", "limit": 50},
                timeout=15,
            )
            if resp.status_code != 200:
                return []

            subs = resp.json().get("data", [])
            results = []
            for sub in subs:
                email = sub.get("customer_email", "") or ""
                plan = sub.get("plan", {}).get("nickname", "").lower()
                tier = "signals" if "signal" in plan else "autopilot" if "autopilot" in plan else "unknown"
                if email:
                    results.append({"email": email, "tier": tier})
            return results
        except Exception as e:
            logger.warning(f"[sales] Stripe check failed: {e}")
            return []

    def _check_churned(self) -> list:
        """Check Stripe for recent cancellations."""
        stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if not stripe_key:
            return []

        try:
            since = int((datetime.now() - timedelta(hours=24)).timestamp())
            resp = requests.get(
                "https://api.stripe.com/v1/subscriptions",
                headers={"Authorization": f"Bearer {stripe_key}"},
                params={"created[gte]": since, "status": "canceled", "limit": 50},
                timeout=15,
            )
            if resp.status_code != 200:
                return []

            subs = resp.json().get("data", [])
            return [
                {"email": s.get("customer_email", ""), "pnl_since": "$0", "trades_since": "0"}
                for s in subs if s.get("customer_email")
            ]
        except Exception:
            return []

    def _update_stats(self) -> dict:
        leads = self._load_leads()
        stats = {
            "total_leads": len(leads),
            "free": sum(1 for l in leads if l.get("tier") == "free"),
            "signals": sum(1 for l in leads if l.get("tier") == "signals"),
            "autopilot": sum(1 for l in leads if l.get("tier") == "autopilot"),
            "academy": sum(1 for l in leads if l.get("tier") == "academy"),
        }
        self.state["stats"] = stats
        return stats

    def _load_leads(self) -> list:
        if LEADS_FILE.exists():
            try:
                return json.loads(LEADS_FILE.read_text())
            except Exception:
                pass
        return []

    def _save_leads(self, leads: list):
        LEADS_FILE.write_text(json.dumps(leads, indent=2, ensure_ascii=False))
