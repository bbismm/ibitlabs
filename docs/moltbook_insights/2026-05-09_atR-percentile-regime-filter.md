# ATR Percentile as Volatility-Regime Switch for Mean Reversion Entry

**Source**: u/xiaocai-finance (k:76), post `27f97dd7`, https://www.moltbook.com/m/post/27f97dd7, 2026-05-09
**Extends**: FR+OI mean reversion framework (u/xiaocai-finance, `fdbd0c63`, 2026-05-06)

## Hypothesis

ATR percentile rank (relative to historical ATR distribution) acts as a volatility-regime gate:

- ATR in 25th-75th percentile (moderate vol) → FR+OI mean reversion WR = 71%
- ATR > 75th percentile (high vol) → WR drops to 47% → switch to momentum
- ATR < 25th percentile (dead vol) — not specified; likely needs separate treatment

Mechanism: high ATR means a directional move is already underway. Mean reversion entries fight the trend. "Extreme" StochRSI/BB signals at high ATR confirm a new regime, not a reversion target.

## Supporting Evidence (per `feedback_real_data_before_features.md` ≥3 rule)

1. xiaocai-finance 05-06 (`fdbd0c63`): GEX sign as vol proxy — negative GEX → compress hold to 6-8h (same intuition: vol regime changes optimal hold)
2. xiaocai-finance 05-09 (`27f97dd7`): explicit ATR percentile thresholds with WR numbers
3. shekel-skill 05-07 (`9530285e`): multi-layer regime stack, "per-token bias" as first filter — volatility asymmetry implied
4. nexussim 05-09 (`ba7f0124`): IV regime flip detection = 42% of AMATE returns (biggest component) — regime-detection layer dominates signal layer

~4 data points, all same direction. Threshold for hypothesis activation met. But author karma is low (k:76) — no high-karma corroboration yet.

## Applied to v5.1

v5.1 does not filter entries by ATR percentile. `atr_normalized` is logged in `entry_confidence_map.jsonl` (when it populates) but is not a gating condition. During high-vol windows, StochRSI+BB+OFI may fire with same position size as low-vol windows, but inherent edge may be sub-50%.

## Do NOT Implement Until All Triggers Met

1. `entry_confidence_map.jsonl` has ≥30 fills (0 since 2026-05-02 restart — investigate if still 0 by 2026-05-16)
2. ≥10 of those fills fall in ATR >75th percentile bucket
3. Live WR in that ATR bucket is measurably below 50%

**If triggers met**: wire ATR percentile >75th as entry scaling factor (0.5x size or skip) in v5.1 as a shadow gate for 30 trades before full activation. Within v5.1 architecture (entry-only, no exit changes).

**If entry_confidence_map stays empty past 2026-05-16**: investigate write path — possible JSONL path mismatch or no new entries since bot restart.

## Review date: 2026-06-01 (aligned with Rule F review)
