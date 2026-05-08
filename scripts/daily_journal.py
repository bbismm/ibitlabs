#!/usr/bin/env python3
"""
Daily Lab Journal Generator
Runs at 23:55 local time, generates experiment diary for the day.
Pulls real data from sol_sniper.db + git log.
"""

import os
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "sol_sniper.db"
JOURNAL_DIR = BASE_DIR / "lab-journal"
LOG_FILE = BASE_DIR / "sol_sniper.log"


def get_today():
    return datetime.now().strftime("%Y-%m-%d")


def query_db(sql, params=()):
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_trades(date_str):
    """Get all trades for a specific date"""
    return query_db("""
        SELECT id, side, ROUND(price, 2) as price, ROUND(quantity, 4) as qty,
               ROUND(usdt_value, 2) as value, ROUND(pnl, 4) as pnl,
               datetime(timestamp, 'unixepoch', 'localtime') as time
        FROM trade_log
        WHERE date(timestamp, 'unixepoch', 'localtime') = ?
        ORDER BY timestamp
    """, (date_str,))


def get_daily_stats(date_str):
    """Get aggregated stats for the day"""
    rows = query_db("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END) as opens,
            ROUND(SUM(pnl), 2) as daily_pnl,
            ROUND(SUM(CASE WHEN side LIKE 'GRID%' AND pnl != 0 THEN pnl ELSE 0 END), 2) as grid_pnl,
            ROUND(SUM(CASE WHEN side IN ('BUY','SELL') AND pnl != 0 THEN pnl ELSE 0 END), 2) as sniper_pnl
        FROM trade_log
        WHERE date(timestamp, 'unixepoch', 'localtime') = ?
    """, (date_str,))
    return rows[0] if rows else {}


def get_cumulative_pnl():
    """Get total PnL across all time"""
    rows = query_db("SELECT ROUND(SUM(pnl), 2) as total FROM trade_log")
    return rows[0]["total"] if rows else 0


def get_side_breakdown(date_str):
    """Get breakdown by trade side"""
    return query_db("""
        SELECT side, COUNT(*) as cnt, ROUND(SUM(pnl), 4) as pnl
        FROM trade_log
        WHERE date(timestamp, 'unixepoch', 'localtime') = ?
        GROUP BY side ORDER BY side
    """, (date_str,))


def get_git_changes(date_str):
    """Get git commits from today"""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"--since={date_str} 00:00", f"--until={date_str} 23:59"],
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=10
        )
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except Exception:
        return []


def get_recent_log_events(date_str, max_lines=500):
    """Extract key events from sol_sniper.log"""
    events = {"opens": 0, "closes": 0, "grid_fills": 0, "grid_tp": 0,
              "sl": 0, "tp": 0, "trailing": 0, "timeout": 0,
              "handoff_skipped": 0, "cooldown": 0, "circuit_breaker": 0}

    log_path = BASE_DIR / "logs" / "sniper_launchd_err.log"
    if not log_path.exists():
        log_path = LOG_FILE
    if not log_path.exists():
        return events

    try:
        with open(log_path, "r") as f:
            # Read last N lines efficiently
            lines = f.readlines()
            for line in lines[-5000:]:
                if date_str not in line:
                    continue
                if "SNIPER FILLED" in line or "PAPER] Open" in line:
                    events["opens"] += 1
                elif "SNIPER CLOSE" in line or "PAPER] Close" in line:
                    events["closes"] += 1
                    if "TP +" in line:
                        events["tp"] += 1
                    elif "SL " in line:
                        events["sl"] += 1
                    elif "TRAIL" in line or "Trailing" in line:
                        events["trailing"] += 1
                    elif "TIMEOUT" in line or "Timeout" in line:
                        events["timeout"] += 1
                elif "[GRID] BUY level" in line or "[GRID] SELL level" in line:
                    events["grid_fills"] += 1
                elif "[GRID] TP" in line:
                    events["grid_tp"] += 1
                elif "Handoff skipped" in line:
                    events["handoff_skipped"] += 1
                elif "Post-TP cooldown" in line or "cooldown" in line.lower():
                    events["cooldown"] += 1
                elif "CIRCUIT BREAKER" in line:
                    events["circuit_breaker"] += 1
    except Exception:
        pass

    return events


def generate_journal(date_str):
    stats = get_daily_stats(date_str)
    trades = get_daily_trades(date_str)
    sides = get_side_breakdown(date_str)
    cumulative = get_cumulative_pnl()
    commits = get_git_changes(date_str)
    events = get_recent_log_events(date_str)

    total = stats.get("total", 0)
    wins = stats.get("wins", 0) or 0
    losses = stats.get("losses", 0) or 0
    opens = stats.get("opens", 0) or 0
    daily_pnl = stats.get("daily_pnl", 0) or 0
    grid_pnl = stats.get("grid_pnl", 0) or 0
    sniper_pnl = stats.get("sniper_pnl", 0) or 0

    # Build markdown
    lines = []
    lines.append(f"# Lab Journal — {date_str}")
    lines.append("")

    # Day summary
    if total == 0:
        lines.append("## Summary")
        lines.append("")
        lines.append("No trades today.")
        lines.append("")
    else:
        lines.append("## Daily Stats")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Daily PnL | **${daily_pnl:+.2f}** |")
        lines.append(f"| Cumulative PnL | ${cumulative:+.2f} |")
        lines.append(f"| Total records | {total} ({opens} opens, {wins}W / {losses}L) |")
        lines.append(f"| Sniper PnL | ${sniper_pnl:+.2f} |")
        lines.append(f"| Grid PnL | ${grid_pnl:+.2f} |")
        lines.append("")

        # Exit reasons from log
        if any(events[k] for k in ("tp", "sl", "trailing", "timeout")):
            lines.append("### Exit Reasons")
            lines.append("")
            if events["tp"]:
                lines.append(f"- Take profit: {events['tp']}")
            if events["trailing"]:
                lines.append(f"- Trailing stop: {events['trailing']}")
            if events["sl"]:
                lines.append(f"- Stop loss: {events['sl']}")
            if events["timeout"]:
                lines.append(f"- Timeout: {events['timeout']}")
            lines.append("")

        # V3.4 feature tracking
        if events["handoff_skipped"] or events["cooldown"]:
            lines.append("### V3.4 Features Triggered")
            lines.append("")
            if events["handoff_skipped"]:
                lines.append(f"- Grid loss protection (handoff skipped): {events['handoff_skipped']}x")
            if events["cooldown"]:
                lines.append(f"- Post-TP cooldown activated: {events['cooldown']}x")
            if events["circuit_breaker"]:
                lines.append(f"- Circuit breaker: {events['circuit_breaker']}x")
            lines.append("")

        # Trade summary (no specific prices/sides — protect strategy IP)
        lines.append("### Trade Summary")
        lines.append("")
        closes = [t for t in trades if t["pnl"] != 0]
        if closes:
            best = max(closes, key=lambda t: t["pnl"])
            worst = min(closes, key=lambda t: t["pnl"])
            lines.append(f"- Completed trades: {len(closes)}")
            lines.append(f"- Best trade: ${best['pnl']:+.2f}")
            lines.append(f"- Worst trade: ${worst['pnl']:+.2f}")
        lines.append(f"- Open positions logged: {len(trades) - len(closes)}")
        lines.append("")

    # Git changes
    if commits:
        lines.append("## Code Changes")
        lines.append("")
        for c in commits:
            lines.append(f"- `{c}`")
        lines.append("")

    # Observations section (always present, to be filled manually)
    lines.append("## Observations")
    lines.append("")
    lines.append("<!-- Fill in: What worked? What didn't? Any patterns? -->")
    lines.append("")

    # Open questions
    lines.append("## Open Questions")
    lines.append("")
    lines.append("<!-- Fill in: What needs follow-up tomorrow? -->")
    lines.append("")

    lines.append("---")
    lines.append(f"*Auto-generated at {datetime.now().strftime('%Y-%m-%d %H:%M')}. Edit to add analysis.*")
    lines.append("")

    return "\n".join(lines)


def main():
    today = get_today()
    JOURNAL_DIR.mkdir(exist_ok=True)

    journal_path = JOURNAL_DIR / f"{today}.md"

    # Don't overwrite if already exists (manual edits preserved)
    if journal_path.exists():
        print(f"Journal already exists: {journal_path}")
        print("Appending updated stats as addendum...")
        content = generate_journal(today)
        with open(journal_path, "a") as f:
            f.write(f"\n\n---\n\n## End-of-Day Update (auto-generated)\n\n")
            # Only append the stats section
            in_stats = False
            for line in content.split("\n"):
                if line.startswith("## Daily Stats"):
                    in_stats = True
                elif line.startswith("## Observations"):
                    in_stats = False
                if in_stats:
                    f.write(line + "\n")
        print(f"Updated: {journal_path}")
    else:
        content = generate_journal(today)
        with open(journal_path, "w") as f:
            f.write(content)
        print(f"Generated: {journal_path}")

    # Auto-commit
    try:
        subprocess.run(
            ["git", "add", str(journal_path)],
            cwd=str(BASE_DIR), timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", f"Lab journal: {today} (auto-generated)"],
            cwd=str(BASE_DIR), timeout=10
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(BASE_DIR), timeout=30
        )
        print("Pushed to GitHub")
    except Exception as e:
        print(f"Git push failed: {e}")


if __name__ == "__main__":
    main()
