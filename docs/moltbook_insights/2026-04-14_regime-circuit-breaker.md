# Regime Detection as a Confidence-Gated Circuit Breaker

**Source:** u/novav on https://www.moltbook.com/m/trading (4d ago, 75 comments)
**Date found:** 2026-04-14
**Relevance:** Directly addresses current sniper regime mismatch (strategy trained on 180d bear, current 30d is up-biased)

---

## Core Insight

Stop asking "what regime are we in?" and start asking "how confident are we that the current regime matches the one our strategy was validated in?"

Regime detection is not a classifier — it is a **circuit breaker**.

When confidence drops below threshold: reduce exposure + widen risk limits. Do NOT switch strategies. Wait until the new regime stabilizes enough to measure.

---

## What Actually Breaks During Regime Transitions (per the post)

1. **Correlation structure collapse** — relationships the strategy learned (e.g. SOL correlation with BTC/funding rate) may invert or disappear. Agent keeps trading the old relationship; every fill is now adverse selection.

2. **Liquidity topology changes** — execution cost increases 3-5x during transitions lasting <2h. Standard execution patterns fail before any price-level signal fires.

3. **Signal validity decay is non-monotonic** — signals briefly get *stronger* as other participants react predictably, then collapse. An agent monitoring signal strength will see a brief improvement and increase confidence right before the floor drops.

---

## Proposed Action for Sniper

**Current state:** Sniper has a regime gate (bear/neutral/bull classifier) but no confidence score on regime match. It either trades or doesn't — no partial-exposure mode.

**Proposed addition:**

1. Add a `regime_confidence` metric: rolling similarity between current 30d market stats (vol, trend slope, mean-reversion half-life) and the 180d training window stats.

2. Define three bands:
   - `confidence > 0.7` → normal position sizing
   - `0.4 < confidence < 0.7` → halve position size, widen stops 1.5x
   - `confidence < 0.4` → paper-only or halt live entries

3. Log confidence score per trade alongside the existing regime label.

**Why this beats the current approach:** Current gate is binary (valid regime / not). The mismatch is in the *gray zone* — regime looks passable but assumptions are silently degrading. The confidence band catches that gray zone.

---

## Do NOT implement from this file

This is an insights document only. Bring to a live strategy conversation for review before touching any sniper code.
