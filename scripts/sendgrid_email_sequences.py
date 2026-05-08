#!/usr/bin/env python3
from __future__ import annotations
"""
iBitLabs — SendGrid Email Drip Sequences
==========================================
Manages automated email flows for user lifecycle:
  1. Welcome sequence (Day 0/1/3/7)
  2. Academy nudge (if not started after 3 days)
  3. Paid conversion (after 5+ lessons)
  4. Churn prevention (3 days before expiry)

Can run as:
  - Standalone cron job: checks all users and sends due emails
  - Imported module: call send_welcome_email() from registration handler

Setup:
  pip3 install requests
  Environment: SENDGRID_API_KEY, SENDER_EMAIL

Integration with Cloudflare Workers:
  - Call /api/email-trigger endpoint from registration function
  - Or run this script via cron to process the email queue

Usage:
  python3 sendgrid_email_sequences.py --process-queue     # Process all due emails
  python3 sendgrid_email_sequences.py --send-welcome user@example.com
  python3 sendgrid_email_sequences.py --dry-run --process-queue
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------- CONFIG ----------
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "hello@ibitlabs.com")
SENDER_NAME = "iBitLabs"

# KV state file (for standalone mode — in production this reads from Cloudflare KV)
EMAIL_STATE_FILE = Path(os.getenv("EMAIL_STATE_DIR", Path.home() / "ibitlabs")) / "email_state.json"

# URLs
WEBSITE = "https://ibitlabs.com"
DASHBOARD = "https://ibitlabs.com/signals"
ACADEMY = "https://ibitlabs.com/saga/en"
SIGNALS = "https://ibitlabs.com/signals"
ACCOUNT = "https://ibitlabs.com/account"

DRY_RUN = False


# ---------- EMAIL TEMPLATES ----------

WELCOME_SEQUENCE = {
    # Day 0: Immediate welcome
    0: {
        "subject": "Welcome to the experiment 🧪",
        "html": """
<div style="font-family: Inter, -apple-system, sans-serif; max-width: 600px; margin: 0 auto; background: #0d0d1a; color: #e2e8f0; padding: 40px 30px;">
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #8b5cf6; font-size: 24px; margin: 0;">iBitLabs</h1>
        <p style="color: #94a3b8; font-size: 14px;">Built by AI, created by Bonnybb</p>
    </div>

    <h2 style="color: #e2e8f0; font-size: 20px;">Welcome to the experiment.</h2>

    <p>Here's the short version: I can't code. Not a single line.</p>

    <p>But I've been in crypto since 2017. I survived every crash, every cycle.
    So I asked AI one question: <strong style="color: #8b5cf6;">can you build me a real trading system?</strong></p>

    <p>7 days later, it did. And now it's running with $1,000 of my own money — every trade recorded, every signal transparent.</p>

    <p>This is not financial advice. This is a social experiment. And you're now part of it.</p>

    <div style="background: #151530; border-radius: 12px; padding: 20px; margin: 25px 0;">
        <p style="margin: 0 0 10px; font-weight: bold; color: #8b5cf6;">Here's what you can do right now:</p>
        <p style="margin: 5px 0;">📊 <a href="{dashboard}" style="color: #a78bfa;">Watch the live dashboard</a> — real P&L, real trades</p>
        <p style="margin: 5px 0;">🎓 <a href="{academy}" style="color: #a78bfa;">Start the free Sniper Academy</a> — 13 lessons, zero cost</p>
        <p style="margin: 5px 0;">📱 <a href="https://t.me/ibitlabs_signal_bot" style="color: #a78bfa;">Connect Telegram</a> — get alerts when trades happen</p>
    </div>

    <p style="color: #94a3b8; font-size: 13px;">Welcome aboard.<br>— Bonnybb</p>
</div>
""".format(dashboard=DASHBOARD, academy=ACADEMY),
    },

    # Day 1: Academy intro
    1: {
        "subject": "13 free lessons. Zero fluff.",
        "html": """
<div style="font-family: Inter, -apple-system, sans-serif; max-width: 600px; margin: 0 auto; background: #0d0d1a; color: #e2e8f0; padding: 40px 30px;">
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #8b5cf6; font-size: 24px; margin: 0;">iBitLabs</h1>
    </div>

    <h2 style="color: #e2e8f0; font-size: 20px;">The Sniper Academy is free. Here's why.</h2>

    <p>Most "crypto courses" charge hundreds of dollars for recycled content. I'm not doing that.</p>

    <p>The Sniper Academy has 13 lessons covering everything from mean reversion to risk management — the same concepts the AI-built trading bot actually uses.</p>

    <p>Why free? Because this is an experiment. The more people who understand what the system does, the more interesting the experiment becomes.</p>

    <div style="text-align: center; margin: 30px 0;">
        <a href="{academy}" style="display: inline-block; background: #8b5cf6; color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">Start Learning →</a>
    </div>

    <p style="color: #94a3b8; font-size: 13px;">No upsell at the end. Just knowledge.<br>— Bonnybb</p>
</div>
""".format(academy=ACADEMY),
    },

    # Day 3: Social proof + dashboard
    3: {
        "subject": "Here's what happened since you joined",
        "html": """
<div style="font-family: Inter, -apple-system, sans-serif; max-width: 600px; margin: 0 auto; background: #0d0d1a; color: #e2e8f0; padding: 40px 30px;">
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #8b5cf6; font-size: 24px; margin: 0;">iBitLabs</h1>
    </div>

    <h2 style="color: #e2e8f0; font-size: 20px;">The bot has been trading. Here are the results.</h2>

    <p>Since you signed up, the Alpha Sniper has been running 24/7 on SOL/USD futures. Every trade is recorded. Every signal is transparent.</p>

    <p>Want to see exactly what happened?</p>

    <div style="text-align: center; margin: 30px 0;">
        <a href="{dashboard}" style="display: inline-block; background: #8b5cf6; color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">View Live Dashboard →</a>
    </div>

    <p>The dashboard shows real-time P&L, win rate, and complete trade history — all from $1,000 of real money.</p>

    <div style="background: #151530; border-radius: 12px; padding: 20px; margin: 25px 0;">
        <p style="margin: 0; color: #94a3b8; font-size: 13px;">💡 <strong style="color: #e2e8f0;">Tip:</strong> If you haven't started the <a href="{academy}" style="color: #a78bfa;">Sniper Academy</a> yet, Lesson 1 explains exactly how the mean reversion system works.</p>
    </div>

    <p style="color: #94a3b8; font-size: 13px;">— Bonnybb</p>
</div>
""".format(dashboard=DASHBOARD, academy=ACADEMY),
    },

    # Day 7: Soft pitch for paid signals
    7: {
        "subject": "Free vs. real-time signals — here's the difference",
        "html": """
<div style="font-family: Inter, -apple-system, sans-serif; max-width: 600px; margin: 0 auto; background: #0d0d1a; color: #e2e8f0; padding: 40px 30px;">
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #8b5cf6; font-size: 24px; margin: 0;">iBitLabs</h1>
    </div>

    <h2 style="color: #e2e8f0; font-size: 20px;">You've been watching. Here's what you're missing.</h2>

    <p>The free dashboard shows you what happened. The Alpha Signals show you what's happening <em>right now</em>.</p>

    <div style="background: #151530; border-radius: 12px; padding: 20px; margin: 25px 0;">
        <table style="width: 100%; color: #e2e8f0; font-size: 14px; border-collapse: collapse;">
            <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #1e1e3a;"></td>
                <td style="padding: 8px 0; border-bottom: 1px solid #1e1e3a; color: #94a3b8;">Free</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #1e1e3a; color: #8b5cf6;">Alpha ($19/mo)</td>
            </tr>
            <tr>
                <td style="padding: 8px 0;">Live P&L</td>
                <td style="padding: 8px 0;">✅</td>
                <td style="padding: 8px 0;">✅</td>
            </tr>
            <tr>
                <td style="padding: 8px 0;">Trade History</td>
                <td style="padding: 8px 0;">✅ (delayed)</td>
                <td style="padding: 8px 0;">✅ (real-time)</td>
            </tr>
            <tr>
                <td style="padding: 8px 0;">StochRSI + BB Signals</td>
                <td style="padding: 8px 0;">❌</td>
                <td style="padding: 8px 0;">✅</td>
            </tr>
            <tr>
                <td style="padding: 8px 0;">Grid Levels</td>
                <td style="padding: 8px 0;">❌</td>
                <td style="padding: 8px 0;">✅</td>
            </tr>
            <tr>
                <td style="padding: 8px 0;">Telegram Alerts</td>
                <td style="padding: 8px 0;">❌</td>
                <td style="padding: 8px 0;">✅</td>
            </tr>
            <tr>
                <td style="padding: 8px 0;">Entry Conditions</td>
                <td style="padding: 8px 0;">❌</td>
                <td style="padding: 8px 0;">✅</td>
            </tr>
        </table>
    </div>

    <p>This is not a hard sell. If you're learning from the Academy and watching the free dashboard, that's great — that's exactly what this experiment is for.</p>

    <p>But if you want to trade alongside the bot in real time, Alpha Signals gives you everything you need for $19/month.</p>

    <div style="text-align: center; margin: 30px 0;">
        <a href="{signals}" style="display: inline-block; background: #8b5cf6; color: white; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">See Alpha Signals →</a>
    </div>

    <p style="color: #94a3b8; font-size: 13px;">No pressure. The experiment continues either way.<br>— Bonnybb</p>
</div>
""".format(signals=SIGNALS),
    },
}

# Churn prevention email
CHURN_EMAIL = {
    "subject": "Your Alpha Signals access expires in 3 days",
    "html": """
<div style="font-family: Inter, -apple-system, sans-serif; max-width: 600px; margin: 0 auto; background: #0d0d1a; color: #e2e8f0; padding: 40px 30px;">
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #8b5cf6; font-size: 24px; margin: 0;">iBitLabs</h1>
    </div>

    <h2 style="color: #e2e8f0; font-size: 20px;">Your Alpha Signals access expires in 3 days.</h2>

    <p>Just a heads up — your subscription renews in 3 days. If you want to keep receiving real-time signals and Telegram alerts, no action needed.</p>

    <p>If you'd like to cancel or have any questions, you can manage your subscription from your account page.</p>

    <div style="text-align: center; margin: 30px 0;">
        <a href="{account}" style="display: inline-block; background: #151530; color: #8b5cf6; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px; border: 1px solid #8b5cf6;">Manage Account →</a>
    </div>

    <p style="color: #94a3b8; font-size: 13px;">Thanks for being part of the experiment.<br>— Bonnybb</p>
</div>
""".format(account=ACCOUNT),
}


# ---------- SENDGRID API ----------

def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send an email via SendGrid API."""
    if DRY_RUN:
        print(f"   📧 [DRY RUN] Would send to {to_email}: \"{subject}\"")
        return True

    if not SENDGRID_API_KEY:
        print(f"   ⚠️  SENDGRID_API_KEY not set. Skipping send to {to_email}")
        return False

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": SENDER_EMAIL, "name": SENDER_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_content}],
        "tracking_settings": {
            "click_tracking": {"enable": True},
            "open_tracking": {"enable": True},
        },
    }

    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if resp.status_code in (200, 202):
            print(f"   ✅ Email sent to {to_email}: \"{subject}\"")
            return True
        else:
            print(f"   ❌ SendGrid error {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"   ❌ Send failed: {e}")
        return False


# ---------- EMAIL STATE MANAGEMENT ----------

def load_email_state() -> dict:
    """Load the email state tracking file."""
    if EMAIL_STATE_FILE.exists():
        with open(EMAIL_STATE_FILE, "r") as f:
            return json.load(f)
    return {"users": {}}


def save_email_state(state: dict):
    """Save email state."""
    EMAIL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EMAIL_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def record_email_sent(state: dict, email: str, sequence: str, day: int):
    """Record that an email was sent."""
    if email not in state["users"]:
        state["users"][email] = {"emails_sent": [], "registered_at": datetime.now(timezone.utc).isoformat()}
    state["users"][email]["emails_sent"].append({
        "sequence": sequence,
        "day": day,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------- SEQUENCE PROCESSING ----------

def send_welcome_email(to_email: str):
    """Send the immediate welcome email (Day 0). Call from registration handler."""
    template = WELCOME_SEQUENCE[0]
    success = send_email(to_email, template["subject"], template["html"])

    if success:
        state = load_email_state()
        if to_email not in state["users"]:
            state["users"][to_email] = {
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "emails_sent": [],
            }
        record_email_sent(state, to_email, "welcome", 0)
        save_email_state(state)

    return success


def process_email_queue():
    """Check all users and send any due emails in their sequences."""
    state = load_email_state()
    now = datetime.now(timezone.utc)
    emails_sent = 0

    for email, user_data in state["users"].items():
        registered_at = datetime.fromisoformat(user_data["registered_at"])
        days_since_reg = (now - registered_at).days
        sent_days = {
            e["day"] for e in user_data.get("emails_sent", [])
            if e.get("sequence") == "welcome"
        }

        # Process welcome sequence
        for day, template in sorted(WELCOME_SEQUENCE.items()):
            if day in sent_days:
                continue  # Already sent
            if days_since_reg >= day:
                success = send_email(email, template["subject"], template["html"])
                if success:
                    record_email_sent(state, email, "welcome", day)
                    emails_sent += 1

    save_email_state(state)
    print(f"\n📬 Processed queue: {emails_sent} emails sent")
    return emails_sent


# ---------- CLOUDFLARE WORKER INTEGRATION ----------

def generate_worker_snippet():
    """Print a Cloudflare Worker snippet for triggering emails on registration."""
    snippet = '''
// === Add to your registration Cloudflare Function ===
// After successfully creating the user in KV, call this:

async function triggerWelcomeEmail(email, env) {
  try {
    const resp = await fetch("https://api.sendgrid.com/v3/mail/send", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.SENDGRID_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        personalizations: [{ to: [{ email }] }],
        from: { email: "hello@ibitlabs.com", name: "iBitLabs" },
        subject: "Welcome to the experiment 🧪",
        content: [{
          type: "text/html",
          value: WELCOME_EMAIL_HTML  // Import from a shared template
        }],
      }),
    });
    console.log(`Welcome email sent to ${email}: ${resp.status}`);
  } catch (err) {
    console.error(`Failed to send welcome email: ${err}`);
  }
}

// === Cron Trigger for drip sequences ===
// Add to wrangler.toml:
//   [triggers]
//   crons = ["0 9 * * *"]  # Run daily at 9am UTC
//
// In your worker's scheduled handler:
export default {
  async scheduled(event, env, ctx) {
    // Iterate KV users, check registration date, send due emails
    const userKeys = await env.REPLOT_REPORTS.list({ prefix: "user:" });
    for (const key of userKeys.keys) {
      const user = await env.REPLOT_REPORTS.get(key.name, "json");
      if (!user) continue;
      // Check which emails are due and send them
      await processUserEmails(user, env);
    }
  },
};
'''
    print(snippet)
    return snippet


# ---------- MAIN ----------

def main():
    global DRY_RUN

    parser = argparse.ArgumentParser(description="iBitLabs SendGrid Email Sequences")
    parser.add_argument("--process-queue", action="store_true", help="Process all due emails for all users.")
    parser.add_argument("--send-welcome", metavar="EMAIL", help="Send welcome email to a specific address.")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually send emails.")
    parser.add_argument("--show-worker-snippet", action="store_true", help="Print Cloudflare Worker integration code.")
    parser.add_argument("--show-state", action="store_true", help="Show current email state.")
    args = parser.parse_args()

    DRY_RUN = args.dry_run
    if DRY_RUN:
        print("🏷️  DRY RUN mode — no emails will be sent\n")

    if args.show_worker_snippet:
        generate_worker_snippet()
        return

    if args.show_state:
        state = load_email_state()
        print(json.dumps(state, indent=2))
        return

    if args.send_welcome:
        print(f"📧 Sending welcome email to {args.send_welcome}...")
        send_welcome_email(args.send_welcome)
        return

    if args.process_queue:
        print("📬 Processing email queue...")
        process_email_queue()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
