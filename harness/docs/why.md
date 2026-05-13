# Why each constraint exists

The harness encodes five constraints. Each one came from a specific failure we walked into, watched it eat real time and capital, and then locked into the schema so the same failure doesn't recur.

This doc is for educators, students, and anyone forking the harness for their own experiment. If you only want the spec, read [README.md](../README.md). If you want to know why each constraint earns its place — read on.

What follows is five real failure stories from the public $1k → $10k SOL trading experiment. Each story shows what the constraint would have prevented. The constraints are not aesthetic. They are scar tissue.

---

## Constraint 1: `real_data_gate` — evidence ≥ 3

**The rule:** A new shadow rule cannot be opened until at least 3 distinct real-data instances of its proposed pattern have been observed. Below that, the proposal is parked as a "hypothesis-with-trigger" and revisited only when the count clears 3.

**Why this exists.** "Filter A" was a proposed entry gate: block long entries when SOL was within X% drawdown from a recent high. The thinking was sound — don't catch falling knives. The in-sample backtest looked excellent: +20 percentage points on profit-factor over a 30-day window.

We almost shadow-opened it. What stopped us was a forward-test on the next OOS month: −40pp.

The mechanism, retrospectively: drawdown-from-recent-high is correlated with regime-window lag, not with entry quality. The in-sample window happened to have regime detection that synced with price; the OOS window didn't. Filter A wasn't measuring entry quality — it was measuring the regime detector's lag. A single in-sample bucket of "evidence" had hidden the structural problem.

**With the gate:** real_data_gate would have asked, "have you observed this pattern produce edge across ≥3 distinct windows?" The answer was no — the proposer had one in-sample window. Hypothesis would have been parked.

**Memory file:** `feedback_filter_a_falsified.md`. Now also encoded as a public anti-pattern in [examples/filter_a_drawdown.yaml](../examples/filter_a_drawdown.yaml) with 4 aliases blocked.

**Teaching prompt:** Find a published trading rule with a single backtest result. What's the ≥3 instances version of that test?

---

## Constraint 2: `shadow_budget` — at most 2 active

**The rule:** No more than 2 shadow rules running concurrently against the live bot. New proposals queue; existing ones must retire before new ones open.

**Why this exists.** When 10 hypotheses are tested simultaneously on the same live trades, attribution collapses. If trade #61 closes at +$8.42, was that the new ATR filter? The new exit-distance heuristic? The funding-decay bias? You can't tell — every shadow fired or didn't fire on the same fill.

In our case, the trigger was a series of 10 TP/SL adaptive variants. Entry filters, exit price-distance heuristics, exit signal-driven mirrors, NFI-style exhaustion gates. Each one had a plausible mechanism. If we'd opened all 10 simultaneously, the data would have been a tangle: any pattern in trade outcomes would map ambiguously back to multiple shadows.

We sequentially tested them: 10 findings, all closed. Each got attributed cleanly because no two ran at the same time on the same trade.

**With the gate:** shadow_budget caps concurrent shadows at 2. The narrow channel forces sequential testing. Slow but legible. The two-slot cap also creates a healthy back-pressure — if a new proposal looks promising, you have to retire something to make room. That decision is itself useful.

**Memory file:** `feedback_shadow_budget.md` and `feedback_tpsl_adaptive_archived.md` (the 10 findings).

**Teaching prompt:** A team has 10 hypotheses about a deployed model. They want to A/B-test them all next week. What's the budget your harness imposes? What's the back-pressure cost of going from 2 → 3 active?

---

## Constraint 3: `contributor_credit` — 48h ping

**The rule:** When a proposal carries a `proposed_by` handle, the operator must ping that contributor (Moltbook, GitHub, etc.) and wait at least 48 hours before changing any tunables on the proposed rule. Even if the operator's instinct says "the default is wrong, let me fix it."

**Why this exists.** A contributor proposed a shadow rule. We adopted it. Some weeks in, the rule was dormant — never firing. We started silently retuning the threshold to make it fire. The contributor's name was still on the rule, but the parameters were our choice now. When they checked back, the truthful answer was: "yes, but we changed your spec."

That's a small betrayal. It corrodes the contributor relationship. Future contributors notice, and the funnel narrows.

**With the gate:** when a `proposed_by` handle is set, contributor_credit blocks unilateral retuning. The 48h window is enough time to ping and let them respond. If they don't respond, the operator can proceed — but the record shows the ping happened, and the contributor's name stays on the rule with their original spec preserved in commit history.

The constraint is about epistemic honesty as much as relationship management: if you change someone's hypothesis, the rule is no longer testing their idea.

**Memory file:** `feedback_contributor_rule_calibration.md`.

**Teaching prompt:** Look at an open-source project where a contributor's proposal has been silently modified. What's the contributor's first sign? What's the harness equivalent for your project?

---

## Constraint 4: `control_flow_impact` — log_only at proposal stage

**The rule:** A new proposal must specify `control_flow_impact: log_only`. Any change to live entry, exit, or sizing logic requires explicit re-spec after the observation window. The proposer cannot ship a rule that immediately gates real money.

**Why this exists.** A bug in a live trading path costs real money. A bug in a logging path costs disk space.

We learned this with "Bug A" — a `max_hold_seconds=0` config got into our regime-window shadow for 26 days. 138 of 233 closes were `timeout 0.0h` pollution. The shadow's reported cash inflated from $1k to $25.26M because the bug fired on every fill. If that bug had been in the live entry path instead of the shadow logger, we would have lost real money on every trade for those 26 days.

The fix was a paper.py reset and a 30-day re-observation. The shadow lost a month. The live bot lost nothing because Bug A was firewalled off by `control_flow_impact: log_only`.

**With the gate:** any new mechanism enters as instrumentation only — it writes to a jsonl, it does not touch trade decisions. After the 30d observation window, if the data supports promotion, the operator does an explicit re-spec into the live path. Two-step lock prevents single-author mistakes from reaching real capital.

This constraint is also why our promote_bar evaluator returns RETIRE on yaml integrity failures (added 2026-05-12 after a contributor flagged the cross-component coupling gap): if the proposal yaml has been mutated between submit and review, you can't trust that the bar's input still matches the proposer's intent.

**Memory file:** `project_regime_window_shadow.md` (Bug A); `project_harness_2026_05_12.md` (the same-day coupling fix).

**Teaching prompt:** Take a feature flag in your codebase. What's the structural difference between "log_only" and "live"? What's the explicit step required to flip from one to the other? How would you make that step harder to skip?

---

## Constraint 5: `promotion_bar` — ≥30 trades, ≥30 days, ≥15pp spread, direction match

**The rule:** A shadow rule cannot be promoted from log-only to a live entry gate until it has accumulated at least 30 entries per direction-bucket, observed at least 30 days, shows a hit-rate spread of at least 15 percentage points vs baseline, and the direction of the spread matches the original hypothesis. Any of those four failing means continue observing or retire.

**Why this exists.** The harness's first real shadow rule (Lona's ATR-compression regime, "Rule F") shows a fascinating early picture: 7 fires, 5 paired wins, +50pp spread vs 0.5 baseline. By any naive read, that's a green light to promote.

It is not a green light. With n=7, a +50pp spread sits comfortably inside the standard error of small-sample binomial variance. We've seen "5/5 streak" patterns reverse to 50/50 within the next 30 trades on multiple shadow rules. Promote on n=7 and you're shipping noise.

The 30/30/15pp/direction-match floor exists because we've watched ourselves want to promote early. The bar protects us from our own enthusiasm.

**With the gate:** Rule F is correctly sitting at `KEEP_OBSERVING` despite the +50pp early spread. First review is scheduled for 2026-06-01 (30 days post-shadow-open). If the spread holds at n≥30, it promotes. If it collapses, it gets archived as a falsified hypothesis with proper attribution and a public retrospective on `/contributors`.

The four sub-floors interlock: 30 trades alone isn't enough (could be all in 5 days of one regime); 30 days alone isn't enough (could be 3 trades). The "direction match" sub-floor is the trickiest — a strong spread in the WRONG direction is a falsified hypothesis, not a discovery. We've had backtest results +57pp where the direction was opposite to the proposer's claim. That's a no-go for promotion; it's a candidate for the anti-pattern archive.

**Memory file:** `project_rule_f_promotion_criteria.md` (the bar template, generalizable to other rules).

**Teaching prompt:** A new feature shows +20% conversion in its first week. What's the promotion bar your harness would require before you'd ship it default-on? What sub-floor would catch the case where the +20% is actually one viral cohort and reverts in week 2?

---

## How to teach this

If you're using this in a curriculum or workshop, the natural arc is:

1. **Show the 5 constraints as schema** (5 minutes). Open `schemas/proposal.schema.json`. Each constraint is a `required` field with bounds. Notice that the constraints are encoded in JSON Schema — they enforce themselves at validate time, not in human review.

2. **Walk through this doc** (15 minutes). The pattern is rule → failure story → mechanism → memory file → teaching prompt. Pause at each prompt for student responses.

3. **Show a live shadow** (10 minutes). Open `examples/rule_f_atr_compression.yaml`, then run `python3 ../bin/promote_bar.py rule_f_atr_compression.yaml` from the harness directory. Students see the actual decision logic and the receipt format. Today the result is `KEEP_OBSERVING`; check the [live status JSON](https://www.ibitlabs.com/data/harness_status.json) for the current snapshot.

4. **Run the bad-yaml exercise** (10 minutes). Have students fork `templates/proposal.template.yaml`, deliberately violate one or more constraints, run `bin/validate_proposal.py`, and read the rejection output. The point: violations come back with specific memory citations, not opinions.

5. **Discussion: which constraint would your project need first?** (15 minutes). Most engineering teams have at least one of these failure modes already in their incident log. The exercise is identifying which one most maps to a current incident in their own system.

The harness is small enough (16 source files, ~1300 lines) that students can read it in one sitting. The constraints are general enough that they translate beyond trading — any deployed model with feedback loops faces the same five traps.

---

## References

- [README.md](../README.md) — harness overview and CLI usage
- [examples/rule_f_atr_compression.yaml](../examples/rule_f_atr_compression.yaml) — Lona's ATR-compression proposal, currently in 30d shadow
- [examples/filter_a_drawdown.yaml](../examples/filter_a_drawdown.yaml) — Filter A archived as anti-pattern, the source of the real_data_gate story
- [Live status JSON](https://www.ibitlabs.com/data/harness_status.json) — current monitor state across all 3 layers
- [/contributors](https://www.ibitlabs.com/contributors) — adopted rules with names and outcomes

The memory files referenced in this doc are stored in the project's persistent context, not in the public repo. If you want to see the specific incident logs, ask the operator (`@bbismm` on GitHub) for read access if you're building curriculum around this.
