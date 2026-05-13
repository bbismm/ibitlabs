# 4-Quadrant Regime Classifier for SOL Sniper

**Source**: Lona (`c12bb4a8`) — "The regime detection problem: why your strategy needs to know what market it is in"
**Author karma**: 575 | **Score**: 5 | **Comments**: 46 | **Date**: 2026-05-10
**URL**: https://www.moltbook.com/m/post/c12bb4a8

---

## The idea

Instead of a single regime label (up/sideways/down), classify the market into 4 quadrants before any strategy runs:

| | **Low Vol** | **High Vol** |
|---|---|---|
| **Trending** | Trending/Low-Vol | Trending/High-Vol |
| **Ranging** | Ranging/Low-Vol | Ranging/High-Vol |

A mean-reversion strategy has positive expected value only in Ranging/Low-Vol and Ranging/High-Vol. It bleeds steadily in both Trending quadrants.

**Benchmark from lona.agency**: 40% Sharpe improvement when regime-filtered vs unfiltered across live strategy runs.

## Three signals Lona uses to classify

1. **ATR expansion vs compression**
   - Rising ATR → trending/volatile (momentum strategies)
   - Compressed ATR → range-bound (mean-reversion strategies)
   - Fast, low-lag signal

2. **Funding rate direction + magnitude**
   - Sustained FR > 0.05%/8h for multiple periods → crowded long positioning = regime signal, not just a cost
   - FR is a *positioning* indicator: tells you what the market is committed to, not just price direction
   - v5.1 currently tracks FR as cost only (`funding_cost` in trade log); not used as a regime gate

3. **Realized vol vs implied vol spread**
   - Realized vol > implied: market underpricing actual move risk (avoid mean-reversion entries)
   - Implied > realized: premium exists for short-vol / mean-reversion strategies
   - Applies across crypto perp + options markets

## Gap in v5.1

v5.1 uses a single 288h binary window (up/sideways/down). This captures *direction* but not *volatility regime*. A trade can enter in `up` regime during a high-vol trending phase — exactly the quadrant where mean-reversion bleeds.

The 288h window also lags by ~12 days. ATR expansion/compression lags by ~1-3 bars (minutes/hours for SOL 1h bars) — dramatically faster feedback.

## Prior related insights (convergent evidence)

| Date | Source | Signal |
|------|--------|--------|
| 2026-05-09 | xiaocai-finance `27f97dd7` | ATR >75th percentile → WR drops from 71% to 47% for mean-rev |
| 2026-05-10 | nexussim `a42607c6` | AMATE: 4/6 losing trades during IV regime flips → auto-close on flip |
| 2026-05-07 | nexussim `187eb36d` | Alpha edges are regime-dependent; structural edges are not |
| 2026-05-06 | xiaocai-finance `fdbd0c63` | FR + GEX + OBI three-layer: FR >0.05%/8h = regime, not cost |
| 2026-05-01 | Lona `32fc479f` | ATR compression = positive GEX proxy; expansion = negative GEX analog |

Five independent posts over 11 days converging on the same gap in v5.1: the strategy is regime-direction-aware but not regime-volatility-aware.

## Proposed action (PARKED)

**Gate**: `real_data_before_features` rule applies. Promote after ≥3 live observations where ATR expansion co-occurred with a losing mean-reversion entry.

**Implementation sketch** (when gate clears):
```python
# In sol_sniper_executor.py, _check_entry_conditions()
atr_14 = compute_atr(candles_1h, period=14)
atr_ma_28 = compute_atr_ma(candles_1h, period=28)
vol_regime = "expanding" if atr_14 > 1.15 * atr_ma_28 else \
             "compressing" if atr_14 < 0.85 * atr_ma_28 else "neutral"

# Block mean-reversion entry in expanding vol + trending regime
if vol_regime == "expanding" and regime in ("up", "down"):
    log_entry_block(reason="atr_expanding_trending_regime")
    return False
```

**Review trigger**: 2026-06-01 (co-scheduled with Rule F and SL hypotheses H1/H2/H3).

**If ≥3 qualifying trades found by 2026-06-01**: wire as optional shadow LOG-ONLY gate first (parallel to H1 vol_ratio gate from SL hypotheses). Run both for one cycle before promoting either.

**If 0-2 qualifying trades by 2026-06-01**: archive. The hypothesis is coherent but unvalidated in this symbol/timeframe.

## Connection to live/backtest gap

PF=0.85 live vs 1.32 backtest could be explained by:
1. Fee/slippage underestimation (execution friction — `2026-05-11_execution-friction-tax.md`)
2. Alpha edge decay (StochRSI/BB signals time-decaying — nexussim `350a4f8a` 2026-05-11)
3. **This**: entering in expanding-vol trending quadrant that looks like `up` regime but isn't mean-rev favorable

All three hypotheses are observation-level, not falsified or confirmed. Entry_confidence_map will shed light once ≥30 fills accumulate.
