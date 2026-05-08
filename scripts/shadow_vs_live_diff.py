#!/usr/bin/env python3
"""
Shadow vs Live Diff — daily attribution report.

Reads both sniper trade_log tables (live + shadow), restricted to closes in
the last N hours, and produces a side-by-side report:

  • aggregate stats per instance (trades, win rate, gross PnL, avg PnL)
  • per-trade pairing: for closes that happened within +/- 30 minutes of each
    other, compare exit_reason / pnl / hold_time
  • flagged divergences: same direction, very different exit_reason or pnl

The shadow exists to validate the regime-trailing sweep proposal in real time
(activate=0.004 vs live 0.008). This script is the pulse-check on whether the
backtest's promised +$5,148/180d edge is showing up out-of-sample.

Usage:
  python3 scripts/shadow_vs_live_diff.py                    # last 24h
  python3 scripts/shadow_vs_live_diff.py --hours 168        # last 7d
  python3 scripts/shadow_vs_live_diff.py --json             # machine-readable

Designed to be wired to a daily LaunchAgent — push the report via ntfy when
the cumulative shadow-vs-live delta exceeds a configured floor.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

LIVE_DB = "/Users/bonnyagent/ibitlabs/sol_sniper.db"
SHADOW_DB = "/Users/bonnyagent/ibitlabs/sol_sniper_shadow.db"
PAIRING_WINDOW_SEC = 30 * 60  # 30 minutes


def fetch_closes(db_path: str, hours: int) -> list:
    if not Path(db_path).exists():
        return []
    cutoff = time.time() - hours * 3600
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT * FROM trade_log
               WHERE timestamp >= ? AND pnl IS NOT NULL AND pnl != 0
               ORDER BY timestamp ASC""",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def aggregate(closes: list) -> dict:
    if not closes:
        return {"n": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "total_pnl": 0.0, "avg_pnl": 0.0, "gross_win": 0.0,
                "gross_loss": 0.0, "by_reason": {}}
    n = len(closes)
    wins = sum(1 for c in closes if float(c.get("pnl") or 0) > 0)
    losses = n - wins
    total = sum(float(c.get("pnl") or 0) for c in closes)
    gross_win = sum(float(c["pnl"]) for c in closes if float(c["pnl"]) > 0)
    gross_loss = sum(float(c["pnl"]) for c in closes if float(c["pnl"]) <= 0)
    by_reason = {}
    for c in closes:
        r = c.get("exit_reason") or "untagged"
        by_reason.setdefault(r, {"n": 0, "pnl": 0.0})
        by_reason[r]["n"] += 1
        by_reason[r]["pnl"] += float(c["pnl"])
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / n,
        "total_pnl": total,
        "avg_pnl": total / n,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "by_reason": by_reason,
    }


def pair_trades(live: list, shadow: list) -> list:
    """
    Naive pairing: for each live close, find the shadow close with the same
    direction whose timestamp is closest, within PAIRING_WINDOW_SEC. Each
    shadow close can only be paired once. Unpaired closes go in the
    'unpaired_live' / 'unpaired_shadow' buckets.
    """
    used = set()
    pairs = []
    for L in live:
        L_dir = L.get("direction") or _infer_dir(L)
        L_ts = float(L["timestamp"])
        best = None
        best_dt = None
        for i, S in enumerate(shadow):
            if i in used:
                continue
            S_dir = S.get("direction") or _infer_dir(S)
            if L_dir != S_dir:
                continue
            dt = abs(float(S["timestamp"]) - L_ts)
            if dt > PAIRING_WINDOW_SEC:
                continue
            if best is None or dt < best_dt:
                best = i
                best_dt = dt
        if best is not None:
            used.add(best)
            pairs.append((L, shadow[best], best_dt))
    unpaired_live = [L for L in live
                     if not any(p[0] is L for p in pairs)]
    unpaired_shadow = [shadow[i] for i in range(len(shadow)) if i not in used]
    return pairs, unpaired_live, unpaired_shadow


def _infer_dir(c: dict) -> str:
    side = (c.get("side") or "").upper()
    if "BUY" in side:
        return "short"  # close BUY closes a short
    if "SELL" in side:
        return "long"
    return "?"


def fmt_money(x: float) -> str:
    return f"${x:+.2f}"


def render_text(live_agg, shadow_agg, pairs, unpaired_live, unpaired_shadow, hours):
    lines = []
    lines.append(f"=== Shadow vs Live (last {hours}h) ===")
    lines.append("")
    lines.append(f"{'metric':<22}{'live':>14}{'shadow':>14}{'delta':>14}")
    rows = [
        ("trades", live_agg["n"], shadow_agg["n"]),
        ("wins", live_agg["wins"], shadow_agg["wins"]),
        ("losses", live_agg["losses"], shadow_agg["losses"]),
        ("win rate", f"{live_agg['win_rate']:.0%}", f"{shadow_agg['win_rate']:.0%}"),
        ("total pnl", fmt_money(live_agg["total_pnl"]), fmt_money(shadow_agg["total_pnl"])),
        ("avg pnl", fmt_money(live_agg["avg_pnl"]), fmt_money(shadow_agg["avg_pnl"])),
        ("gross win", fmt_money(live_agg["gross_win"]), fmt_money(shadow_agg["gross_win"])),
        ("gross loss", fmt_money(live_agg["gross_loss"]), fmt_money(shadow_agg["gross_loss"])),
    ]
    for name, l, s in rows:
        delta = ""
        if isinstance(l, (int, float)) and isinstance(s, (int, float)):
            delta = f"{(s - l):+}"
        elif name == "total pnl":
            delta = fmt_money(shadow_agg["total_pnl"] - live_agg["total_pnl"])
        lines.append(f"{name:<22}{str(l):>14}{str(s):>14}{delta:>14}")

    lines.append("")
    lines.append("Exit reasons:")
    all_reasons = sorted(set(live_agg["by_reason"]) | set(shadow_agg["by_reason"]))
    lines.append(f"{'reason':<14}{'live n':>10}{'live pnl':>14}{'shadow n':>10}{'shadow pnl':>14}")
    for r in all_reasons:
        lr = live_agg["by_reason"].get(r, {"n": 0, "pnl": 0.0})
        sr = shadow_agg["by_reason"].get(r, {"n": 0, "pnl": 0.0})
        lines.append(
            f"{r:<14}{lr['n']:>10}{fmt_money(lr['pnl']):>14}{sr['n']:>10}{fmt_money(sr['pnl']):>14}"
        )

    lines.append("")
    lines.append(f"Paired trades: {len(pairs)}  |  unpaired live: {len(unpaired_live)}  |  unpaired shadow: {len(unpaired_shadow)}")
    if pairs:
        lines.append("")
        lines.append("Per-pair detail:")
        lines.append(f"{'time':<17}{'dir':<7}{'live exit':<14}{'live pnl':>12}{'shadow exit':<14}{'shadow pnl':>12}{'delta':>12}")
        for L, S, dt in pairs[-15:]:  # last 15 pairs to keep output bounded
            t = time.strftime("%m-%d %H:%M", time.localtime(float(L["timestamp"])))
            d = (L.get("direction") or _infer_dir(L))[:5]
            le = (L.get("exit_reason") or "?")[:13]
            se = (S.get("exit_reason") or "?")[:13]
            lp = float(L.get("pnl") or 0)
            sp = float(S.get("pnl") or 0)
            lines.append(
                f"{t:<17}{d:<7}{le:<14}{fmt_money(lp):>12}{se:<14}{fmt_money(sp):>12}{fmt_money(sp-lp):>12}"
            )

    if unpaired_live or unpaired_shadow:
        lines.append("")
        lines.append("Unpaired (no counterpart within +/- 30 min):")
        for L in unpaired_live:
            t = time.strftime("%m-%d %H:%M", time.localtime(float(L["timestamp"])))
            lines.append(f"  LIVE only   {t}  {(L.get('exit_reason') or '?'):<14} {fmt_money(float(L['pnl']))}")
        for S in unpaired_shadow:
            t = time.strftime("%m-%d %H:%M", time.localtime(float(S["timestamp"])))
            lines.append(f"  SHADOW only {t}  {(S.get('exit_reason') or '?'):<14} {fmt_money(float(S['pnl']))}")

    lines.append("")
    lines.append(f"Verdict: shadow {fmt_money(shadow_agg['total_pnl'] - live_agg['total_pnl'])} vs live over window")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-db", default=LIVE_DB)
    parser.add_argument("--shadow-db", default=SHADOW_DB)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    live = fetch_closes(args.live_db, args.hours)
    shadow = fetch_closes(args.shadow_db, args.hours)

    if not Path(args.shadow_db).exists():
        print(f"shadow DB not found at {args.shadow_db} — has the shadow instance run yet?",
              file=sys.stderr)
        return 2

    live_agg = aggregate(live)
    shadow_agg = aggregate(shadow)
    pairs, unpaired_live, unpaired_shadow = pair_trades(live, shadow)

    if args.json:
        print(json.dumps({
            "hours": args.hours,
            "live": live_agg,
            "shadow": shadow_agg,
            "delta_total_pnl": shadow_agg["total_pnl"] - live_agg["total_pnl"],
            "n_paired": len(pairs),
            "n_unpaired_live": len(unpaired_live),
            "n_unpaired_shadow": len(unpaired_shadow),
        }, indent=2))
    else:
        print(render_text(live_agg, shadow_agg, pairs, unpaired_live, unpaired_shadow, args.hours))
    return 0


if __name__ == "__main__":
    sys.exit(main())
