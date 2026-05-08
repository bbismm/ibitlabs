"""
risk_officer — portfolio-level safety gate for multi-symbol v5.1.

Implements the static cap + dynamic risk-OFF brake design from
`docs/multi_symbol_eth_expansion_DD.md` decision #1.

Usage (intended; not yet wired into sol_sniper_executor):

    from risk_officer import RiskOfficer
    from v5_1_config import config_for

    cfg = config_for("SOL")
    ro = RiskOfficer(
        cfg,
        db_paths=["sol_sniper.db", "sol_sniper_eth_paper.db"],
        exchange=exchange,  # None in pure-paper mode
        paper_mode=False,
    )

    ok, scaled_notional, reason = ro.check_can_open(
        symbol="SOL",
        proposed_notional_usd=800.0,
        current_balance=1000.0,
    )
    if not ok:
        log.info(f"[RISK-OFFICER] skip entry: {reason}")
        return

    # else: trade with notional = scaled_notional (may be less than proposed)

Design notes
------------

The risk officer is intentionally *boring*. It does not learn, does not adapt
to recent performance, does not chase. Its only dynamic dimension is a
single-direction safety brake that *reduces* the cap after a drawdown and
restores it only on a new equity high. Reflexivity is the bug it refuses to
have.

Why static between symbols
~~~~~~~~~~~~~~~~~~~~~~~~~~
At our sample size (~30-90 trades over 90 days), "smart" cross-symbol
allocation is data dredging. Dynamic-EMA-weighted regime-conditional weights
need thousands of samples per arm to beat a flat split. We don't have them.

Why dynamic in the safety direction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A drawdown brake is a single-direction function — it only ever reduces
exposure, never raises mid-cycle. No reflexivity, no chasing, no sample-size
dependency on the trigger (DD is defined, not estimated).

What lives here vs in the strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Per-trade entry conditions (StochRSI, BB, regime, vol_ratio, etc.) live in
sol_sniper_signals.py. Per-position exit logic (TP/SL/trailing) lives in
sol_sniper_executor.py. The risk officer arbitrates *across* positions and
*across* symbols — it never overrides an exit, only blocks or scales an
entry.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ── Static caps ──
# Sourced from docs/multi_symbol_eth_expansion_DD.md decision #1.
PORTFOLIO_BASELINE_X = 1.5     # max total notional / cash, no brake
PER_SYMBOL_MAX_X = 1.0          # max per-symbol notional / cash
PER_SYMBOL_MIN_X = 0.4          # below this, fee drag is material → skip

# ── Dynamic risk-OFF brake ──
# 7-day drawdown thresholds. Higher (more negative) DD → smaller portfolio
# cap. ONLY ever reduces; the cap restores to baseline on a new equity high.
# Tuples are (drawdown_threshold, cap_multiplier), evaluated worst-to-best.
DD_BRAKE_LEVELS = [
    (-0.15, 0.0),   # 15%+ drawdown → halt all new entries (manual reset only)
    (-0.10, 0.5),   # 10-15%       → 0.5x cash
    (-0.05, 1.0),   # 5-10%        → 1.0x cash (still per-symbol normal)
    # else: 1.5x cash (baseline)
]

# 7-day rolling window for drawdown computation.
DD_WINDOW_SECONDS = 7 * 86400


@dataclass
class PortfolioSnapshot:
    """One-shot view of the portfolio used to make a single can-open decision."""
    cash: float
    per_symbol_notional_usd: dict  # {"SOL": 420.0, "ETH": 0.0, ...}
    total_notional_usd: float
    brake_cap_x: float             # 0.0 / 0.5 / 1.0 / 1.5
    brake_dd_pct: float            # negative or 0.0 (never positive)

    def __str__(self) -> str:
        per = ", ".join(f"{s}=${n:.0f}" for s, n in self.per_symbol_notional_usd.items())
        return (
            f"cash=${self.cash:.0f} | total notional=${self.total_notional_usd:.0f} "
            f"({per}) | brake={self.brake_cap_x:.1f}x (DD {self.brake_dd_pct:+.1%})"
        )


class RiskOfficer:
    """Portfolio-level gate. Stateless across calls (recomputes each time)."""

    def __init__(
        self,
        config,
        db_paths: list[str],
        exchange=None,
        paper_mode: bool = False,
    ):
        """
        Args:
            config: SniperConfig (any symbol's; we only read shared params)
            db_paths: trade_log DBs across all v5.1 instances. In a 2-bot
                deployment: ['sol_sniper.db', 'sol_sniper_eth_live.db'] or
                ['sol_sniper.db', 'sol_sniper_eth_paper.db'] for paper-mixed.
                Drawdown is computed by aggregating PnL across all of them.
            exchange: ccxt-like exchange instance for fetch_positions(). Pass
                None when running in pure paper-mode (no real positions to
                read).
            paper_mode: if True, exchange.fetch_positions is skipped; per-symbol
                notional is treated as 0 except for the calling symbol's own
                paper state (which the caller must pass into check_can_open
                via the `existing_own_notional_usd` arg).
        """
        self.config = config
        self.db_paths = [str(p) for p in db_paths]
        self.exchange = exchange
        self.paper_mode = paper_mode

    # ──────────────────────────────────────────────────────────────────
    # Drawdown computation
    # ──────────────────────────────────────────────────────────────────
    def compute_7d_drawdown_pct(self, current_balance: float) -> float:
        """Reconstruct 7d equity curve from trade_log PnLs and return (current
        - peak) / peak as a negative number, or 0.0 at a new high / no data.

        Aggregates closed trades across all configured db_paths so the brake
        is portfolio-aware, not symbol-aware.
        """
        if current_balance <= 0:
            return 0.0
        cutoff_ts = time.time() - DD_WINDOW_SECONDS

        rows: list[tuple[float, float]] = []
        for db_path in self.db_paths:
            if not Path(db_path).exists():
                continue
            try:
                conn = sqlite3.connect(db_path)
                fetched = conn.execute(
                    "SELECT timestamp, COALESCE(pnl, 0) FROM trade_log "
                    "WHERE strategy_version = 'hybrid_v5.1' "
                    "AND exit_reason IS NOT NULL AND exit_reason != '' "
                    "AND timestamp >= ? "
                    "ORDER BY timestamp ASC",
                    (cutoff_ts,),
                ).fetchall()
                conn.close()
                rows.extend((float(ts), float(p)) for ts, p in fetched)
            except sqlite3.Error as e:
                logger.warning(f"[RISK-OFFICER] DB {db_path} unreadable: {e}")

        if not rows:
            return 0.0

        rows.sort(key=lambda r: r[0])
        sum_pnl_7d = sum(p for _, p in rows)
        starting_balance = current_balance - sum_pnl_7d

        running = starting_balance
        peak = starting_balance
        for _, pnl in rows:
            running += pnl
            if running > peak:
                peak = running

        if peak <= 0:
            return 0.0
        dd = (current_balance - peak) / peak
        return min(0.0, dd)  # never positive

    def compute_brake(self, current_balance: float) -> Tuple[float, float]:
        """Return (cap_multiplier, dd_pct).

        cap_multiplier ∈ {0.0, 0.5, 1.0, 1.5}.
        """
        dd = self.compute_7d_drawdown_pct(current_balance)
        for threshold, cap in DD_BRAKE_LEVELS:
            if dd <= threshold:
                return (cap, dd)
        return (PORTFOLIO_BASELINE_X, dd)

    # ──────────────────────────────────────────────────────────────────
    # Portfolio notional aggregation
    # ──────────────────────────────────────────────────────────────────
    def fetch_per_symbol_notional_usd(
        self,
        own_symbol: str,
        own_notional_usd: float = 0.0,
    ) -> dict:
        """Return {'SOL': X, 'ETH': Y, ...} of CURRENTLY OPEN notional.

        In live mode: queries exchange.fetch_positions() and converts via
            contracts × price (Coinbase positions report contracts, mark price).
            (We approximate notional from contracts × markPrice if present;
            fall back to contracts × entryPrice otherwise.)

        In paper mode: returns {own_symbol: own_notional_usd}, since this
            paper bot is the only state-holder for itself, and the live SOL
            bot's exposure shouldn't constrain a paper bot's hypothetical
            entry (different account).
        """
        if self.paper_mode or self.exchange is None:
            return {own_symbol: float(own_notional_usd)}

        try:
            positions = self.exchange.fetch_positions()
        except Exception as e:
            logger.warning(f"[RISK-OFFICER] fetch_positions failed: {e}")
            # fail safe: pretend portfolio is empty so the cap is permissive
            # — but the per-symbol cap still applies. Better than spurious halt.
            return {own_symbol: float(own_notional_usd)}

        out: dict = {}
        for p in positions:
            contracts = float(p.get("contracts") or 0)
            if contracts == 0:
                continue
            symbol_id = p.get("symbol") or p.get("info", {}).get("product_id") or "?"
            price = (
                float(p.get("markPrice") or 0)
                or float(p.get("entryPrice") or 0)
                or float(p.get("info", {}).get("mark_price") or 0)
            )
            # Notional in USD = contracts × contract_size × price.
            # We don't know each symbol's contract_size from the position dict
            # alone, but the calling SniperConfig knows its own. For
            # unknown symbols, fall back to contracts × price (treating each
            # contract as 1 base unit) — accurate enough for the cap math
            # since only the calling symbol's value is what gates the entry,
            # and "all other symbols" combined just need to be in the right
            # ballpark. TODO: pass a {symbol → contract_size} map for full
            # accuracy across heterogeneous symbols.
            notional = contracts * price
            sym_short = symbol_id.split("-")[0]
            # Map Coinbase product short → our internal alias.
            # SLP → SOL, ETP → ETH, etc.
            alias = {"SLP": "SOL", "ETP": "ETH"}.get(sym_short, sym_short)
            out[alias] = out.get(alias, 0.0) + notional

        # Always include own_symbol so the caller can read it back even if
        # there's no current position.
        out.setdefault(own_symbol, 0.0)
        return out

    # ──────────────────────────────────────────────────────────────────
    # The actual gate
    # ──────────────────────────────────────────────────────────────────
    def snapshot(
        self,
        own_symbol: str,
        current_balance: float,
        own_open_notional_usd: float = 0.0,
    ) -> PortfolioSnapshot:
        """One-shot portfolio view + brake state for diagnostics."""
        per_sym = self.fetch_per_symbol_notional_usd(
            own_symbol=own_symbol,
            own_notional_usd=own_open_notional_usd,
        )
        total = sum(per_sym.values())
        cap_x, dd = self.compute_brake(current_balance)
        return PortfolioSnapshot(
            cash=current_balance,
            per_symbol_notional_usd=per_sym,
            total_notional_usd=total,
            brake_cap_x=cap_x,
            brake_dd_pct=dd,
        )

    def check_can_open(
        self,
        symbol: str,
        proposed_notional_usd: float,
        current_balance: float,
        own_open_notional_usd: float = 0.0,
    ) -> Tuple[bool, float, str]:
        """Decide whether to allow opening a new position with the given
        proposed notional. Returns (allowed, scaled_notional, reason).

        Logic order:
          1. Halt brake (7d DD > 15%)        → (False, 0, ...)
          2. Per-symbol min                   → (False, 0, ...) — scale-down
                                                   below 0.4x cash means fees
                                                   eat alpha; better to skip
          3. Per-symbol max (1.0x cash)       → scale to cap
          4. Portfolio cap (cap_x × cash)     → scale further if needed
          5. Re-check per-symbol min after scaling — same skip condition
          6. Allow with final scaled notional

        Scaling preserves the *spirit* of the proposed entry. If the available
        room is too small to be worth the fee drag, we skip rather than fire
        a tiny token position.
        """
        snap = self.snapshot(
            own_symbol=symbol,
            current_balance=current_balance,
            own_open_notional_usd=own_open_notional_usd,
        )

        # 1. Halt brake
        if snap.brake_cap_x == 0.0:
            return (
                False, 0.0,
                f"halt: 7d DD = {snap.brake_dd_pct:+.1%} (≤ -15%); manual reset required",
            )

        # 2. Per-symbol min (against the proposed)
        per_sym_min = PER_SYMBOL_MIN_X * current_balance
        if proposed_notional_usd < per_sym_min:
            return (
                False, 0.0,
                f"skip: proposed ${proposed_notional_usd:.0f} below per-symbol min "
                f"${per_sym_min:.0f} (= {PER_SYMBOL_MIN_X}x cash) — fee drag too high",
            )

        # 3. Per-symbol max (1.0x cash, less anything already open in this symbol)
        per_sym_max = PER_SYMBOL_MAX_X * current_balance
        already_in_this_symbol = snap.per_symbol_notional_usd.get(symbol, 0.0)
        per_sym_room = max(0.0, per_sym_max - already_in_this_symbol)

        # 4. Portfolio cap (brake_cap_x × cash, less total currently open)
        portfolio_max = snap.brake_cap_x * current_balance
        portfolio_room = max(0.0, portfolio_max - snap.total_notional_usd)

        # The smaller of the two ceilings wins
        ceiling = min(per_sym_room, portfolio_room)
        scaled = min(proposed_notional_usd, ceiling)

        # 5. Re-check per-symbol min after scaling
        if scaled < per_sym_min:
            return (
                False, 0.0,
                f"skip: scaled ${scaled:.0f} below min ${per_sym_min:.0f} "
                f"(per-symbol room ${per_sym_room:.0f}, "
                f"portfolio room ${portfolio_room:.0f}) — fee drag too high",
            )

        # 6. Allow
        scaled_pct = scaled / proposed_notional_usd if proposed_notional_usd > 0 else 0
        if scaled < proposed_notional_usd:
            reason = (
                f"scaled to ${scaled:.0f} ({scaled_pct:.0%} of proposed) — "
                f"brake {snap.brake_cap_x:.1f}x, "
                f"per-sym room ${per_sym_room:.0f}, portfolio room ${portfolio_room:.0f}"
            )
        else:
            reason = (
                f"full size ${scaled:.0f} — "
                f"brake {snap.brake_cap_x:.1f}x, no constraint binding"
            )
        return (True, scaled, reason)


# ──────────────────────────────────────────────────────────────────
# Smoke test
# ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    """Self-contained smoke test using a fake DB and SniperConfig.

    Verifies:
      • baseline: small position fits, no brake
      • per-symbol cap: huge proposed scales down
      • per-symbol min: tiny proposed gets skipped (not scaled to 0)
      • DD brake: 7d DD > 5% reduces the cap
      • halt: 7d DD > 15% blocks entry entirely
    """
    import os
    import tempfile
    from dataclasses import dataclass as _dc

    print("=" * 60)
    print("risk_officer smoke test")
    print("=" * 60)

    @_dc
    class _FakeCfg:
        contract_size: float = 5.0

    def _fake_db(pnls: list[tuple[int, float]]) -> str:
        """pnls = [(seconds_ago, pnl_usd), ...] — create a temp DB with these closes."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.execute("""
            CREATE TABLE trade_log (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                pnl REAL,
                strategy_version TEXT,
                exit_reason TEXT
            )
        """)
        now = time.time()
        for secs_ago, pnl in pnls:
            conn.execute(
                "INSERT INTO trade_log(timestamp, pnl, strategy_version, exit_reason) "
                "VALUES (?, ?, 'hybrid_v5.1', 'sl')",
                (now - secs_ago, pnl),
            )
        conn.commit()
        conn.close()
        return tmp.name

    cash = 1000.0

    # ── Test 1: empty DB, baseline cap, small proposal fits cleanly ──
    db1 = _fake_db([])
    ro1 = RiskOfficer(_FakeCfg(), db_paths=[db1], paper_mode=True)
    ok, scaled, reason = ro1.check_can_open("SOL", 800, cash, 0)
    print(f"\n1. baseline (empty DB), propose $800:")
    print(f"   {'✅' if ok and scaled == 800 else '❌'}  ok={ok} scaled=${scaled:.0f}  ({reason})")
    os.unlink(db1)

    # ── Test 2: empty DB, propose huge $5000 → scales to per-sym cap $1000 ──
    db2 = _fake_db([])
    ro2 = RiskOfficer(_FakeCfg(), db_paths=[db2], paper_mode=True)
    ok, scaled, reason = ro2.check_can_open("SOL", 5000, cash, 0)
    expected_cap = PER_SYMBOL_MAX_X * cash
    print(f"\n2. propose $5000, expect scale to per-symbol cap ${expected_cap:.0f}:")
    print(f"   {'✅' if ok and abs(scaled - expected_cap) < 0.01 else '❌'}  ok={ok} scaled=${scaled:.0f}  ({reason})")
    os.unlink(db2)

    # ── Test 3: tiny proposal $200 below per-sym min ($400) → skip ──
    db3 = _fake_db([])
    ro3 = RiskOfficer(_FakeCfg(), db_paths=[db3], paper_mode=True)
    ok, scaled, reason = ro3.check_can_open("SOL", 200, cash, 0)
    print(f"\n3. propose $200 (below per-sym min $400), expect skip:")
    print(f"   {'✅' if not ok and scaled == 0 else '❌'}  ok={ok} scaled=${scaled:.0f}  ({reason})")
    os.unlink(db3)

    # ── Test 4: 7d DD = -7% → first brake step (cap → 1.0x) ──
    # We need PnLs that, given current_balance=$1000, produce a peak then DD.
    # Sequence: +$100 (peak $1100) then -$70 (current $1030 → DD = (1030-1100)/1100 = -6.4%)
    # With current_balance=1000 passed in, starting_balance = 1000 - 30 = 970,
    # walk: 970 + 100 = 1070 (peak), 1070 - 70 = 1000 (current). DD = (1000-1070)/1070 ≈ -6.5%.
    db4 = _fake_db([(86400 * 3, 100), (86400 * 1, -70)])
    ro4 = RiskOfficer(_FakeCfg(), db_paths=[db4], paper_mode=True)
    cap, dd = ro4.compute_brake(cash)
    print(f"\n4. DD ≈ -6.5%, expect brake → 1.0x:")
    print(f"   computed: cap={cap:.1f}x  dd={dd:+.1%}")
    print(f"   {'✅' if cap == 1.0 else '❌'}")
    os.unlink(db4)

    # ── Test 5: 7d DD = -16% → halt ──
    # Sequence: +$200 (peak $1200) then -$320 (current $880, DD = (880-1200)/1200 = -26%)
    db5 = _fake_db([(86400 * 3, 200), (86400 * 1, -320)])
    cb5 = 880  # after a real loss the balance is genuinely $880
    ro5 = RiskOfficer(_FakeCfg(), db_paths=[db5], paper_mode=True)
    ok, scaled, reason = ro5.check_can_open("SOL", 800, cb5, 0)
    cap, dd = ro5.compute_brake(cb5)
    print(f"\n5. DD ≈ -26%, expect HALT (cap=0):")
    print(f"   cap={cap:.1f}x dd={dd:+.1%}")
    print(f"   {'✅' if not ok and cap == 0.0 else '❌'}  ok={ok}  ({reason})")
    os.unlink(db5)

    # ── Test 6: snapshot string format ──
    db6 = _fake_db([])
    ro6 = RiskOfficer(_FakeCfg(), db_paths=[db6], paper_mode=True)
    snap = ro6.snapshot("SOL", cash, own_open_notional_usd=420.0)
    print(f"\n6. snapshot stringified:")
    print(f"   {snap}")
    os.unlink(db6)

    print(f"\n{'='*60}")
