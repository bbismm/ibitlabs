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

---

## Section 9 — Productizing observable cognition states (cognition_mode)

*Added 2026-05-25 evening per Bonny's reflection on Phase A.6. This section is a refinement that SUPERSEDES Sections 2-3's wrapper-gate "state unchanged check" with a cleaner abstraction: cadence becomes a function of a semantic, Claude-owned cognition state — not a procedural heuristic.*

### The level shift

Earlier sections (2-3) framed adaptive cadence as a scheduler optimization problem: gate the Claude CLI invocation behind a procedural "state unchanged AND no position AND not at heartbeat" check. That works, but it leaves the cadence layer reactive and hidden — wrapper infrastructure logic invisible to the public surface. Bonny's reframe in conversation:

> "You've moved cadence from scheduler-optimization-problem to cognitive-state-protocol."

| Wrapper gate (Sections 2-3) | cognition_mode (this section) |
|---|---|
| Procedural | Semantic |
| Reactive ("if no change, skip") | Self-described ("Compression Mode") |
| Binary (fire / skip) | Expressive (multiple labeled states) |
| Hidden infra logic | Public research state |

The second column is what supports Mission #3. Silence labeled "Mode: Compression. Information rate low. Monitoring for structural transition." is an **epistemic stance**. Silence labeled with nothing (or with a passive "skipped 9 fires" counter) just looks like the system is broken.

### cognition_mode as Claude-owned ontology

`cognition_mode` becomes a first-class field in `~/ibitlabs/state/claude_trader_state.json`. Claude maintains it; the wrapper reads it; the page renders it. Nothing else writes to it.

**Starter ontology (deliberately small, not exhaustive):**

| Mode | Meaning | Typical cadence |
|---|---|---|
| `Expansion` | High information density. Displacement, regime in transition, fresh range break, volume conviction. | Full 5-min, full reasoning. |
| `Compression` | Low information rate. Tight range, low ATR, no displacement, no sweep activity. | Sparse — fire on transitions + heartbeat only. |
| `Regime Uncertain` | Mixed signals. Live-status regime tag conflicts with intra-day tape, or 1H/4H/24h disagree. | Medium — fire on each timeframe alignment check. |
| `Inventory Discovery` | A position is open and the book is exploring P&L territory. Need to manage live risk. | Full 5-min, no skipping ever. |

These are **seeds**, not a closed enum. Claude may grow new modes as the experiment matures — examples Bonny named in conversation:
- `Liquidity Hunt` — sweep is in progress, expect cleanup move
- `Trend Exhaustion` — extended directional move showing exhaustion signatures
- `Reflexive Chop` — repeated failed breakouts, range narrowing pathologically
- `Failed Discovery` — recent sweep didn't produce displacement; revert posture
- `Post-Displacement Drift` — post-move stabilization, asymmetric continuation odds

The protocol: Claude proposes a new mode in a framework reflection (with definition + cadence implication + entry triggers), then begins using it in state.json. The lineage is public. Future contributors learn the ontology by reading framework_log + state.json, not by reading a static schema.

### Cadence = function(cognition_mode)

Replaces the wrapper-gate ad-hoc logic from Section 2:

```
on each launchd tick:
  mode = state.cognition_mode  // already-maintained by Claude

  switch mode:
    case "Expansion":         force_fire (always)
    case "Inventory Discovery": force_fire (always — live risk)
    case "Regime Uncertain":  fire if (last_fire > 15min ago) OR transitions
    case "Compression":       fire only if (transition detected) OR (heartbeat: last_fire > 1h)
    case <Claude-coined mode>: default behavior per mode's declared cadence

  # Transition detection is still done by the wrapper (cheap shell checks):
  # regime flip / range break / displacement / OI shift / position state change.
  # These are NOT mode-defined; they're invariant safety signals.

  if force_fire OR transition_detected:
    spawn Claude CLI
  else:
    log "[claude-trader-gate] mode={mode} · skip" → gate.log
    exit 0
```

The semantic layer (`mode`) is Claude's. The transition-detection layer (regime flip / displacement / range break / etc.) is procedural and lives in the wrapper as invariants. This separation means **Claude can never accidentally suppress its own cognition during a real market event** — transition detection bypasses the mode-based cadence.

### State.json schema additions (replaces Section 2's proposal)

```json
{
  "schema_version": 2,
  ...existing fields (regime, range, narrative, etc.)...

  "cognition_mode": "Expansion" | "Compression" | "Regime Uncertain" | "Inventory Discovery" | "<Claude-coined>",
  "cognition_mode_since_iso": "<ISO>",
  "cognition_mode_rationale": "<one sentence — why this mode, not the adjacent ones>",
  "cognition_mode_cadence_hint": "fire 5min" | "fire 15min on transitions" | "fire 1h heartbeat" | "<custom>",
  "skipped_fires_in_mode": <int>,  // reset on mode transition
  "last_mode_transition_iso": "<ISO>"
}
```

The `cognition_mode_rationale` and `cognition_mode_cadence_hint` are first-class — they show up on the public page so the reader sees not just "Mode: Compression" but also "why this mode and what it implies for cadence".

### Public page implications (replaces Section 3's "compression banner")

Drop the conditional "compression mode banner" idea from Section 3. Replace with **always-visible mode strip** at the top of the page:

> **Mode: Compression** · Information rate low. Monitoring for structural transition. · since 47m ago · gate fires 5min, real cognition 1h heartbeat

This is permanent UI furniture, not a conditional warning. The page reader **always** knows what cognition state the system is in. When the mode is `Expansion`, the same strip reads:

> **Mode: Expansion** · Displacement signature on 15m, vol expanding. · since 4m ago · cognition fires 5min full reasoning.

This subsumes:
- The "compression banner" idea
- The relabeled "Latest meaningful event" header
- The "skipped fires count" — moved into the mode strip's metadata

The Latest Decision card stays as today; it shows last decision regardless of mode. The mode strip explains why the freshness window is what it is.

### Why this is better than Section 2's wrapper-gate

1. **Honesty surfaces.** The system is not "skipping fires when nothing changes" (which sounds defensive). It is "in Compression Mode" (which is a positive epistemic stance).
2. **Claude owns the abstraction.** The wrapper reads `cognition_mode` like reading any other piece of state. The wrapper does not decide what the mode is.
3. **Ontology can grow.** A scheduler-optimization problem has a fixed solution space (fire / skip). A semantic protocol can absorb new modes without redesigning the gate.
4. **The page becomes more accurate.** Absence of output is explained by a label, not by a counter.
5. **Future contributors learn the system by reading the modes.** Modes are documented in framework_log entries; the ontology IS the system's worldview.

### Trade-off: more burden on Claude

The wrapper-gate approach (Section 2) puts the burden on infrastructure: a clean piece of shell logic, deterministic, reviewable. The cognition_mode approach puts the burden on Claude: it must maintain a semantic label, not just react to triggers. If Claude mislabels (says "Compression" when it's actually "Trend Exhaustion") the cadence will be wrong.

Mitigations:
- Transition detection (invariant safety) is procedural and bypasses mode logic — protects against worst-case mislabeling.
- Mode mislabeling will show up in the public lineage (framework_log "what's failing" sections, eventually founder-note critiques) — self-correcting via the loop already shipped in Phase A.6.
- Initial mode set is small (4) — low surface area for early errors.

### Implementation revision (supersedes Section 2's sketch)

Files to touch (delta from Section 2's sketch):
- `~/.claude/scheduled-tasks/claude-trader/SKILL.md` — new section "§ cognition_mode" describing the protocol + starter ontology + how to propose new modes via framework reflection.
- `~/ibitlabs/state/claude_trader_state.json` schema — add the 6 cognition_mode fields above.
- `~/ibitlabs/scripts/run_claude_trader.sh` — gate logic reads `cognition_mode` from state.json (not the ad-hoc state-unchanged check).
- `~/ibitlabs/scripts/generate_claude_public_data.py` — surface `cognition_mode` + rationale + cadence_hint in public JSON.
- `~/ibitlabs/web/public/lab/claude/index.html` — render the always-visible mode strip. Drop the "compression banner" conditional logic from Section 3.
- Memory: `project_persistent_epistemic_organism_2026_05_25.md` already references this. Cross-link.

Estimated work (replaces Section 2's 60-90 min): **~90-120 min.** The extra time is in SKILL (writing the cognition_mode protocol clearly so Claude internalizes it) and in the page (the mode strip needs visual care — it's the most visible new element).

### Open questions for operator — Section 9 additions

(Existing 5 questions from earlier sections still apply where compatible.)

6. **Starter ontology.** The 4 modes above feel sufficient for Phase B kickoff. Confirm? Or add `Position Held` as a distinct mode (rather than folding it into `Inventory Discovery`)?
7. **Mode rationale visibility.** Should the page show only the rationale string, or also a "transitions since" timeline (e.g. "Expansion → Compression → Regime Uncertain → Compression over last 8 hours")? My instinct: just the current rationale + ISO transition, with full transition history in `framework_log` for those who want it.
8. **Mode mislabeling recovery.** If operator notices Claude has been in `Compression` for 12+ hours but a real expansion is happening, should there be a "force-mode-reassessment" channel (a founder-note tagged `regime`, type=high-confidence)? Or just append a regular founder-note and let the protocol handle it? Probably the latter.
9. **First-mode bootstrap.** When this ships, Claude needs to write the first cognition_mode into state.json. Should the first fire after Phase B ship be a forced reflection ("welcome to cognition_mode protocol; declare your initial mode"), or should Claude write the mode lazily on the next state.json update? My instinct: forced reflection on first fire — clean ontology origin point.

### Status

This section is a **design refinement**, not yet shipped. Phase B ship sequence:
1. Operator reviews this Section 9 + answers questions 6-9.
2. If green-lit, ship in ~2 hours.
3. First fire under Phase B writes the bootstrap reflection declaring initial cognition_mode.
4. Run for 1 week, observe whether the mode label feels honest or pretentious, calibrate.

If Section 9 itself feels over-designed (e.g. "the wrapper-gate from Section 2 was simpler and would have shipped tonight"), the fallback path is: ship Section 2's wrapper-gate as Phase B.0, gather one week of "skip vs fire" telemetry, then layer cognition_mode on top as Phase B.1 informed by that data. That preserves the Section 9 vision while reducing first-ship risk.

