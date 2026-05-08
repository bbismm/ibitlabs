# ATR Compression as Crypto GEX Regime Proxy

**Source**: u/Lona (k:507), https://www.moltbook.com/m/post/32fc479f, 2026-04-29
**Escalated by**: moltbook-trading-learn, 2026-05-01
**Proposed action**: Shadow experiment — add ATR compression filter as confirming log signal for regime gate

## The Insight

Lona built a crypto translation of sharkquant's dealer gamma (GEX) framework for agents without live options data. Core mapping:

- **ATR < 85% of 28-period ATR MA → compression regime** (positive GEX analog): dealers hedge against crowd, range is capped, mean reversion holds → sniper strategy has edge
- **ATR > 115% of 28-period ATR MA → expansion regime** (negative GEX analog): dealers hedge with crowd, trends extend violently → mean reversion bleeds → sniper should not be in

Strategy Lona tested:
- In compression: entry on BB lower band + RSI < 40. Exit at BB midline or −6% SL.
- In expansion: entry on BB upper band + EMA10 > EMA50 + RSI 50–80. Exit at BB midline or −6% SL / +12% TP.

BTC daily 2023–2025 backtest results pending (as of post date).

## Why This Matters for Sniper

The sniper's current regime gate uses a directional trend window (288h live, 120h shadow). The `project_regime_window_shadow.md` problem: the window captures trend direction but not volatility regime. Both states look identical to the trend detector:

- Bear trend + ATR compression → mean reversion intact (dealers capping range)
- Bear trend + ATR expansion → mean reversion bleeds (trends extend, dealer hedging amplifies)

The current regime mismatch concern is that bear-trained strategy is running in an up-biased regime. A secondary issue: even when trend is down, the strategy may enter during expansion sub-states where the mean-reversion assumption breaks.

## Proposed Shadow Experiment

Add `atr_regime` log field to `trade_log` (shadow mode — log only, no blocking). Logic:
1. Compute ATR(14) on 1H SOL-PERP candles
2. Compute 28-period SMA of ATR
3. Tag each entry: `atr_regime = "compression"` if ATR < 85% × ATR_MA, `"expansion"` if ATR > 115% × ATR_MA, `"neutral"` otherwise
4. Log alongside existing `regime`, `stochrsi`, `bb_width` fields
5. After 30+ trades: compute WR split by `atr_regime`; if compression WR is significantly higher than expansion WR, upgrade to a hard entry gate

Estimated scope: ~30 lines in `sol_sniper_executor.py`. Log-only flag is compatible with the "no structural changes until 30+ trades" rule from `feedback_12h_cap_rejected.md`.

## Conflicts / Contradictions Check

- Does NOT conflict with 288h/120h shadow regime window experiment — orthogonal axis (vol regime vs trend direction)
- Does NOT introduce profit caps (barred by `feedback_no_upside_caps.md`)
- Log-only in shadow mode = compatible with "no structural changes until 30 trades" constraint
- ATR is coincident, not leading — Lona is explicit about this limitation. Treat as confirming signal only, not primary entry gate

## Condition for Upgrade to Hard Gate

If after 30+ trades: compression WR ≥ expansion WR + 15pp → add ATR expansion as entry blocker.
If results are flat → discard; don't add noise to the signal stack.
