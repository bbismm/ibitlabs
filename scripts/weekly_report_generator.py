#!/usr/bin/env python3
from __future__ import annotations
"""
iBitLabs — Weekly Performance Report + OG Image Generator (v3)
================================================================
v3 (2026-05-03): rewritten to read directly from `sol_sniper.db` + the
authoritative `/api/live-status` endpoint. The v2 reader (`reports/2*.json`)
was broken: only two stale paper-trade JSONs from 2026-04-02/03 ever existed,
so weekly reports for W17–W19 reported $0 P&L / 0 fills / balance $1,894.68
while the actual account was at ~$980 with real activity. Live-status is the
same source the public dashboard and `/signals` use, so reports can no longer
diverge from what readers see on the website.

Generates:
  1. Multi-panel weekly chart (PNG)
  2. Dynamic OG share image (1200x630)
  3. Telegram Channel weekly summary
  4. Twitter copy

Usage:
  python3 weekly_report_generator.py [--dry-run]
  python3 weekly_report_generator.py --og-only
"""

import os
import sqlite3
import argparse
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------- CONFIG ----------
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "sol_sniper.db"
OUTPUT_DIR = BASE_DIR / "reports"
OG_DIR = BASE_DIR / "og_images"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@ibitlabs_sniper")
# Twitter automation paused 2026-04-22 (memory feedback_social_paused.md).
# Hard-disabled despite default "0" because prior runs hit the true branch
# anyway (env inheritance from somewhere). Set MOLTBOOK_FORCE_TWITTER=1 to
# explicitly re-enable when Bonny reactivates.
TWITTER_ENABLED = os.getenv("MOLTBOOK_FORCE_TWITTER", "0") == "1"
# Moltbook publishing — primary social surface post 2026-04-30.
MOLTBOOK_PUBLISHER = str(Path.home() / "scripts" / "moltbook_publish.py")
MOLTBOOK_KEYCHAIN_SERVICE = "ibitlabs-moltbook-agent"  # @ibitlabs_agent persona

STARTING_CAPITAL = 1000.0
LIVE_SINCE = "2026-04-07"
LIVE_STATUS_URL = "https://www.ibitlabs.com/api/live-status"

COLORS = {
    "bg": "#0d0d1a", "card_bg": "#151530",
    "purple": "#8b5cf6", "purple_light": "#a78bfa",
    "green": "#22c55e", "red": "#ef4444",
    "text": "#e2e8f0", "text_dim": "#94a3b8", "grid": "#1e1e3a",
}


# ---------- DATA LOADING ----------

def fetch_live_status(timeout: int = 10) -> dict | None:
    """Authoritative source for cumulative balance / PnL / fees / funding / WR."""
    try:
        resp = requests.get(LIVE_STATUS_URL, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️  live-status fetch failed: {e}")
        return None


def load_daily_pnl_series(db_path: Path, since_date: str) -> list[tuple[str, float, int, float]]:
    """
    Aggregate `trade_log` (closed round-trip rows) into per-day buckets since
    `since_date` (YYYY-MM-DD). Returns list of (date_str, day_pnl, day_trades, day_fees).
    """
    if not db_path.exists():
        return []
    since_ts = datetime.strptime(since_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    db = sqlite3.connect(str(db_path))
    rows = db.execute(
        """
        SELECT date(timestamp, 'unixepoch') AS d,
               ROUND(COALESCE(SUM(pnl), 0), 4) AS day_pnl,
               COUNT(*) AS day_trades,
               ROUND(COALESCE(SUM(fees), 0), 4) AS day_fees
        FROM trade_log
        WHERE timestamp >= ?
        GROUP BY d
        ORDER BY d
        """,
        (since_ts,),
    ).fetchall()
    db.close()
    return [(r[0], float(r[1] or 0), int(r[2] or 0), float(r[3] or 0)) for r in rows]


def get_week_dates(year: int, week: int) -> tuple[str, str]:
    """Get start (Monday) and end (Sunday) dates for an ISO week."""
    jan4 = datetime(year, 1, 4)
    start = jan4 + timedelta(weeks=week - 1, days=-jan4.weekday())
    end = start + timedelta(days=6)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def calculate_stats(daily_series: list[tuple[str, float, int, float]],
                    live: dict | None,
                    week_start: str, week_end: str) -> dict:
    """Build weekly + cumulative stats. Cumulative comes from live-status (authoritative);
    daily series + max-drawdown come from the DB."""

    week_rows = [r for r in daily_series if week_start <= r[0] <= week_end]

    w_pnl = sum(r[1] for r in week_rows)
    w_trades = sum(r[2] for r in week_rows)
    w_fees = sum(r[3] for r in week_rows)
    w_days_traded = len(week_rows)
    w_win_days = sum(1 for r in week_rows if r[1] > 0)

    # Cumulative — prefer live-status (matches the dashboard), fall back to DB sum
    if live:
        balance = float(live.get("balance", STARTING_CAPITAL))
        c_pnl = float(live.get("total_pnl", 0))
        c_realized = float(live.get("realized_delta", 0))
        c_fees = float(live.get("total_fees", 0))
        c_funding = float(live.get("funding_cost", 0))
        c_trades = int(live.get("total_trades", 0))
        c_win_rate = float(live.get("win_rate", 0))
        live_source = "live-status"
    else:
        c_realized = sum(r[1] for r in daily_series)
        c_pnl = c_realized
        c_fees = sum(r[3] for r in daily_series)
        c_funding = 0.0
        c_trades = sum(r[2] for r in daily_series)
        wins = sum(1 for r in daily_series if r[1] > 0)
        c_win_rate = (wins / len(daily_series) * 100) if daily_series else 0
        balance = STARTING_CAPITAL + c_pnl
        live_source = "db-fallback"

    c_total_days = len(daily_series)
    c_win_days = sum(1 for r in daily_series if r[1] > 0)

    # Max drawdown across the cumulative-realized curve from DB
    cum_vals = []
    running = 0.0
    for _, day_pnl, _, _ in daily_series:
        running += day_pnl
        cum_vals.append(running)
    peak = 0.0
    max_dd = 0.0
    for v in cum_vals:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    days_live = (datetime.now(timezone.utc).date() - datetime.strptime(LIVE_SINCE, "%Y-%m-%d").date()).days

    return {
        "week_pnl": w_pnl, "week_pnl_pct": (w_pnl / STARTING_CAPITAL) * 100,
        "week_fills": w_trades,
        "week_fees": w_fees,
        "week_days_traded": w_days_traded,
        "week_win_days": w_win_days,
        "week_loss_days": w_days_traded - w_win_days,
        "week_rows": week_rows,

        "cum_pnl": c_pnl, "cum_pnl_pct": (c_pnl / STARTING_CAPITAL) * 100,
        "cum_realized": c_realized,
        "cum_fees": c_fees,
        "cum_funding": c_funding,
        "carry_cost": c_fees + c_funding,
        "cum_trades": c_trades,
        "cum_win_rate": c_win_rate,
        "cum_win_days": c_win_days,
        "cum_total_days": c_total_days,
        "balance": balance,
        "max_drawdown": max_dd,
        "max_drawdown_pct": (max_dd / STARTING_CAPITAL) * 100,
        "days_live": days_live,
        "cum_vals": cum_vals,
        "live_source": live_source,
    }


# ---------- CHARTS ----------

def generate_charts(stats: dict, week_label: str) -> dict:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        print("⚠️  matplotlib not installed.")
        return {}

    C = COLORS
    outputs = {}

    # ===== WEEKLY REPORT (multi-panel) =====
    fig = plt.figure(figsize=(12, 8))
    fig.patch.set_facecolor(C["bg"])
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.3)

    def style(ax, title):
        ax.set_facecolor(C["card_bg"])
        ax.set_title(title, color=C["text"], fontsize=12, fontweight="bold", pad=10)
        ax.tick_params(colors=C["text_dim"], labelsize=9)
        for s in ax.spines.values():
            s.set_color(C["grid"])
        ax.grid(True, color=C["grid"], alpha=0.3)

    # Panel 1: Cumulative P&L
    ax1 = fig.add_subplot(gs[0, 0])
    style(ax1, "Cumulative P&L ($)")
    if stats["cum_vals"]:
        cv = stats["cum_vals"]
        color = C["green"] if cv[-1] >= 0 else C["red"]
        ax1.plot(range(len(cv)), cv, color=color, linewidth=2)
        ax1.fill_between(range(len(cv)), cv, alpha=0.1, color=color)
        ax1.axhline(y=0, color=C["grid"], linewidth=0.8, linestyle="--")
        ax1.set_xlabel("Day", color=C["text_dim"], fontsize=9)
    else:
        ax1.text(0.5, 0.5, "No closed trades yet", transform=ax1.transAxes,
                 ha="center", va="center", color=C["text_dim"])

    # Panel 2: This week's daily P&L bars
    ax2 = fig.add_subplot(gs[0, 1])
    style(ax2, "This Week's Daily P&L")
    if stats["week_rows"]:
        dates = [r[0][5:] for r in stats["week_rows"]]  # MM-DD
        vals = [r[1] for r in stats["week_rows"]]
        bar_colors = [C["green"] if v >= 0 else C["red"] for v in vals]
        ax2.bar(dates, vals, color=bar_colors, width=0.6)
        ax2.axhline(y=0, color=C["grid"], linewidth=0.8, linestyle="--")
    else:
        ax2.text(0.5, 0.5, "No closed trades this week", transform=ax2.transAxes,
                 ha="center", va="center", color=C["text_dim"])

    # Panel 3: Win/Loss days pie
    ax3 = fig.add_subplot(gs[1, 0])
    style(ax3, "Win Days vs Loss Days (cumulative)")
    if stats["cum_total_days"] > 0:
        sizes = [stats["cum_win_days"], stats["cum_total_days"] - stats["cum_win_days"]]
        if sum(sizes) > 0:
            ax3.pie(sizes, colors=[C["green"], C["red"]], startangle=90,
                    wedgeprops={"width": 0.3})
            pct = stats["cum_win_days"] / stats["cum_total_days"] * 100
            ax3.text(0, 0, f"{pct:.0f}%", ha="center", va="center",
                     color=C["text"], fontsize=20, fontweight="bold")

    # Panel 4: Key stats
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor(C["card_bg"])
    ax4.axis("off")
    for s in ax4.spines.values():
        s.set_color(C["grid"])

    lines = [
        f"Balance:        ${stats['balance']:,.2f}",
        f"Total P&L:      ${stats['cum_pnl']:+.2f} ({stats['cum_pnl_pct']:+.2f}%)",
        f"Realized:       ${stats['cum_realized']:+.2f}",
        f"Carry (fees+fund): -${stats['carry_cost']:.2f}",
        f"Max Drawdown:   ${stats['max_drawdown']:.2f} ({stats['max_drawdown_pct']:.1f}%)",
        f"Closed trades:  {stats['cum_trades']}  |  WR {stats['cum_win_rate']:.1f}%",
        f"Days Live:      {stats['days_live']}",
        f"",
        f"Week P&L:       ${stats['week_pnl']:+.2f} ({stats['week_pnl_pct']:+.2f}%)",
        f"Week trades:    {stats['week_fills']}",
        f"Week win days:  {stats['week_win_days']}/{stats['week_days_traded']}",
    ]
    ax4.text(0.05, 0.95, "\n".join(lines), transform=ax4.transAxes, va="top",
             color=C["text"], fontsize=10, family="monospace", linespacing=1.6)

    fig.suptitle(f"iBitLabs Weekly Report — {week_label}",
                 color=C["text"], fontsize=16, fontweight="bold", y=0.98)
    fig.text(0.98, 0.01, f"ibitlabs.com  •  source: {stats['live_source']}",
             ha="right", color=C["purple"], fontsize=9, alpha=0.6)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"weekly_{week_label}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    outputs["chart"] = path
    print(f"   📈 Weekly chart: {path}")

    # ===== OG IMAGE (1200x630) =====
    fig_og, ax_og = plt.subplots(figsize=(12, 6.3))
    fig_og.patch.set_facecolor(C["bg"])
    ax_og.set_facecolor(C["bg"])
    ax_og.axis("off")

    ax_og.text(0.5, 0.88, "iBitLabs — Alpha Sniper", transform=ax_og.transAxes,
               ha="center", color=C["purple_light"], fontsize=28, fontweight="bold")
    ax_og.text(0.5, 0.78, "AI-Built Crypto Trading System", transform=ax_og.transAxes,
               ha="center", color=C["text_dim"], fontsize=16)

    pnl_color = C["green"] if stats["cum_pnl"] >= 0 else C["red"]
    metrics = [
        ("Balance", f"${stats['balance']:,.2f}", pnl_color),
        ("Win Rate", f"{stats['cum_win_rate']:.1f}%", C["text"]),
        ("Total P&L", f"${stats['cum_pnl']:+.2f}", pnl_color),
        ("Days Live", f"{stats['days_live']}", C["text"]),
    ]
    for i, (label, value, color) in enumerate(metrics):
        x = 0.125 + i * 0.25
        ax_og.text(x, 0.52, value, transform=ax_og.transAxes,
                   ha="center", color=color, fontsize=24, fontweight="bold")
        ax_og.text(x, 0.42, label, transform=ax_og.transAxes,
                   ha="center", color=C["text_dim"], fontsize=12)

    if stats["cum_vals"]:
        inset = fig_og.add_axes([0.1, 0.05, 0.8, 0.28])
        inset.set_facecolor(C["bg"])
        cv = stats["cum_vals"]
        cc = C["green"] if cv[-1] >= 0 else C["red"]
        inset.plot(range(len(cv)), cv, color=cc, linewidth=2)
        inset.fill_between(range(len(cv)), cv, alpha=0.1, color=cc)
        inset.axhline(y=0, color=C["grid"], linewidth=0.5, linestyle="--")
        for s in inset.spines.values():
            s.set_visible(False)
        inset.tick_params(colors=C["text_dim"], labelsize=8)

    ax_og.text(0.5, 0.01, "www.ibitlabs.com  •  Built by AI, created by Bonnybb",
               transform=ax_og.transAxes, ha="center", color=C["purple"], fontsize=10, alpha=0.7)

    OG_DIR.mkdir(parents=True, exist_ok=True)
    og_path = OG_DIR / "og_latest.png"
    plt.savefig(og_path, dpi=100, bbox_inches="tight", facecolor=C["bg"])
    og_dated = OG_DIR / f"og_{week_label}.png"
    plt.savefig(og_dated, dpi=100, bbox_inches="tight", facecolor=C["bg"])
    plt.close()
    outputs["og"] = og_path
    print(f"   🖼️  OG image: {og_path}")

    return outputs


# ---------- FORMATTING ----------

def format_telegram(stats: dict, week_label: str) -> str:
    def esc(t):
        for c in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            t = t.replace(c, f"\\{c}")
        return t

    pnl_emoji = "🟢" if stats["week_pnl"] >= 0 else "🔴"
    cum_emoji = "🟢" if stats["cum_pnl"] >= 0 else "🔴"
    w_pnl = esc(f"{stats['week_pnl']:+.2f}")
    w_pct = esc(f"{stats['week_pnl_pct']:+.2f}")
    c_bal = esc(f"{stats['balance']:,.2f}")
    c_pnl = esc(f"{stats['cum_pnl']:+.2f}")
    c_pct = esc(f"{stats['cum_pnl_pct']:+.2f}")
    c_dd = esc(f"{stats['max_drawdown_pct']:.1f}")
    c_carry = esc(f"{stats['carry_cost']:.2f}")
    c_real = esc(f"{stats['cum_realized']:+.2f}")
    c_wr = esc(f"{stats['cum_win_rate']:.1f}")

    return (
        f"📊 *iBitLabs Weekly Report — {esc(week_label)}*\n\n"
        f"{pnl_emoji} *Week P&L: ${w_pnl}* \\({w_pct}%\\)\n"
        f"Closed trades: {stats['week_fills']}  \\|  "
        f"Win days: {stats['week_win_days']}/{stats['week_days_traded']}\n\n"
        f"📈 *Cumulative \\(since {esc(LIVE_SINCE)}\\)*\n"
        f"{cum_emoji} Balance: ${c_bal}\n"
        f"Total P&L: ${c_pnl} \\({c_pct}%\\)\n"
        f"Realized: ${c_real}  \\|  Carry: \\-${c_carry}\n"
        f"{stats['cum_trades']} trades  \\|  WR {c_wr}%  \\|  Max DD {c_dd}%\n"
        f"Days Live: {stats['days_live']}\n\n"
        f"_$1,000 real money\\. Fully transparent\\._\n\n"
        f"🔗 [Live Signals](https://ibitlabs.com/signals) \\| "
        f"[The Saga](https://ibitlabs.com/saga/en)"
    )


def format_twitter(stats: dict, week_label: str) -> str:
    ps = "+" if stats["week_pnl"] >= 0 else ""
    emoji = "🟢" if stats["week_pnl"] >= 0 else "🔴"
    # "AI built this. I can't code." dropped 2026-05-08 — out of step with
    # 2026-05-04 README rewrite framing. Public-record + co-builder is the
    # current voice (CLAUDE.md vision). Twitter is paused anyway.
    return (
        f"📊 Weekly Report — {week_label}\n\n"
        f"{emoji} Week: ${ps}{stats['week_pnl']:.2f} ({ps}{stats['week_pnl_pct']:.2f}%)\n"
        f"• {stats['week_fills']} closed trades\n"
        f"• Win days: {stats['week_win_days']}/{stats['week_days_traded']}\n\n"
        f"📈 Cumulative: ${stats['cum_pnl']:+.2f} ({stats['cum_pnl_pct']:+.2f}%)\n"
        f"• Balance: ${stats['balance']:,.2f}\n"
        f"• {stats['cum_trades']} trades, WR {stats['cum_win_rate']:.1f}%\n"
        f"• {stats['days_live']} days live\n\n"
        f"$1,000 → $10,000 in public. Receipts: ibitlabs.com/signals\n\n"
        f"#crypto #trading #SOL #buildinpublic"
    )


def format_moltbook(stats: dict, week_label: str, week_start: str, week_end: str) -> tuple[str, str]:
    """Returns (title, body) for the Moltbook weekly receipts post.

    Polanyi-respecting: first-person uncertainty, no bullet-point wisdom,
    receipts-centered narrative. Posts to s/general as @ibitlabs_agent.
    """
    ws_short = week_start[5:]  # MM-DD
    we_short = week_end[5:]

    title = f"Week {week_label} receipts"

    pnl_sign = "+" if stats["week_pnl"] >= 0 else ""
    cum_sign = "+" if stats["cum_pnl"] >= 0 else ""
    real_sign = "+" if stats["cum_realized"] >= 0 else ""

    body = (
        f"Week {week_label} receipts ({ws_short} → {we_short}):\n"
        f"\n"
        f"This week\n"
        f"  Closed trades: {stats['week_fills']}\n"
        f"  Net P&L:       ${pnl_sign}{stats['week_pnl']:.2f} ({pnl_sign}{stats['week_pnl_pct']:.2f}%)\n"
        f"  Win days:      {stats['week_win_days']}/{stats['week_days_traded']}\n"
        f"\n"
        f"Cumulative since 2026-04-07 ({stats['days_live']} days live)\n"
        f"  Balance:    ${stats['balance']:,.2f}\n"
        f"  Total P&L:  ${cum_sign}{stats['cum_pnl']:.2f} ({cum_sign}{stats['cum_pnl_pct']:.2f}%)\n"
        f"  Realized:   ${real_sign}{stats['cum_realized']:.2f}\n"
        f"  Carry cost: -${stats['carry_cost']:.2f} (fees + funding)\n"
        f"  Trades:     {stats['cum_trades']}, WR {stats['cum_win_rate']:.1f}%\n"
        f"  Max DD:     {stats['max_drawdown_pct']:.1f}%\n"
        f"\n"
        f"$1,000 → $10,000 in public. Every trade ID is on /signals; the "
        f"chart attached on the Telegram channel is generated from the same "
        f"SQLite DB the bot writes to. The numbers above are what stayed "
        f"after the week was over — what didn't is also visible by diff.\n"
        f"\n"
        f"Full chart + per-trade detail: https://ibitlabs.com/signals"
    )
    return title, body


def _moltbook_api_key() -> str:
    """Fetch @ibitlabs_agent API key from macOS Keychain. Empty on failure."""
    try:
        import subprocess
        return subprocess.check_output(
            ["security", "find-generic-password",
             "-s", MOLTBOOK_KEYCHAIN_SERVICE, "-a", "ibitlabs", "-w"],
            text=True, timeout=5,
        ).strip()
    except Exception as e:
        print(f"   ⚠️  Keychain fetch failed: {e}")
        return ""


def publish_moltbook(title: str, body: str) -> None:
    import subprocess
    import tempfile

    api_key = _moltbook_api_key()
    if not api_key:
        print("   ⚠️  Moltbook skipped — no API key from Keychain")
        return

    # Write to temp files since the publisher uses --title-file/--body-file
    title_path = body_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
            tf.write(title)
            title_path = tf.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
            tf.write(body)
            body_path = tf.name

        result = subprocess.run(
            ["python3", MOLTBOOK_PUBLISHER,
             "--title-file", title_path,
             "--body-file", body_path,
             "--submolt", "general",
             "--api-key", api_key],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode == 0:
            print("   ✅ Moltbook posted")
            # Surface the URL if present in stdout
            for line in result.stdout.splitlines():
                if "moltbook.com/post/" in line:
                    print(f"      {line.strip()}")
                    break
        else:
            print(f"   ❌ Moltbook failed (exit {result.returncode}): {result.stderr[:300]}")
    except Exception as e:
        print(f"   ❌ Moltbook exception: {e}")
    finally:
        for p in (title_path, body_path):
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass


# ---------- TELEGRAM ----------

def send_telegram(text: str, photo: Path | None = None):
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️  No TELEGRAM_BOT_TOKEN")
        return
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        if photo and photo.exists():
            with open(photo, "rb") as p:
                r = requests.post(f"{base}/sendPhoto",
                    data={"chat_id": TELEGRAM_CHANNEL_ID, "caption": text, "parse_mode": "MarkdownV2"},
                    files={"photo": p}, timeout=30)
        else:
            r = requests.post(f"{base}/sendMessage",
                json={"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "MarkdownV2"},
                timeout=30)
        print(f"   {'✅' if r.status_code == 200 else '❌'} Telegram: {r.status_code}")
        if r.status_code != 200:
            print(f"      {r.text[:300]}")
    except Exception as e:
        print(f"   ❌ {e}")


# ---------- MAIN ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--og-only", action="store_true")
    parser.add_argument("--week", help="Override ISO week as YYYY-Www (e.g. 2026-W19)")
    args = parser.parse_args()

    if args.week:
        year_str, week_str = args.week.split("-W")
        year, week = int(year_str), int(week_str)
    else:
        # Report on the week that JUST ENDED. Find the most recent Sunday
        # (in UTC, ISO week ending day) and use its ISO week number.
        #
        # Robust to launchd timezone wobble:
        #   Sunday 20:00 EDT → Mon 00:00 UTC → isoweekday=1 → days_back=1 → last Sun → W=just-ended
        #   Sunday 20:00 EST → Mon 01:00 UTC → isoweekday=1 → days_back=1 → last Sun → W=just-ended
        #   Manual run on Friday → isoweekday=5 → days_back=5 → last Sun → W=just-ended
        # Fix 2026-05-08: prior `now() - 1d` then isocalendar() landed on the
        # WRONG week when launchd fired ~midnight UTC, producing zero-data
        # reports for the week that hadn't started yet (e.g. W19 on 5/3).
        now_utc = datetime.now(timezone.utc)
        days_back_to_sun = now_utc.isoweekday() % 7  # Sun=0, Mon=1, ..., Sat=6
        last_sunday = now_utc - timedelta(days=days_back_to_sun)
        iso = last_sunday.isocalendar()
        year, week = iso[0], iso[1]
    week_label = f"{year}-W{week:02d}"
    week_start, week_end = get_week_dates(year, week)

    print(f"📊 {'OG image' if args.og_only else 'Weekly report'} for {week_label} ({week_start} → {week_end})...")

    live = fetch_live_status()
    daily_series = load_daily_pnl_series(DB_PATH, LIVE_SINCE)
    print(f"   📄 {len(daily_series)} day-buckets in trade_log since {LIVE_SINCE}; live-status: {'OK' if live else 'unavailable'}")

    stats = calculate_stats(daily_series, live, week_start, week_end)
    print(
        f"   Week: ${stats['week_pnl']:+.2f} | {stats['week_fills']} trades  |  "
        f"Cum: ${stats['cum_pnl']:+.2f} | Bal ${stats['balance']:,.2f}  |  "
        f"source: {stats['live_source']}"
    )

    charts = generate_charts(stats, week_label)

    if args.og_only:
        print("✅ OG image done")
        return

    tg = format_telegram(stats, week_label)
    tw = format_twitter(stats, week_label)

    social_file = OUTPUT_DIR / f"weekly_social_{week_label}.txt"
    with open(social_file, "w") as f:
        f.write(f"=== Weekly Report — {week_label} ===\n")
        f.write(f"Week P&L: ${stats['week_pnl']:+.2f}\n")
        f.write(f"Balance: ${stats['balance']:,.2f}\n")
        f.write(f"Source: {stats['live_source']}\n\n")
        f.write(f"--- TWITTER ---\n{tw}\n")
    print(f"   📝 Social copy: {social_file}")

    mb_title, mb_body = format_moltbook(stats, week_label, week_start, week_end)

    if not args.dry_run:
        send_telegram(tg, photo=charts.get("chart"))
        publish_moltbook(mb_title, mb_body)
        if TWITTER_ENABLED:
            try:
                from twitter_auto_poster import post_tweet, upload_image
                print("   🐦 Posting to Twitter/X...")
                chart_path = charts.get("chart")
                media_id = upload_image(chart_path) if chart_path else None
                post_tweet(tw, media_id=media_id)
            except Exception as e:
                print(f"   ⚠️  Twitter post skipped: {e}")
        else:
            print("   🐦 Twitter post skipped (paused per feedback_social_paused.md).")
    else:
        print(f"\n--- TELEGRAM ---\n{tg}\n")
        print(f"\n--- MOLTBOOK ---\nTitle: {mb_title}\n\n{mb_body}\n")
        print(f"\n--- TWITTER (paused — would not post) ---\n{tw}\n")

    print(f"\n✅ Done for {week_label}")


if __name__ == "__main__":
    main()
