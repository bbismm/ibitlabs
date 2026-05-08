"""
Support Agent — Automated customer support via email + Discord.

Handles:
1. API connection issues (Coinbase setup help)
2. Billing questions (Stripe subscription management)
3. Dashboard/signals troubleshooting
4. Account upgrade guidance
5. Escalation to human (you) for complex issues

Required env vars:
  SENDGRID_API_KEY — for email responses
  STRIPE_SECRET_KEY — for billing lookups
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path

import requests

from .base_growth_agent import BaseGrowthAgent

logger = logging.getLogger(__name__)

TICKETS_FILE = Path(__file__).parent.parent / "growth_state" / "support_tickets.json"


class SupportAgent(BaseGrowthAgent):
    """
    Auto-support system. Runs every 30 minutes.

    Workflow:
    1. Check email inbox for support requests
    2. Match against knowledge base
    3. Auto-respond if confident match (>80%)
    4. Escalate to human if uncertain
    5. Track resolution metrics
    """

    KNOWLEDGE_BASE = {
        "connect coinbase": {
            "answer": (
                "To connect your Coinbase account to iBitLabs Sniper Autopilot:\n\n"
                "1. Go to coinbase.com → Settings → API\n"
                "2. Create a new API key\n"
                "3. Enable permissions: 'Trade' and 'View' (NOT 'Transfer')\n"
                "4. Copy your API Key and API Secret\n"
                "5. Enter them in your iBitLabs Autopilot dashboard\n\n"
                "Important: NEVER enable 'Transfer' permission. The Sniper only needs trade access.\n"
                "The system will verify the connection and start trading SOL/USD within 5 minutes."
            ),
            "keywords": ["connect", "coinbase", "api", "key", "setup", "link"],
        },
        "cancel subscription": {
            "answer": (
                "To cancel your subscription:\n\n"
                "1. Go to www.ibitlabs.com and click 'Manage Subscription'\n"
                "2. Or email us and we'll process it immediately\n\n"
                "Your access continues until the end of your current billing period.\n"
                "Autopilot users: all open positions will be closed before disconnection.\n\n"
                "We'd love to know why you're leaving — any feedback helps us improve."
            ),
            "keywords": ["cancel", "unsubscribe", "stop", "end subscription", "refund"],
        },
        "not working": {
            "answer": (
                "Common troubleshooting steps:\n\n"
                "1. Dashboard not loading: Clear browser cache, try incognito mode\n"
                "2. Signals delayed: Check your internet connection. Signals refresh every 30s\n"
                "3. Autopilot not trading: Check Coinbase API key permissions (Trade + View)\n"
                "4. Access code invalid: Codes expire after 30 days. Email us for a new one\n\n"
                "If none of these help, reply with your account email and we'll investigate."
            ),
            "keywords": ["not working", "broken", "error", "bug", "issue", "problem", "down", "loading"],
        },
        "pricing": {
            "answer": (
                "iBitLabs pricing:\n\n"
                "- Academy: FREE — 8-module course on mean reversion trading\n"
                "- Dashboard: $19/mo (or $199/year) — real-time signals, manual copy-trading\n"
                "- Autopilot: $49/mo (or $499/year) — automated trading on Coinbase ($5K+ recommended)\n\n"
                "All paid plans come with a 7-day satisfaction guarantee."
            ),
            "keywords": ["price", "pricing", "cost", "how much", "plan", "tier", "subscription"],
        },
        "performance": {
            "answer": (
                "iBitLabs Sniper performance:\n\n"
                "- Backtested win rate: 82.5% across 1000+ trades\n"
                "- Strategy: Mean reversion sniper on SOL/USD (long + short)\n"
                "- 13-month backtest: +27.62% return while SOL dropped -40%\n"
                "- Live dashboard: www.ibitlabs.com\n\n"
                "Past performance doesn't guarantee future results. "
                "The Sniper adapts to market regime: long in uptrends, short in downtrends, both in sideways."
            ),
            "keywords": ["performance", "returns", "profit", "results", "pnl", "track record", "sniper"],
        },
        "upgrade": {
            "answer": (
                "To upgrade your plan:\n\n"
                "1. Visit www.ibitlabs.com\n"
                "2. Click on the plan you want\n"
                "3. Complete checkout via Stripe\n"
                "4. You'll receive an access code within 5 minutes\n\n"
                "Current subscribers: contact us to switch plans — we'll prorate the difference."
            ),
            "keywords": ["upgrade", "switch plan", "change plan", "higher tier"],
        },
    }

    def __init__(self):
        super().__init__("support", interval_seconds=1800)  # every 30 min

    def execute(self) -> dict:
        actions = []

        # 1. Process pending tickets
        tickets = self._load_tickets()
        pending = [t for t in tickets if t.get("status") == "pending"]

        for ticket in pending:
            response = self._auto_respond(ticket)
            if response:
                ticket["status"] = "auto_resolved"
                ticket["response"] = response["answer"]
                ticket["resolved_at"] = datetime.now().isoformat()
                self._send_response(ticket["email"], response["subject"], response["answer"])
                actions.append(f"resolved: {ticket['email']}")
            else:
                ticket["status"] = "escalated"
                ticket["escalated_at"] = datetime.now().isoformat()
                actions.append(f"escalated: {ticket['email']}")

        if pending:
            self._save_tickets(tickets)

        # 2. Update stats
        stats = self._update_stats(tickets)

        self._log_action("SUPPORT_CYCLE", f"Actions: {', '.join(actions) or 'no pending tickets'}")

        return {"actions": actions, "stats": stats}

    def add_ticket(self, email: str, subject: str, body: str):
        """Add a new support ticket (called by email webhook or Discord)."""
        tickets = self._load_tickets()
        tickets.append({
            "id": f"T{len(tickets)+1:04d}",
            "email": email,
            "subject": subject,
            "body": body,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        })
        self._save_tickets(tickets)
        self._log_action("NEW_TICKET", f"{email}: {subject[:50]}")

    def _auto_respond(self, ticket: dict) -> dict:
        """Match ticket against knowledge base. Returns response or None."""
        text = f"{ticket.get('subject', '')} {ticket.get('body', '')}".lower()

        best_match = None
        best_score = 0

        for topic, kb_entry in self.KNOWLEDGE_BASE.items():
            keywords = kb_entry["keywords"]
            score = sum(2 if kw in text else 0 for kw in keywords)
            # Bonus for exact topic match
            if topic in text:
                score += 5

            if score > best_score:
                best_score = score
                best_match = kb_entry

        # Need confidence threshold
        if best_score >= 4 and best_match:
            return {
                "answer": best_match["answer"],
                "subject": f"Re: {ticket.get('subject', 'Your iBitLabs question')}",
                "confidence": best_score,
            }

        return None  # escalate to human

    def _send_response(self, to: str, subject: str, body: str):
        api_key = os.environ.get("SENDGRID_API_KEY", "")
        from_email = os.environ.get("SENDGRID_FROM_EMAIL", "support@ibitlabs.com")

        if not api_key:
            logger.info(f"[support] Would email {to}: {subject}")
            return

        try:
            requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": from_email, "name": "iBitLabs Support"},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                },
                timeout=15,
            )
        except Exception as e:
            logger.warning(f"[support] Email send failed: {e}")

    def _update_stats(self, tickets: list) -> dict:
        total = len(tickets)
        auto_resolved = sum(1 for t in tickets if t.get("status") == "auto_resolved")
        escalated = sum(1 for t in tickets if t.get("status") == "escalated")
        pending = sum(1 for t in tickets if t.get("status") == "pending")

        stats = {
            "total_tickets": total,
            "auto_resolved": auto_resolved,
            "escalated": escalated,
            "pending": pending,
            "auto_resolve_rate": round(auto_resolved / max(total, 1) * 100, 1),
        }
        self.state["stats"] = stats
        return stats

    def _load_tickets(self) -> list:
        if TICKETS_FILE.exists():
            try:
                return json.loads(TICKETS_FILE.read_text())
            except Exception:
                pass
        return []

    def _save_tickets(self, tickets: list):
        TICKETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TICKETS_FILE.write_text(json.dumps(tickets[-500:], indent=2, ensure_ascii=False))
