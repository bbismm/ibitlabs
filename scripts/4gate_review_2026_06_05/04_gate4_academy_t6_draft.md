# Gate 4 — Academy T6 update draft

**This is a content template, not a script.** After Gates 1-3 land, edit this file to match the actual outcome, then port the prose into `~/ibitlabs/web/public/academy.html` lesson T6.

**Why this matters:** the original T6 lesson teaches "When the data says something isn't working, the right call is to turn it off. That's what makes this experiment real." Un-doing the disable publicly without explaining the data contradicts the published epistemics — readers lose trust in the experiment's stated discipline.

---

## Decision branch (fill in based on Gates 1-3 verdict)

### Branch A — All gates clear → swap in (grid + tighter trailing)

> **2026-06-05 update.** After 30 days of shadow data and a re-decomposition over the same 120-day window the original disable used, the combined (grid + trailing 0.4%/0.5%) variant cleared the bar that v1 had failed. New numbers:
>
> | | live (v5.1, --no-grid) | shadow (combined) |
> |---|---|---|
> | Closed trades | [N_LIVE] | [N_SHADOW] |
> | Regime coverage | [LIVE_REGIMES] | [SHADOW_REGIMES] |
> | PF over 120d | 1.32 | [PF_NEW] |
> | Slippage-adjusted edge | baseline | [EDGE_AFTER_SLIPPAGE] |
>
> What changed: [explain — e.g. "shadow's regime-aware grid avoided the counter-trend leg that drove the original −$16 / 7L1W loss"]. What didn't: the entry rule, the regime classifier, the safety floor, the circuit breaker.
>
> Live now runs grid ON + trailing 0.4%/0.5%. The original disable was the right call given what we knew on 2026-04-20; this swap is the same discipline running on a larger evidence base.

### Branch B — Gate 1 or 2 fails → defer

> **2026-06-05 update.** The 30-day shadow review confirmed [the failing gate]. Mean reversion still runs solo on live. Next re-evaluation: [DATE — typically +30d on next maturation cycle].
>
> Specifically: shadow accumulated [N] closed trades against the 30-trade bar / regime distribution covered [BUCKETS] of the required ≥2 buckets × ≥5 trades. The bar is the bar; small-sample wins don't move it.

### Branch C — Decomposition shows only one lever works

> **2026-06-05 update.** Decomposing the candidate (grid + trailing 0.4%/0.5%) over 120d showed [the working lever] alone delivered the gap; the combined version had [confounding behavior]. Adopted [working lever] only on live; the other stays disabled.
>
> Original PF baseline: 1.32. [Working lever] alone: [PF]. Combined: [PF]. Single-lever cleanly beats the combined → adopt single.

---

## Process checklist (after committing to a branch)

- [ ] Edit `web/public/academy.html` T6 — append (don't overwrite) the historical paragraph
- [ ] Update `~/ibitlabs/README.md` line about "currently running mean-reversion-only on the live SOL bot" if branch A or C
- [ ] Update memory: `feedback_no_grid_reenable_without_review.md` — append outcome + the specific data that crossed each gate
- [ ] Update memory: retire/archive `project_c_hook_2026_05_12.md` if Path C data-collection mission completed; OR extend it as ongoing observability
- [ ] Trigger sniper plist swap per `sniper_swap_prep_2026_05_11.md` lines 154-172 ONLY IF branch A or C
- [ ] Next saga-daily chapter — auto-handles the trading event (verify it lands)
- [ ] Next Moltbook brand-builder post — auto-anchors on the swap event (verify it lands within 1 fire)

## Anti-patterns to refuse

- **Don't quietly remove the original "Why It Was Disabled" paragraph.** Append, don't overwrite — the historical record is part of the teaching.
- **Don't frame the swap as "we figured it out" or "v2 is better."** Frame as "data updated, decision updated."
- **Don't announce on Moltbook before the swap is live AND verified.** Sequence: code change → plist reload → 1h smoke → THEN brand-builder anchor.
- **Don't use the swap event as a "look how disciplined we are" marketing post.** The discipline is in the process, not the headline. Let the data carry it.

## Cross-reference

- Memory: `feedback_no_grid_reenable_without_review.md` — original disable rationale + 4-gate locked
- Memory: `project_v52_spec_phase_a.md` — RETIRED 05-06; load-bearing for the "PF<1.00 should point to substrate, not architecture" line
- Memory: `project_c_hook_2026_05_12.md` — the observability hook that fed Gate 1's regime-coverage half
- Prep doc: `~/ibitlabs/notes/sniper_swap_prep_2026_05_11.md` — full design context
