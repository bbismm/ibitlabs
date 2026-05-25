"""
Cross-validate vol_ratio entry filter thresholds {1.0, 1.1, 1.2, 1.3, 1.4, 1.5,
1.55, 1.7, 2.0} against LIVE-traded outcomes.

Origin: 2026-05-24 ship of SNIPER_MIN_VOL_RATIO=1.5 was justified by
"6/7 SL losers < 1.55" — SL-only angle. Initial scan of 21 LIVE entries showed
the 1.5 cut also removes a profitable [1.2, 1.5) bucket. This script re-runs
the sweep on the full LIVE-replay set (via entry_confidence_map ↔ trade_log
match, same pattern as momentum_filter_long_2026_05_24.py) to settle whether
1.2 or 1.5 is the better threshold.

Output sections:
  A. Per-direction summary (long/short)
  B. Threshold sweep — kept_W/L, kept_WR, PnL_kept, net_swing vs baseline
  C. Bucket PnL (immutable, regardless of threshold)
  D. SL-only signature (the original 6/7 < 1.55 claim re-verified)
"""

import json
import sqlite3
from pathlib import Path

JSONL = Path.home() / "ibitlabs" / "logs" / "entry_confidence_map.jsonl"
DB = Path.home() / "ibitlabs" / "sol_sniper.db"


def load_matched() -> list:
    entries = []
    with open(JSONL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") == "entry_confidence_map":
                entries.append(rec)

    # dedupe by order_id, keep first with non-None vol_ratio
    by_oid = {}
    for e in entries:
        oid = e.get("order_id", "?")
        vr = (e.get("market_state") or {}).get("vol_ratio")
        if oid not in by_oid:
            by_oid[oid] = e
        elif by_oid[oid].get("market_state", {}).get("vol_ratio") is None and vr is not None:
            by_oid[oid] = e
    entries = list(by_oid.values())

    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    matched = []
    for e in entries:
        ep = e.get("entry_price")
        dir_ = e.get("direction")
        ets = e.get("entry_ts")
        vr = (e.get("market_state") or {}).get("vol_ratio")
        if vr is None or not (ep and dir_ and ets):
            continue
        cur.execute(
            """
            SELECT id FROM trade_log
            WHERE instance_name='live' AND strategy_version='hybrid_v5.1'
              AND direction=? AND ABS(entry_price-?)<0.001
              AND exit_price IS NULL AND ABS(timestamp-?)<120
            ORDER BY ABS(timestamp-?) ASC LIMIT 1
            """,
            (dir_, ep, ets, ets),
        )
        op = cur.fetchone()
        if not op:
            continue
        open_id = op[0]
        cur.execute(
            """
            SELECT id, pnl, exit_reason FROM trade_log
            WHERE instance_name='live' AND strategy_version='hybrid_v5.1'
              AND direction=? AND ABS(entry_price-?)<0.001
              AND id>? AND exit_price IS NOT NULL
            ORDER BY id ASC LIMIT 1
            """,
            (dir_, ep, open_id),
        )
        cr = cur.fetchone()
        if not cr:
            continue
        cid, pnl, reason = cr
        matched.append({
            "close_id": cid,
            "direction": dir_,
            "regime": e.get("regime"),
            "vol_ratio": vr,
            "pnl": pnl,
            "exit_reason": (reason or "").strip(),
            "is_winner": pnl > 0,
        })
    return matched


def summarize(label, lst):
    if not lst:
        print(f"  {label}: n=0")
        return
    pnl = sum(x["pnl"] for x in lst)
    wins = sum(1 for x in lst if x["is_winner"])
    print(f"  {label}: n={len(lst):3d} PnL=${pnl:+8.2f} WR={100*wins/len(lst):5.1f}% avg=${pnl/len(lst):+6.2f}")


def main():
    matched = load_matched()
    longs = [m for m in matched if m["direction"] == "long"]
    shorts = [m for m in matched if m["direction"] == "short"]

    print(f"=== Universe ===")
    print(f"  matched entries: n={len(matched)} (long={len(longs)} short={len(shorts)})")
    baseline_pnl = sum(m["pnl"] for m in matched)
    print(f"  baseline PnL (no filter): ${baseline_pnl:+.2f}")

    print(f"\n=== A. Per-direction summary ===")
    summarize("ALL    ", matched)
    summarize("LONG   ", longs)
    summarize("SHORT  ", shorts)

    print(f"\n=== B. Threshold sweep (apply to BOTH directions) ===")
    print(f"{'thr (≥)':>7} {'kept':>5} {'kpW':>4} {'kpL':>4}  {'drop':>5} {'dpW':>4} {'dpL':>4}  "
          f"{'kept_WR':>8} {'PnL_kept':>9} {'PnL_drop':>9}  {'swing':>8}")
    for thr in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.55, 1.7, 2.0]:
        kept = [m for m in matched if m["vol_ratio"] >= thr]
        drop = [m for m in matched if m["vol_ratio"] < thr]
        kw = sum(1 for x in kept if x["is_winner"])
        kl = sum(1 for x in kept if not x["is_winner"])
        dw = sum(1 for x in drop if x["is_winner"])
        dl = sum(1 for x in drop if not x["is_winner"])
        kpnl = sum(x["pnl"] for x in kept)
        dpnl = sum(x["pnl"] for x in drop)
        wr = 100 * kw / len(kept) if kept else 0
        swing = kpnl - baseline_pnl
        mark = ""
        if thr == 1.5:
            mark = "  ← LIVE"
        elif thr == 1.55:
            mark = "  ← SL-sig"
        print(f"{thr:>7.2f} {len(kept):>5} {kw:>4} {kl:>4}  {len(drop):>5} {dw:>4} {dl:>4}  "
              f"{wr:>7.1f}% {kpnl:>+9.2f} {dpnl:>+9.2f}  {swing:>+8.2f}{mark}")

    print(f"\n=== B'. Threshold sweep LONG-only ===")
    print(f"{'thr (≥)':>7} {'kept':>5} {'kpW':>4} {'kpL':>4}  {'kept_WR':>8} {'PnL_kept':>9} {'swing':>8}")
    base_long = sum(m["pnl"] for m in longs)
    for thr in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.55, 1.7, 2.0]:
        kept = [m for m in longs if m["vol_ratio"] >= thr]
        kw = sum(1 for x in kept if x["is_winner"])
        kl = sum(1 for x in kept if not x["is_winner"])
        kpnl = sum(x["pnl"] for x in kept)
        wr = 100 * kw / len(kept) if kept else 0
        print(f"{thr:>7.2f} {len(kept):>5} {kw:>4} {kl:>4}  {wr:>7.1f}% {kpnl:>+9.2f}  {kpnl - base_long:>+8.2f}")

    print(f"\n=== B''. Threshold sweep SHORT-only ===")
    print(f"{'thr (≥)':>7} {'kept':>5} {'kpW':>4} {'kpL':>4}  {'kept_WR':>8} {'PnL_kept':>9} {'swing':>8}")
    base_short = sum(m["pnl"] for m in shorts)
    for thr in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.55, 1.7, 2.0]:
        kept = [m for m in shorts if m["vol_ratio"] >= thr]
        kw = sum(1 for x in kept if x["is_winner"])
        kl = sum(1 for x in kept if not x["is_winner"])
        kpnl = sum(x["pnl"] for x in kept)
        wr = 100 * kw / len(kept) if kept else 0
        print(f"{thr:>7.2f} {len(kept):>5} {kw:>4} {kl:>4}  {wr:>7.1f}% {kpnl:>+9.2f}  {kpnl - base_short:>+8.2f}")

    print(f"\n=== C. Bucket PnL (immutable distribution) ===")
    buckets = [(0.0, 1.1), (1.1, 1.2), (1.2, 1.3), (1.3, 1.5), (1.5, 1.8),
               (1.8, 2.5), (2.5, 99)]
    for lo, hi in buckets:
        sub = [m for m in matched if lo <= m["vol_ratio"] < hi]
        if not sub:
            print(f"  [{lo:>4.1f}, {hi:>4.1f})  n=  0")
            continue
        pnl = sum(x["pnl"] for x in sub)
        wins = sum(1 for x in sub if x["is_winner"])
        print(f"  [{lo:>4.1f}, {hi:>4.1f})  n={len(sub):>2}  PnL=${pnl:+8.2f}  WR={100*wins/len(sub):>5.1f}%  avg=${pnl/len(sub):+6.2f}")

    print(f"\n=== D. SL-only signature check (the original claim) ===")
    sls = [m for m in matched if m["exit_reason"] == "stop_loss"]
    print(f"  Total SL exits matched: {len(sls)}")
    if sls:
        below_155 = sum(1 for x in sls if x["vol_ratio"] < 1.55)
        below_150 = sum(1 for x in sls if x["vol_ratio"] < 1.50)
        below_120 = sum(1 for x in sls if x["vol_ratio"] < 1.20)
        print(f"    SL with vol_ratio < 1.55: {below_155}/{len(sls)}")
        print(f"    SL with vol_ratio < 1.50: {below_150}/{len(sls)}")
        print(f"    SL with vol_ratio < 1.20: {below_120}/{len(sls)}")
        print(f"  SL vol_ratios sorted: {sorted(round(x['vol_ratio'],2) for x in sls)}")

    print(f"\n=== E. Per-trade table sorted by vol_ratio asc ===")
    print(f"{'cid':>5} {'dir':<5} {'regime':<10} {'vol_r':>6} {'pnl':>8} {'reason':<14} {'state'}")
    for m in sorted(matched, key=lambda x: x["vol_ratio"]):
        state = "WIN " if m["is_winner"] else "LOSS"
        print(f"{m['close_id']:>5} {m['direction']:<5} {str(m['regime']):<10} "
              f"{m['vol_ratio']:>6.2f} {m['pnl']:>+8.2f} {m['exit_reason']:<14} {state}")


if __name__ == "__main__":
    main()
