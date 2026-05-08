"""
iBitLabs Content Agent — Generate X posts from today's trading data
Run via Claude Code: /post-today

Reads trade history from the database, generates storytelling tweets,
and posts them to X via twitter_poster._send_tweet().
"""

import os
import json
import sqlite3
import time
from datetime import datetime, timedelta

START_DATE = datetime(2026, 4, 7)
STARTING_CAPITAL = 1000.0


def day_count() -> int:
    return max(1, (datetime.now() - START_DATE).days + 1)


def get_today_trades() -> list:
    """Read today's completed trades from the database."""
    db_path = os.path.join(os.path.dirname(__file__), "sol_sniper.db")
    if not os.path.exists(db_path):
        return []

    today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM trade_log WHERE timestamp >= ? ORDER BY timestamp",
            (today_start,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_balance() -> float:
    """Get current balance from state or dashboard."""
    try:
        state_path = os.path.join(os.path.dirname(__file__), "sol_sniper_state.json")
        if os.path.exists(state_path):
            with open(state_path) as f:
                state = json.load(f)
                if state.get("position") and state["position"].get("margin"):
                    return float(state["position"]["margin"])
    except Exception:
        pass
    return 0.0


def get_experiment_summary() -> dict:
    """Get a full summary for content generation."""
    db_path = os.path.join(os.path.dirname(__file__), "sol_sniper.db")
    summary = {
        "day": day_count(),
        "starting_capital": STARTING_CAPITAL,
        "today_trades": get_today_trades(),
    }

    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            # All trades since start
            start_ts = START_DATE.timestamp()
            rows = conn.execute(
                "SELECT * FROM trade_log WHERE timestamp >= ? ORDER BY timestamp",
                (start_ts,)
            ).fetchall()
            summary["total_trade_rows"] = len(rows)
        except Exception:
            pass
        finally:
            conn.close()

    return summary


def post_to_x(text: str):
    """Post a tweet using the existing OAuth 2.0 setup."""
    # Import here to avoid circular deps
    from twitter_poster import _send_tweet
    _send_tweet(text)
    print(f"[POSTED TO X] {text[:80]}...")


def draft_posts(trades_data: str) -> str:
    """
    Returns a prompt/context string that Claude Code can use
    to generate posts. Called by the /post-today skill.
    """
    summary = get_experiment_summary()
    day = summary["day"]
    trades = summary["today_trades"]

    context = f"""=== iBitLabs Experiment — Day {day} ===
Starting capital: $1,000
Today's date: {datetime.now().strftime('%B %d, %Y')}

Today's trades from database:
"""
    if trades:
        for t in trades:
            context += f"  - {t}\n"
    else:
        context += "  (no completed trades today)\n"

    context += f"""
Additional data provided:
{trades_data}

---
Generate 1-2 tweets for X as Bonny (first person, casual, honest).
Max 260 chars each (before the URL line).
End each with "ibitlabs.com" on its own line.
No emojis mid-sentence. Be real — if it was a loss, own it.
"""
    return context
