"""PromotionBar: evaluates whether a shadow rule passes its promotion bar.

Reads:
  - Proposal yaml (defines bar thresholds + which shadow jsonl to read)
  - shadow_log_jsonl (fire events from the shadow rule)
  - sol_sniper.db trade_log (eventual close PnL for each entry)

Pairs each shadow fire with its matching close (by symbol + direction + entry_price +
post-fire timestamp), computes hit_rate vs 0.5 baseline, and returns:
  PROMOTE / KEEP_OBSERVING / RETIRE / RETIRE_BY_DEADLINE
with a metric receipt suitable for a contributor message or Moltbook adoption post.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .proposal import Proposal

IBITLABS_ROOT = Path("/Users/bonnyagent/ibitlabs")
DEFAULT_DB = IBITLABS_ROOT / "sol_sniper.db"

Decision = Literal["PROMOTE", "KEEP_OBSERVING", "RETIRE", "RETIRE_BY_DEADLINE"]


@dataclass
class PromotionDecision:
    decision: Decision
    metrics: dict
    receipt: str

    def to_dict(self) -> dict:
        return asdict(self)


class PromotionBar:
    """Wraps a Proposal + access to its shadow jsonl + the trade_log DB."""

    def __init__(self, proposal: Proposal, *, db_path: Path | None = None):
        self.proposal = proposal
        self.db_path = Path(db_path) if db_path else DEFAULT_DB

    def load_fires(self) -> list[dict]:
        rel = self.proposal.data["shadow_log_jsonl"]
        jsonl_path = IBITLABS_ROOT / rel if not Path(rel).is_absolute() else Path(rel)
        if not jsonl_path.exists():
            return []
        fires: list[dict] = []
        with jsonl_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    fires.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return fires

    def pair_with_closes(self, fires: list[dict]) -> list[dict]:
        if not fires or not self.db_path.exists():
            return [{"fire": f, "close": None, "pnl": None} for f in fires]

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            paired: list[dict] = []
            for fire in fires:
                symbol = fire.get("symbol")
                direction = fire.get("direction")
                entry_price = fire.get("entry_price")
                entry_ts = fire.get("entry_ts")
                if not all([symbol, direction, entry_price, entry_ts]):
                    paired.append({"fire": fire, "close": None, "pnl": None})
                    continue
                cur.execute(
                    """
                    SELECT id, symbol, direction, entry_price, exit_price, pnl, timestamp
                    FROM trade_log
                    WHERE side = 'SELL'
                      AND exit_price IS NOT NULL
                      AND symbol = ?
                      AND direction = ?
                      AND ABS(entry_price - ?) < 0.05
                      AND timestamp >= ?
                      AND timestamp < ? + 86400 * 14
                    ORDER BY timestamp ASC
                    LIMIT 1
                    """,
                    (symbol, direction, entry_price, entry_ts, entry_ts),
                )
                row = cur.fetchone()
                if row:
                    paired.append({"fire": fire, "close": dict(row), "pnl": row["pnl"]})
                else:
                    paired.append({"fire": fire, "close": None, "pnl": None})
            return paired
        finally:
            conn.close()

    def evaluate(self) -> PromotionDecision:
        # Integrity re-check (proposed by riverholybot, Moltbook 2026-05-12):
        # re-run validate_all() at PROMOTE entry to catch yaml mutation between
        # submit and review. If any constraint now fails, the bar can't trust
        # its own input — return RETIRE with the first violation as receipt.
        integrity_violations = self.proposal.validate_all()
        if integrity_violations:
            first = integrity_violations[0]
            return PromotionDecision(
                decision="RETIRE",
                metrics={
                    "integrity_check": "failed",
                    "violations": len(integrity_violations),
                    "first_constraint": first.constraint,
                },
                receipt=(
                    f"yaml integrity check failed at evaluate() entry "
                    f"([{first.constraint}] {first.detail}). "
                    f"Proposal yaml may have been mutated since submission. "
                    f"Memory rule: {first.memory_rule}."
                ),
            )

        bar = self.proposal.data["promotion_bar"]
        proposed_at = self._parse_ts(self.proposal.data["proposed_at"])
        retire_days = bar["retire_after_days"]
        now = datetime.now(timezone.utc)
        days_observed = (now - proposed_at).days

        fires = self.load_fires()
        paired = self.pair_with_closes(fires)

        n_total = len(fires)
        n_paired = sum(1 for p in paired if p["pnl"] is not None)
        wins = sum(1 for p in paired if (p["pnl"] or 0) > 0)
        hit_rate = (wins / n_paired) if n_paired else None
        spread_pp = ((hit_rate - 0.5) * 100) if hit_rate is not None else None

        metrics = {
            "total_entries": n_total,
            "paired_closes": n_paired,
            "wins": wins,
            "hit_rate": hit_rate,
            "hit_rate_spread_vs_baseline_pp": spread_pp,
            "days_observed": days_observed,
            "min_entries_required": bar["min_entries"],
            "min_observation_days_required": bar["min_observation_days"],
            "retire_after_days": retire_days,
            "min_hit_rate_spread_pp": bar["min_hit_rate_spread_pp"],
        }

        # 1) Hard deadline expired with insufficient data → retire by deadline
        if days_observed >= retire_days and (
            n_total < bar["min_entries"] or hit_rate is None
        ):
            return PromotionDecision(
                decision="RETIRE_BY_DEADLINE",
                metrics=metrics,
                receipt=(
                    f"{days_observed}d elapsed >= retire_after_days={retire_days}; "
                    f"collected {n_total}/{bar['min_entries']} entries. "
                    "Archive as anti-pattern."
                ),
            )

        # 2) Window not closed and not enough data → keep observing
        if days_observed < bar["min_observation_days"] or n_total < bar["min_entries"]:
            return PromotionDecision(
                decision="KEEP_OBSERVING",
                metrics=metrics,
                receipt=(
                    f"{days_observed}/{bar['min_observation_days']}d observed, "
                    f"{n_total}/{bar['min_entries']} entries collected. Continue."
                ),
            )

        # 3) Enough data — check signal strength
        if hit_rate is None:
            return PromotionDecision(
                decision="KEEP_OBSERVING",
                metrics=metrics,
                receipt="No paired closes yet; cannot compute hit-rate.",
            )

        min_spread = bar["min_hit_rate_spread_pp"]
        if abs(spread_pp) < min_spread:
            decision: Decision = "RETIRE" if days_observed >= retire_days else "KEEP_OBSERVING"
            return PromotionDecision(
                decision=decision,
                metrics=metrics,
                receipt=(
                    f"hit_rate={hit_rate:.1%} spread={spread_pp:+.1f}pp < min={min_spread}pp. "
                    "Signal too weak."
                ),
            )

        # 4) Direction match (if required)
        if bar.get("direction_match_required"):
            direction = self.proposal.data["direction"]
            if direction == "long_bias" and spread_pp < 0:
                return PromotionDecision(
                    decision="RETIRE",
                    metrics=metrics,
                    receipt=(
                        f"Hypothesis direction=long_bias but observed spread="
                        f"{spread_pp:+.1f}pp negative. Direction-flipped = falsified."
                    ),
                )
            if direction == "short_bias" and spread_pp > 0:
                return PromotionDecision(
                    decision="RETIRE",
                    metrics=metrics,
                    receipt=(
                        f"Hypothesis direction=short_bias but observed spread="
                        f"{spread_pp:+.1f}pp positive. Direction-flipped = falsified."
                    ),
                )

        return PromotionDecision(
            decision="PROMOTE",
            metrics=metrics,
            receipt=(
                f"{n_total} entries over {days_observed}d, hit_rate={hit_rate:.1%}, "
                f"spread={spread_pp:+.1f}pp >= {min_spread}pp. Ready for entry-gate re-spec."
            ),
        )

    @staticmethod
    def _parse_ts(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
