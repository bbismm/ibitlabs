# claude-trader · adaptive cadence design doc

**Status:** DESIGN — no code changes yet. Awaiting founder sign-off.
**Date:** 2026-05-25
**Author:** Bonny + Claude (drafted via founder-notes channel discussion)
**Related:** Phase A.5 (founder-notes / state-snapshot / EV-gate / missed-setups), founder-note v2 claim C3 (cadence_mismatch)

## Problem statement

Today claude-trader fires every 5 minutes via `com.ibitlabs.claude-trader` launchd plist — fixed cadence, 288 fires/day. Bonny's founder-note observation #3 (now claim C3 in the lineage) names a deeper issue than what Phase A's "reasoning length scales to state change" instruction addressed:

> Fixed cognition cadence vs variable market information rate → market in compression has near-zero information entropy, but the agent is forced to produce reasoning every 5 minutes → manufactures narrative, fake opportunity, overfits local candles.

The current mitigation (state.json + "one-sentence reasoning on unchanged state") reduces *output length* but not *fire count*. Claude still spins up a fresh CLI session, reads context, decides "no change", writes a brief decision — **every 5 minutes, indefinitely**. The wall-clock and quota cost is real (288 Opus sessions/day even when nothing is happening), and the cognitive load — even when output is one sentence — still asks Claude to "say something" 288 times when honest expansion-stage trading might warrant one decision per hour.

## Design principle

Cognition cadence should be a function of market information rate, not a constant.

| Market state                  | Cadence behavior                                    |
|-------------------------------|----------------------------------------------------|
| Expansion (displacement, vol shift, regime flip) | Full 5-min cadence, full reasoning            |
| Compression, no position      | Skip fires when state unchanged; heartbeat 1×/hour |
| State unchanged + open position | Full 5-min cadence — managing live risk         |
| Approaching reflection cadence (≥4h since last reflection) | Force fire so reflection clock advances |

Inversion of today: instead of "always fire, occasionally write short", the system becomes "fire only when there's signal, summarize what was skipped".

## Proposed architecture — wrapper-level gate

The launchd plist stays at 5-min `StartInterval` (don't touch the scheduler — reliability + uniform monitoring). The change lives in `~/ibitlabs/scripts/run_claude_trader.sh`, the wrapper that decides whether to actually spawn the Claude CLI process.

### Gate logic (pseudocode)

```
on each launchd tick:
  state = read claude_trader_state.json
  live  = curl /api/live-status (fast, ~1s)

  force_fire = false

  # Reasons to definitely fire:
  if no state file yet: force_fire = true                  # cold-start
  if live.position is not None: force_fire = true          # holding risk
  if live.regime != state.regime: force_fire = true        # regime flip
  if abs(live.price - state.range_midpoint) > range_width * 0.6: force_fire = true  # range break
  if (now - last_decision_ts) > 1h: force_fire = true      # heartbeat (compression-safe)
  if (now - last_reflection_ts) > 4h: force_fire = true    # framework clock

  if force_fire:
    spawn claude CLI as normal
  else:
    # state unchanged + no position + recent enough decision + recent enough reflection
    log "[claude-trader-gate] skip — state unchanged, no position"
    increment skipped_fires_counter in state.json
    exit 0 (no JSONL write, no Claude session, no quota burn)
```

The "force_fire" predicate is intentionally generous — any of (cold-start / position open / regime flip / range break / 1h heartbeat / 4h reflection clock) triggers a real fire. The skip path only activates when **all** of those are false.

### State.json additions

Add fields the wrapper reads:
- `range_midpoint_usd` (computed from range_low/high, or maintained by Claude)
- `range_width_usd`
- `skipped_fires_since_last_decision` (counter incremented by gate; reset to 0 by each real fire)
- `last_gate_check_iso` (for operator visibility)

Claude's persistent-state protocol stays the same — the wrapper just **reads** what Claude maintains.

### Public page implications

This is the load-bearing UX question Bonny flagged.

**Today's page experience:**
- "Last fire 2m ago" badge updates constantly (every 5 min there's a new entry in the pulse counter, even if "Same baseline as fire X").
- Visual pulse animation on the green "live" dot reinforces "system is running, watching markets".

**Under adaptive cadence:**
- In compression, "Last fire" could read "47m ago" or "1h 14m ago".
- A reader landing on the page during a quiet stretch sees a stale-looking timestamp.
- This is **honest** (the system isn't doing meaningful work; compression has no signal) — but a casual reader might interpret it as "this is broken" or "the project was abandoned".

### Proposed page mitigations

1. **Compression-mode status banner:** when `last_gate_check_iso > last_fire_iso`, surface a small strip:
   > "compression mode · gate is awake every 5 min · last real fire 47m ago · 9 fires skipped (no signal)"
   This says "this is by design, not stale" without faking pulse activity.

2. **Add skipped-fires count to the pulse counter:**
   > "5 HOLDs · 18 fires skipped (compression) since framework v0.2 · last fire 23m ago"
   Aggregates skipped fires as activity proof without fabricating decisions.

3. **Keep the green pulse-dot animation,** but tie it to the gate's most-recent check rather than the most-recent decision. The gate IS still running every 5 min — that's what the dot represents.

4. **Re-design "Latest decision" card** to handle long gaps gracefully. Currently it shows "5m ago"; under adaptive cadence the freshness window should be longer. Maybe label the card "Latest meaningful event" instead of "Latest decision" to set expectations.

## Edge cases worth thinking through

| Case | Behavior | Why this is safe / risky |
|------|----------|--------------------------|
| State.json corrupt or missing | force_fire = true | Cold-start path always fires; safe failure mode |
| Operator manually deletes state.json (debugging) | Cold-start; Claude rewrites on next fire | Operator workflow preserved |
| Live-status endpoint flakes | Gate can't compute regime check → force_fire = true | Failure mode = "fire too much", not "skip too much" |
| Range break right after a fire (during skipped window) | Next launchd tick (≤5 min later) catches it via the range-break trigger | 5-min worst-case detection lag |
| Claude's framework cadence clock (every ≈50 fires) | Currently fire-count-based; under adaptive cadence, switch to time-based (every 4h) | Already partially in the SKILL (4h heartbeat) |
| Position opens during a skipped window | Position is opened by the executor reading a previous fire's ENTER decision. The wrapper checks `live.position` every tick, so the very next tick fires immediately | No risk of skipped fires while holding |
| Sudden compression-to-expansion transition | Range break + vol shift both trigger → fires immediately | Detection mostly handled by the range_break check |

## Cost / benefit math

Today: 288 fires/day × ~3-5s Claude CLI session ≈ 14-24 minutes of Opus quota/day.

Under adaptive cadence (estimated, in a typical compression-heavy day):
- ~20-40 real fires (transitions + 1/hr heartbeat + ~4h reflections)
- ~250 skip-checks (each ~50ms shell cost, no Claude API call)
- Net Opus quota: ~85% reduction
- Net page-pulse "feel": much sparser

In an expansion day:
- Real fires approach the current 288 (most ticks have something to read)
- Page pulse looks the same as today

The cost saved isn't urgent (subscription quota, not per-call billing) but the bigger win is **cognitive integrity**: Claude is no longer asked to manufacture content when there is none. Mission #3 angle: a system that goes quiet during quiet markets is more honest than one that produces 288 daily reasonings of identical "still nothing happening".

## Implementation sketch (if approved)

Files to touch:
- `~/ibitlabs/scripts/run_claude_trader.sh` — add gate logic at top of script before the Claude CLI invocation. Gate output goes to a new `~/ibitlabs/logs/claude-trader/gate.log`.
- `~/ibitlabs/scripts/generate_claude_public_data.py` — surface `skipped_fires_since_last_decision` and `last_gate_check_iso` in the public JSON; add "compression mode" detection logic (state unchanged AND no position AND skipped_fires > 3).
- `~/ibitlabs/web/public/lab/claude/index.html` — render the compression-mode banner; update pulse counter copy to include skipped count; relabel "Latest decision" → "Latest meaningful event".
- `~/.claude/scheduled-tasks/claude-trader/SKILL.md` — Claude needs to know it may be invoked less frequently. Update § Framework reflection cadence to use time-based instead of fire-count-based scheduling (4h-based, which is already there as a fallback).
- Memory: project_claude_trader_phase0_2026_05_25.md gets a Phase B section (this).

Estimated work: ~60-90 minutes. Not large, but the page-UX change (compression-mode banner + pulse-counter copy) needs careful framing — easy to make it look broken, easy to make it look pretentious.

## Open questions for the operator

1. **Heartbeat interval.** I proposed 1h. Should it be tighter (30min) so the page doesn't look stale, or looser (2-3h) to let the cognition fully match the tape?
2. **"Compression mode" banner copy.** Should it be a permanent visible element when active, or only show after >30min of no real fires? (Showing too early might look pedantic.)
3. **Framework reflection clock under skipped fires.** Today the SKILL says "every ≥50 fires". With skipped fires no longer in decisions.jsonl, fire-count drift becomes meaningless. Move fully to 4h-based, or 4h-OR-50-fire-whichever-first? My recommendation: pure 4h-based.
4. **Whether to also surface a "skipped fires" event row in the public timeline.** Could be useful as "the system noticed nothing and did nothing for 47 minutes — this is the system working", or could be noise. My instinct: a single summary line per "skip window" (i.e. "47m skipped · compression · no transitions detected") is enough; not 9 individual rows.
5. **Should the wrapper still tick every 5 min, or can the launchd interval increase too?** Argument for keeping 5min: detection latency on transitions stays tight. Argument for increasing (e.g. to 10 or 15 min): even simpler infrastructure, but 5-min-worst-case-lag on a regime flip during compression becomes 15-min-worst-case-lag — that's a real loss if compression ends with a sharp displacement.

## Recommended decision path

1. Operator reviews this doc, answers the 5 open questions inline (or selects defaults).
2. If green-lit, ship the implementation in ~90 min. Phase B of adaptive cadence becomes the next memory checkpoint.
3. Run for 1 week with skipped-fires telemetry visible to operator. If skipped:real-fire ratio looks reasonable and the page UX doesn't feel broken, lock in. If it feels worse than today's "always-on pulse", revert via single env flag.

## Why this is in a design doc, not a commit

Bonny chose path (c) in the founder-notes discussion: ship epistemic schema now, design cadence first. The reasoning was good and bears repeating:

> "Adaptive cadence has UX implications — the page goes quiet for hours. That might be honest, or might look broken. Don't ship without operator sign-off."

Today's commit (`b3fa4b0` / `95157cf` / `ab063c0` chain) shipped four collaboration mechanisms (founder-notes / state-snapshot / EV-gate / missed-setup-log) and the epistemic schema on top. Adaptive cadence is the next layer up and the highest-leverage one — but it touches the visible artifact and deserves explicit founder framing of "what does this page promise to a viewer."

The design doc itself is the artifact for that conversation.
