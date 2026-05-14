"""EdgeHalflifeMonitor: rolling-window decay signal for live and shadow strategies.

The harness already gates shadow -> live with PromotionBar (point-in-time threshold).
What it didn't watch: an already-live rule whose edge decays. Regime cycling has a
shorter half-life than a non-adaptive strategy's effective period, so PF can drift
from 1.4 -> 1.0 -> 0.8 without any single review noticing.

This module gives each rule (and the whole-bot baseline) three rolling windows
(30 / 60 / 90 days) of hit_rate + profit_factor, plus a simple decay classifier.
Output is observation-only -- no control flow, no auto-archive. It feeds rollback
status; an operator (or, later, a launchd job) decides whether to archive.

Modes
-----
- Baseline: read sol_sniper.db trade_log directly, filtered by strategy_version +
  instance_name. Answers "is v5.1 itself decaying right now?"
- Per-rule: read a proposal's shadow jsonl, pair with closes (mirrors PromotionBar),
  compute windows. Answers "is the shadow signal degrading as we observe it?"
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .proposal import Proposal

IBITLABS_ROOT = Path("/Users/bonnyagent/ibitlabs")
DEFAULT_DB = IBITLABS_ROOT / "sol_sniper.db"

DecayStatus = Literal["healthy", "degrading", "decayed", "insufficient_data"]

WINDOWS_DAYS = (30, 60, 90)
SECONDS_PER_DAY = 86_400

# Decay classification thresholds. Tuned conservative; meant to flag, not auto-act.
MIN_PAIRED_FOR_SIGNAL = 5         # below this in 30d window -> insufficient_data
MIN_PAIRED_FOR_DECAYED = 10       # below this we won't call "decayed" even if hit_rate < 0.5
PF_DROP_RATIO = 0.70              # 30d PF < 90d PF * 0.70 -> degrading
HIT_RATE_DROP_PP = 10.0           # 30d hit_rate - 90d hit_rate < -10pp -> degrading


@dataclass
class WindowMetrics:
    window_days: int
    n_paired: int
    wins: int
    losses: int
    hit_rate: float | None
    pnl_total: float
    profit_factor: float | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EdgeStatus:
    target_id: str
    mode: Literal["baseline", "rule"]
    status: DecayStatus
    windows: list[WindowMetrics] = field(default_factory=list)
    receipt: str = ""
    last_close_at: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["windows"] = [w.to_dict() for w in self.windows]
        return d


def _window_metrics(paired: list[dict], window_days: int, now_ts: float) -> WindowMetrics:
    """paired = list of {pnl: float, timestamp: float}. Filter by window, summarize."""
    cutoff = now_ts - window_days * SECONDS_PER_DAY
    sub = [p for p in paired if p["timestamp"] >= cutoff and p["pnl"] is not None]
    n = len(sub)
    wins = sum(1 for p in sub if p["pnl"] > 0)
    losses = sum(1 for p in sub if p["pnl"] < 0)
    hit_rate = (wins / n) if n else None
    pnl_total = sum(p["pnl"] for p in sub)
    gains = sum(p["pnl"] for p in sub if p["pnl"] > 0)
    drains = -sum(p["pnl"] for p in sub if p["pnl"] < 0)
    pf = (gains / drains) if drains > 0 else (None if gains == 0 else float("inf"))
    return WindowMetrics(
        window_days=window_days,
        n_paired=n,
        wins=wins,
        losses=losses,
        hit_rate=hit_rate,
        pnl_total=pnl_total,
        profit_factor=pf,
    )


def _classify(windows: list[WindowMetrics]) -> tuple[DecayStatus, str]:
    """Decay heuristic. Walks 30d vs 90d. Returns (status, receipt)."""
    by_w = {w.window_days: w for w in windows}
    w30, w90 = by_w.get(30), by_w.get(90)

    if w30 is None or w30.n_paired < MIN_PAIRED_FOR_SIGNAL:
        return "insufficient_data", (
            f"30d n_paired={w30.n_paired if w30 else 0} < {MIN_PAIRED_FOR_SIGNAL}; "
            "no decay claim possible yet."
        )

    # Decayed = recent window is itself failing, with enough sample.
    if (
        w30.n_paired >= MIN_PAIRED_FOR_DECAYED
        and w30.hit_rate is not None
        and w30.hit_rate < 0.5
        and w30.profit_factor is not None
        and w30.profit_factor != float("inf")
        and w30.profit_factor < 1.0
    ):
        return "decayed", (
            f"30d hit_rate={w30.hit_rate:.1%}, PF={w30.profit_factor:.2f}, "
            f"n={w30.n_paired}. Recent window is unprofitable on both axes."
        )

    # Degrading = sharp drop from 90d -> 30d, even if 30d still net positive.
    if w90 and w90.n_paired >= MIN_PAIRED_FOR_SIGNAL:
        # PF drop
        if (
            w30.profit_factor is not None
            and w90.profit_factor is not None
            and w90.profit_factor not in (None, float("inf"))
            and w90.profit_factor > 0
            and w30.profit_factor < w90.profit_factor * PF_DROP_RATIO
        ):
            return "degrading", (
                f"PF dropped from {w90.profit_factor:.2f} (90d) to "
                f"{w30.profit_factor:.2f} (30d) -- below {int(PF_DROP_RATIO*100)}% of trailing."
            )
        # Hit-rate drop
        if (
            w30.hit_rate is not None
            and w90.hit_rate is not None
            and (w30.hit_rate - w90.hit_rate) * 100 < -HIT_RATE_DROP_PP
        ):
            return "degrading", (
                f"hit_rate dropped from {w90.hit_rate:.1%} (90d) to "
                f"{w30.hit_rate:.1%} (30d) -- worse than -{int(HIT_RATE_DROP_PP)}pp."
            )

    return "healthy", (
        f"30d n={w30.n_paired}, hit_rate={w30.hit_rate:.1%}"
        + (f", PF={w30.profit_factor:.2f}" if w30.profit_factor is not None else "")
        + ". No decay signal."
    )


class EdgeHalflifeMonitor:
    """Computes rolling-window decay status for baseline trade_log or a proposal."""

    def __init__(self, *, db_path: Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB

    def baseline(
        self,
        *,
        strategy_version: str = "hybrid_v5.1",
        instance_name: str = "live",
    ) -> EdgeStatus:
        """Whole-bot decay over the trade_log filtered by strategy_version + instance."""
        target_id = f"baseline:{strategy_version}/{instance_name}"
        if not self.db_path.exists():
            return EdgeStatus(
                target_id=target_id,
                mode="baseline",
                status="insufficient_data",
                receipt=f"DB not found at {self.db_path}",
            )

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT timestamp, pnl
                FROM trade_log
                WHERE side = 'SELL'
                  AND exit_price IS NOT NULL
                  AND strategy_version = ?
                  AND instance_name = ?
                ORDER BY timestamp ASC
                """,
                (strategy_version, instance_name),
            )
            paired = [{"pnl": r["pnl"], "timestamp": r["timestamp"]} for r in cur.fetchall()]
        finally:
            conn.close()

        return self._build_status(target_id, "baseline", paired)

    def for_proposal(self, proposal: Proposal) -> EdgeStatus:
        """Per-rule decay using PromotionBar's pairing logic."""
        from .promotion_bar import PromotionBar  # local import to avoid cycles

        target_id = proposal.data["proposal_id"]
        bar = PromotionBar(proposal, db_path=self.db_path)
        fires = bar.load_fires()
        paired_raw = bar.pair_with_closes(fires)
        # Pull each pair's timestamp from the matching close (or the fire's entry_ts).
        paired: list[dict] = []
        for p in paired_raw:
            if p["pnl"] is None:
                continue
            close = p.get("close") or {}
            ts = close.get("timestamp") or p["fire"].get("entry_ts")
            if ts is None:
                continue
            paired.append({"pnl": p["pnl"], "timestamp": float(ts)})
        return self._build_status(target_id, "rule", paired)

    @staticmethod
    def _build_status(
        target_id: str,
        mode: Literal["baseline", "rule"],
        paired: list[dict],
    ) -> EdgeStatus:
        now_ts = datetime.now(timezone.utc).timestamp()
        windows = [_window_metrics(paired, d, now_ts) for d in WINDOWS_DAYS]
        status, receipt = _classify(windows)
        last_close = max((p["timestamp"] for p in paired), default=None)
        last_close_iso = (
            datetime.fromtimestamp(last_close, tz=timezone.utc).isoformat(timespec="seconds")
            if last_close
            else None
        )
        return EdgeStatus(
            target_id=target_id,
            mode=mode,
            status=status,
            windows=windows,
            receipt=receipt,
            last_close_at=last_close_iso,
        )
