# Multi-symbol expansion (SOL → SOL+ETH) — Architecture DD

**Date:** 2026-05-04
**Status:** Decision document, pre-implementation
**Goal:** Extend v5.1 from SOL-only perp to SOL+ETH perp, as the primary acceleration lever for $1k → $10k.
**Why this exists:** v5.1 is live on SOL since 2026-04-20. Two weeks in, the throughput bottleneck is N (trades per day), not edge per trade. Multi-symbol is the highest-leverage way to raise N while validating that v5.1's edge generalizes — both effects compound.

This DD locks 4 architecture decisions before any code is written. Implementation, paper-mode validation, and live promotion follow as a separate plan.

---

## Decision context

We considered three paths to acceleration:
1. **Multi-symbol expansion (this DD):** scale N at constant edge, validate edge cross-symbol
2. **High-edge SOL-only strategy hunt:** seek 2-5% per-trade edge through multi-strategy ensemble or on-chain alpha
3. **Higher leverage / smaller stops:** mathematically faster, blows up the experiment under any adverse run

Path 1 won because:
- It validates v5.1's edge as method, not as SOL-specific lucky fit
- Validation timeline is shorter (more samples per unit time)
- Engineering risk is bounded (extending working code, not new research)
- Mission fit: "$1k holder can follow along" survives — readers can replicate the multi-symbol design as written

Path 2 (especially on-chain alpha) is parked as a future research track, not a critical path for the $10k milestone.

Path 3 is an explicit non-option per `feedback_no_upside_caps.md` framing: don't blow up the experiment to look fast.

---

## Decision #1 — Risk budget allocation

**Choice:** Static portfolio-level cap with risk-OFF dynamic brake.

```
Symbol-level allocation:    STATIC
  Portfolio max notional:   1.5x cash
  Per-symbol max:           1.0x cash
  Per-symbol min:           0.4x cash       (below this, fee drag is material)

Risk-OFF dynamic brake:     ON
  7d DD > 5%   →  portfolio cap → 1.0x
  7d DD > 10%  →  portfolio cap → 0.5x
  7d DD > 15%  →  portfolio cap → 0.0x  (full halt, manual reset)
  New equity high  →  reset to 1.5x

Per-trade sizing:           DYNAMIC by entry_confidence_map (Phase 3, deferred until ≥50 fills)

Cross-symbol alpha rotation: NONE
  Earliest reconsideration: ≥200 trades per symbol (~6-12 months out)
```

**Why static, not "smart" dynamic between symbols:**
- Dynamic alpha allocation needs ~thousands of samples per side. We will have ~60-90 in 90 days. Below that, the dynamic allocator is fitting noise and chasing reversion.
- Reflexivity: if allocation depends on recent performance, the strategy's behavior changes the data it's measuring against. Cannot separate "ETH did badly" from "we starved ETH last week."
- Static is teachable: a $1k holder can replicate "1.5x portfolio cap, 1.0x per-symbol cap." Dynamic-EMA-weighted regime-conditional allocation is not.

**Why dynamic in the safety direction:**
- Risk-OFF brake is a single-direction function: only reduces, never raises mid-cycle. No reflexivity, no chasing.
- DD trigger is defined, not estimated — no sample-size dependency.
- Stops a failing strategy from compounding losses while keeping the door open to recovery.

**Correlation note:** SOL and ETH have ~0.75-0.85 correlation in major moves. The 1.5x portfolio cap reflects this — both bots maxed out is ~1.5x crypto-beta exposure on the account. A single 8% crypto down-day at full exposure = ~12% account drawdown. Painful but survivable; would trigger the first risk-OFF brake step.

---

## Decision #2 — Regime detector: per-symbol, same algorithm

**Choice:** Each bot runs its own instance of v5.1's regime detector on its own symbol's price data. Algorithm shared, data independent. Parameters initially identical to SOL's live values; any divergence requires evidence and gets logged as a contributor frame candidate.

**Considered and rejected:**
- **Single macro detector (BTC.D-driven)** — clean coherence, but ignores symbol-level regime asymmetry, which is exactly what multi-symbol is supposed to capture. Also imposes new untested signal on top of existing v5.1 logic.
- **Per-symbol + portfolio macro brake layer** — most defensible, but the risk-OFF brake (Decision #1) already provides portfolio-level safety. Adding macro-regime brake is over-engineering before we know we need it.

**Why per-symbol same-algorithm wins:**
- Most faithful extension of v5.1's existing methodology — we are testing whether the *method* generalizes, not inventing a new method
- Symbol-level regime divergence (SOL compression while ETH expansion) is the interesting signal we want to observe, not suppress
- Same-algorithm = same bug-fix surface: any v5.1 detector improvement automatically benefits both bots
- Generates a falsifiable claim: "v5.1's regime detector parameters tuned on SOL apply equally well to ETH." Either confirmed or learned-from — both are publishable

**Implementation note:** parameters (regime window 288h live / 120h shadow, ATR thresholds, vol_ratio cutoffs) start identical to SOL. Divergence is permitted only when:
1. ≥30 ETH trades have completed
2. Per-bucket hit-rate spread on ETH disagrees with SOL by ≥10pp on the same parameter
3. The proposed divergence is logged as a tuning frame in the contributor ledger

---

## Decision #3 — Per-symbol configuration: three-tier sharing

**Choice:** Configuration items split into three tiers by sharing semantics.

| Tier | What | Sharing | Rationale |
|---|---|---|---|
| 🔒 **Shared logic (single source)** | All entry/exit conditions, risk officer rules, confluence scoring, strategy_version tag, condition definitions | ❌ never per-symbol | Same strategy, not two strategies; bug fixes propagate; teaching narrative requires "one method" |
| 🔧 **Default shared, divergence requires evidence** | ATR multipliers, regime window hours, vol_ratio thresholds, min/max hold time, fee_cushion | ⚠️ initial = SOL values, can diverge after ≥30 ETH trades + documented evidence | This is the experiment: does v5.1 need per-symbol calibration? |
| 🔓 **Always per-symbol** | symbol identifier, fee schedule, min order size, tick size, margin/leverage requirement, contract spec | ✅ always per-symbol | Coinbase contract specs differ; sharing would silently misprice trades |

**Implementation:** single module `v5_1_config.py` exports `config_for(symbol: str) -> dict`. Symbol-specific overrides live in a small per-symbol section; default behavior is shared.

```python
# Sketch
SHARED_DEFAULTS = {
    "regime_window_hours": 288,
    "atr_multiplier_sl": 1.4,
    "vol_ratio_threshold": 1.2,
    "max_hold_hours_compound": 24,
    # ...all v5.1's tuned shared values
}

PER_SYMBOL_OVERRIDES = {
    "SOL": {
        "min_order_size": 0.1,
        "tick_size": 0.01,
        "fee_taker_bps": 8,
        "fee_maker_bps": 5,
        "fee_cushion_bps": 18,
    },
    "ETH": {
        "min_order_size": 0.01,
        "tick_size": 0.10,
        "fee_taker_bps": 8,
        "fee_maker_bps": 5,
        "fee_cushion_bps": 18,  # initial = SOL value, override only on evidence
    },
}
```

**Why this design reduces failure modes:**
- "Default shared" prevents accidental drift — no engineer can silently divergence a parameter without leaving a trail
- "Always per-symbol" tier prevents the worst-case bug class (one symbol's fee schedule applied to another's notional)
- Three-tier classification makes every parameter's intent explicit; reviewers can spot misclassifications

---

## Decision #4 — Dashboard / `/signals` presentation

**Choice:** Hero combined equity curve with per-symbol breakdown panels and a phantom "SOL-only counterfactual" reference line. SOL-only historical view preserved as a togglable filter.

```
/signals layout post-launch:

  ┌─────────────────────────────────────────────────────────┐
  │ HERO: Combined account equity, 2026-04-20 → now         │
  │   ─── Live (combined since multi-symbol launch)         │
  │   ─── Phantom SOL-only (counterfactual)                 │
  │   │   ↑ vertical line at multi-symbol launch date       │
  └─────────────────────────────────────────────────────────┘
  ┌──────────────────┐  ┌──────────────────┐
  │ SOL contribution │  │ ETH contribution │
  │ N trades, X% WR  │  │ N trades, X% WR  │
  │ PnL: $YY         │  │ PnL: $YY         │
  └──────────────────┘  └──────────────────┘
  ┌─────────────────────────────────────────────────────────┐
  │ Filters: [All] [SOL only] [ETH only] [Pre-multi-symbol] │
  └─────────────────────────────────────────────────────────┘
```

**Key designs:**

1. **Multi-symbol launch is a dated milestone**, marked by a vertical line on the equity chart. Public artifact: this date appears in the saga, contributor ledger, and any external write-up — readers can reference it.

2. **Phantom SOL-only counterfactual.** When ETH bot opens a position, the system records what SOL bot would have done at that moment (skip / hold / open). This builds a virtual SOL-only equity curve continuing forward from launch. Readers see directly: did multi-symbol help, hurt, or push sideways? The counterfactual is computed honestly — phantom trades use the same fees, slippage, and latency assumptions as live SOL trades.

3. **SOL-only historical view preserved.** `?view=sol_only` filter shows the original 04-20 → multi-symbol-launch period unchanged. SOL track record is never mutated by the expansion.

4. **Per-symbol attribution columns** in trade lists let readers and analysts segment performance.

**Why this serves the mission better than a simple combined view:**
- The phantom counterfactual makes "did expanding to ETH help?" a question the data answers, not a question we narrate
- Three possible outcomes (helped / neutral / hurt) all teach something — the dashboard can support any of them honestly
- SOL-only baseline being preserved means we don't lose 14+ days of established track record by re-anchoring the chart

---

## Implementation phases

```
Phase 0 — Health check (this week, ~1 hour)
  Confirm bot has been working since 2026-05-02 21:30 restart
  Verify Rule F shadow + entry_confidence_map + close-verify paths fire correctly

Phase 1 — Engineering DD (this week, ~1 day)
  This document. Once approved, implementation begins.

Phase 2 — Code (week 1-2)
  v5_1_config.py module with per-symbol config_for()
  ETH bot launchd job (com.ibitlabs.sniper-eth.plist), paper-mode default
  Risk officer extended with portfolio-level cap + risk-OFF brake
  Phantom SOL-only counterfactual recorder

Phase 3 — Paper-mode validation (week 3)
  ETH bot runs paper-mode for ≥7 days, ≥10 virtual trades
  Verify: regime detector outputs sensible per-symbol tags
  Verify: portfolio cap correctly arbitrates concurrent open requests
  Verify: phantom SOL-only line reconstructs the live SOL-only curve identically over the overlap window (sanity check)

Phase 4 — Live promotion (week 4, gated on Phase 3 passing)
  ETH bot live with capped sizing (0.4x cash max for first 10 trades)
  Risk officer's risk-OFF brake activated for combined account
  Update /signals layout to multi-symbol view
  Saga chapter publishes the multi-symbol launch as a dated event

Phase 5 — Post-launch monitoring (weeks 5+)
  Per-symbol parameter drift gates (per Decision #3 tier 2)
  ETH per-symbol max sizing raises to 1.0x after ≥30 trades + verified parameters
  Rule F first review: 2026-06-01
  Regime window 120h shadow review: 2026-05-27
  12h compound shadow review: 2026-05-23
```

---

## Rollback conditions

If, after live promotion, any of these occur — pause ETH bot (set `com.ibitlabs.sniper-eth` plist to disabled) and revert to SOL-only while we investigate:

1. **Combined drawdown ≥ 12% within 14 days of ETH live launch** — beyond what Risk-OFF brake handles, manual review required
2. **ETH bot's paper-mode hit rate diverges from SOL backtest by >25pp** in either direction (overfit or underfit signal)
3. **Phantom SOL-only counterfactual outperforms combined live by >5%** over 30 days — multi-symbol is hurting
4. **Per-symbol parameter divergence proposed > 3 times in 30 days** — strategy is overfit per-symbol, not generalizing
5. **Any cross-symbol bug** that mispriced a trade (wrong fee_cushion, wrong tick_size, wrong margin assumption) — pause until reviewer signs off

ETH-only is never preferred over SOL-only; we only roll back to SOL-only or full pause, never to ETH-only.

---

## Why this is the right move now

The cleanest unit of evidence for $1k → $10k is not a number — it's a methodology that any $1k holder can replicate. v5.1 SOL-only proves "we have a strategy that works on SOL." v5.1 SOL+ETH proves "we have a method that works on multiple liquid perps." The second claim is significantly more valuable as teaching, and significantly more defensible as edge.

The acceleration is real but not the only point. Multi-symbol is the moment v5.1 stops being "the SOL bot" and becomes "the framework" — that transition is what makes the rest of the journey to $10k a series of additions rather than a series of guesses.

---

**Author:** Bonny + Claude
**Reviewers:** none required for this DD; implementation reviewed before each phase
**Companion saga chapter:** to be drafted as "Day X · The day we let ETH in" (en + zh) referencing this DD
