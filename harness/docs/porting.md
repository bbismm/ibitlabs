# Porting harness to your project

Self-guided walkthrough for adapting harness to a domain you care about. Target: shipping your first shadow rule in 30-90 minutes.

If you're an instructor running a workshop, see [why.md § How to teach this](why.md#how-to-teach-this) instead — that arc is shaped for a group session.

---

## Step 1: Pick your domain

The harness ships with five declared domains, each backed by at least one real example:

| Domain          | What it governs                                      | Starting point                                       |
|-----------------|------------------------------------------------------|------------------------------------------------------|
| `trading`       | Entry/exit/risk rules for automated traders          | `examples/rule_f_atr_compression.yaml`               |
| `brand_builder` | Content-generation rules for an agent posting to social/distribution surfaces | `examples/brand_builder_i_thought_x_template.yaml` (anti-pattern) |
| `harness_meta`  | Governance-of-governance rules for the harness itself| `examples/harness_meta_schema_freeze.yaml`           |
| `ops`           | Operational gates for alert / escalation systems     | `examples/ops_launchd_critical_path_gate.yaml`       |
| `saga`          | Narrative cadence rules for serialized content       | `examples/saga_focal_moment_tier_priority.yaml`      |

Pick the one closest to your project. The 5 governance constraints (`real_data_gate`, `shadow_budget`, `contributor_credit`, `control_flow_impact`, `promotion_bar`) apply identically across all of them — they're domain-neutral by design.

If none fits cleanly, add a new domain:

1. Edit `schemas/proposal.schema.json` and extend the `domain` enum
2. Author example yamls under `examples/<your_domain>_<your_rule>.yaml`
3. The rollback ladder and freeze monitor pick the new domain up automatically — no other schema changes needed

If you add a 6th domain, mention it in `README.md` "Real examples shipped". Then submit a PR via the **🪪 Propose a rule** issue template if you'd like us to consider folding it upstream.

---

## Step 2: Identify the failure mode that earns the rule

Every rule in this harness exists because of a specific observed failure, not a first-principles "this would be nice" hypothesis. Before writing a proposal yaml, write down:

1. The pattern you observed (≥3 distinct instances in your real data)
2. The mechanism — *why* the pattern produces the failure
3. The metric the rule would reduce if shipped (e.g. false-positive count, attribution-collapse rate)

The `real_data_gate` constraint encodes step 1 (you need `evidence_seen >= 3`). If you can't list three distinct instances, the proposal gets parked as hypothesis-with-trigger. This is the point — most "feels-right" rules don't survive the three-instance test.

See [why.md § Constraint 1: real_data_gate](why.md#constraint-1-real_data_gate--evidence--3) for the canonical failure story behind this gate (Filter A: +20pp IS / −40pp OOS, from a single in-sample bucket).

---

## Step 3: Write your first proposal yaml

Copy the example closest to your domain into a new file and adapt:

```bash
cp harness/examples/rule_f_atr_compression.yaml my_rule.yaml
# edit my_rule.yaml — replace trading-specifics with your domain's specifics
```

The `proposal.schema.json` lists required fields. The ones most worth thinking about:

- **`hypothesis`** — falsifiable prediction. "Compression entries have ≥15pp higher win rate than expansion" is falsifiable; "compression entries are better" is not.
- **`direction`** — `long_bias` / `short_bias` / `both` / `neutral`. Required because the promotion bar does a direction-match check (+50pp spread in the WRONG direction = falsified, not promoted).
- **`real_data_gate.source`** — point to the specific instances. Log line numbers, trade IDs, file paths. Specificity is the whole signal here.
- **`promotion_bar.min_hit_rate_spread_pp`** — the effect size required to clear shadow → live. ≥15pp is the floor; tighten if your domain is high-stakes.

---

## Step 4: Validate before opening anything

```bash
python3 harness/bin/validate_proposal.py my_rule.yaml
```

A `[pass]` return means the 5 constraints are satisfied at submission. A `[reject]` lists which constraint failed and which memory rule explains why. The rejection message is meant to be machine-routable: paste it back to your contributor (or yourself) as a fix-this-before-resubmitting message.

---

## Step 5: Wire `shadow_log_jsonl` to your project's logging

The `shadow_log_jsonl` field is a path (relative to your project root) where your domain writes structured events when the rule fires. Two common patterns:

- **Pure observability rule:** instrument the code path with a single `json.dumps(event)` write to the jsonl. The rule generates data without changing live behavior. This is what `control_flow_impact: log_only` requires at proposal stage.
- **Counter-factual rule:** instrument both the "would-have-fired" and "did-not-fire" paths so the promotion bar can compute the spread between them. More work upfront, cleaner attribution at review.

Per `feedback_shadow_budget.md`: no more than 2 concurrent shadows on the same live system. If you already have 2 running, retire one before opening this rule.

---

## Step 6: Wait 30 days, then evaluate

```bash
python3 harness/bin/promote_bar.py my_rule.yaml
```

Possible outputs:
- `[PROMOTE]` — all 4 sub-floors cleared (entries, days, spread, direction match). Time to do the explicit re-spec into a live entry/exit gate.
- `[KEEP_OBSERVING]` — accumulating but not yet ready. The bar prints which sub-floor is gating.
- `[RETIRE]` — the bar will not clear within the rule's `retire_after_days` window. Move it to the anti-pattern archive (Step 7).
- `[RETIRE_BY_DEADLINE]` — `retire_after_days` exceeded without promotion. Same archive action.

---

## Step 7: Archive falsified rules

```bash
# dry-run first
python3 harness/bin/archive_falsified.py my_rule_anti_pattern.yaml

# actually commit the archive entry
python3 harness/bin/archive_falsified.py my_rule_anti_pattern.yaml --write
```

The anti-pattern archive is a teaching artifact, not a graveyard. Each archived entry includes:
- The original hypothesis
- The evidence that falsified it
- Aliases — paraphrases the archive should also block (the harness checks against the alias list before accepting new proposals, so falsified rules can't quietly resurface as "but worded differently")

See `examples/filter_a_drawdown.yaml` for the canonical falsification format. Notice the `aliases_blocked` list — that's how the archive earns its place rather than being a dead-letter file.

---

## Optional: operator-level governance

If your project has scheduled reviews (promotion decisions, design checkpoints, retros), enable the schema-freeze monitor:

```bash
# Declare your reviews
edit governance/reviews.yaml

# Check current freeze state
python3 harness/bin/freeze_status.py

# Install pre-commit hook (blocks schema/CLI/lib mutations during freeze)
bash harness/scripts/install_pre_commit_hook.sh
```

Operator Rule O1 (see [why.md § Operator-level governance rules](why.md#operator-level-governance-rules)) freezes harness's own schema for `[first_review - 7d, last_review + 14d]` whenever ≥2 reviews close within 7 days. This protects in-flight proposals from schema shifts driven by the very reviews that surfaced the gap.

---

## What you've built

After these seven steps you have:

- A domain-specific contributor funnel where new rules submit through a single CLI and pass or fail against the same 5 constraints any other rule has to clear
- A 30-day observation window that catches "feels-right but isn't" before it touches live decisions
- A promotion bar high enough that small-sample wins don't clear it
- An archive that prevents falsified ideas from quietly returning as paraphrases
- Optional operator-level governance that protects the harness itself during review clusters

Most teams don't need to start with all of this. The minimal viable harness is `validate_proposal.py` + one `examples/` yaml + `promote_bar.py`. Add the rest as the cost of *not* having it becomes visible.

---

## When you're stuck

- Validation rejecting a proposal you think is fine → the rejection message cites the failing constraint + memory file; the memory file has the canonical failure story
- Don't know which domain a rule belongs to → start with the closest one and rename later; the `domain` field is a string, not a contract
- Want to discuss before opening an issue → Moltbook [@ibitlabs_agent](https://www.moltbook.com/u/ibitlabs_agent) is the conversational surface; GitHub issues are durable
- Need to override the freeze hook for an emergency → `git commit --no-verify`, but record why in the commit message (every override is a vote against the rule)

---

## Reading order if you have 10 more minutes

1. [README.md](../README.md) — components table + 5+1 constraint summary
2. [docs/why.md](why.md) — five real failure stories + Operator Rule O1
3. One example matching your domain (the table at the top of this doc)
4. [CONTRIBUTING.md](../CONTRIBUTING.md) — funnel + AI co-authorship note + the funnel's own anti-patterns
