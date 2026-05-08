# Bayesian Logit-Space Signal Combination for Regime-Aware Stacking

**Date:** 2026-04-20  
**Source:** u/nexussim on Moltbook — "Bayesian Update in Logit Space: A Key to Enhanced Trading Performance"  
**URL:** https://www.moltbook.com/m/trading  

---

## The Insight

AMATE (live trading bot on Moltbook platform):
- Uses a "3-edge stack" — multiple signal layers combined via **sum of log-likelihood ratios** (logit-space Bayesian updating)
- Result: 12% WR improvement vs prior method
- Key behavior noted: the logit-space aggregation specifically helped the bot **"identify regime flips and adjust its strategy accordingly"**

The mechanism: instead of asking each signal layer "yes/no, is this a valid entry?" and AND-ing or majority-voting the results, you ask each layer "what is the likelihood ratio of a winning trade given this signal state?" — then sum those in logit space. The posterior is a single probability that naturally degrades when any layer is out-of-distribution for its training regime.

---

## Why This Is Different From the 04-14 and 04-17 Escalations

Prior escalations proposed:
- **04-14**: Add a regime confidence score → 3-band position sizer
- **04-17**: Replace binary gate with continuous `score_current_regime()` function

Those are about *computing regime confidence separately and clamping position size*.

This insight is about the **combination method for the signal stack itself**. If the 4 layers (StochRSI + Bollinger + order flow + regime gate) currently feed into a threshold vote or sequential AND-gate, switching to logit-space combination would:

1. Make regime mismatch **visible in the posterior probability** rather than requiring a separate regime score computation
2. Allow the stack to self-degrade gracefully when regime shifts — the regime gate layer's LLR naturally dominates the sum when its signal is strong, and contributes near-zero when it's out-of-distribution
3. Preserve mean-reversion edge in mixed regimes (StochRSI + BB still vote for an entry, regime LLR is near-neutral → posterior is moderate → take a reduced-size trade)

This complements the 04-14/17 work: the confidence-weighted position sizer can use the logit-space posterior directly as its confidence score, replacing the need for a separate `score_current_regime()` function.

---

## Current Sniper Stack (assumed)

```
Layer 1: StochRSI          → overbought/oversold binary signal
Layer 2: Bollinger Bands   → price relative to band edges binary signal  
Layer 3: Order flow        → delta divergence binary signal
Layer 4: Regime gate       → bear/neutral/bull classifier (binary)

Current combination (assumed): all 4 must agree OR 3-of-4 threshold vote
```

---

## Proposed Change

For each layer, calibrate a **log-likelihood ratio** using the 180d training window:

```python
# For each layer i, measure:
# P(winning trade | signal_i = positive) and P(winning trade | signal_i = neutral/negative)
# LLR_i = log( P(win | positive) / P(win | neutral) )

# At entry decision time:
logit_prior = log(base_win_rate / (1 - base_win_rate))  # e.g. log(0.811/0.189) = 1.46
logit_posterior = logit_prior + sum(LLR_i for all active layers)
posterior_prob = sigmoid(logit_posterior)

# Position sizing using posterior:
if posterior_prob > 0.75:     full_size
elif posterior_prob > 0.55:   half_size
elif posterior_prob > 0.40:   quarter_size or skip
else:                         skip
```

When regime gate layer is in mismatch:
- Its LLR for the current regime would be near 0 (trained on bear; bull conditions have lower predictive power)
- The posterior naturally drops from the full-stack value toward the base rate
- The position sizer automatically reduces without a separate regime circuit breaker

---

## Calibration Requirements

1. For each of the 4 layers, need to compute: win rate given signal positive vs signal neutral/negative across the 180d training window.
2. The regime gate layer's LLR should be computed on *regime-match* (does current regime resemble training regime?) rather than the regime label itself.
3. After calibration, track whether live posterior_prob is a calibrated predictor of actual WR — if posterior says 0.70 but live WR on those entries is 0.50, re-calibrate LLRs.

---

## Proposed Action

1. Pull 180d backtest trade log and compute per-layer LLRs
2. Implement `compute_posterior(signals)` function returning sigmoid probability
3. Replace current threshold-vote with posterior-gated position sizer
4. Log `entry_posterior` field on every live trade entry
5. After 50 live trades: plot actual WR per posterior decile to validate calibration

---

## Risk of Inaction

The current combination method is likely masking the regime mismatch signal: all 4 layers pass threshold individually (they were all trained on bear data and may still fire in up-biased market), so the AND-gate fires normally. The logit-space method would show the degraded posterior even when individual layers still fire, because the LLRs from an out-of-distribution regime are weaker.

---

*Insight note only. No code changes. Bring to live strategy conversation before touching sniper code.*
