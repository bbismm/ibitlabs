# Contributing to harness

`harness` is the governance framework extracted from the iBitLabs $1k → $10k trading lab. It encodes 5 proposal-level constraints + 1 operator-level rule into an executable CLI + library — so contributors and operators flow proposals through one pipeline.

Three kinds of contribution earn permanent credit.

---

## 🪪 Propose a rule

A new governance rule for any domain the harness can serve: `trading`, `brand_builder`, `harness_meta`, `saga`, `ops`. All 5 contributor-funnel constraints (encoded in `schemas/proposal.schema.json`) must be satisfied:

1. `real_data_gate` — `evidence_seen >= 3` distinct instances
2. `shadow_budget` — `current_active < cap`, `cap <= 2` concurrent shadows per domain
3. `contributor_credit` — 48h ping when `proposed_by` is set
4. `control_flow_impact` — must be `log_only` at proposal stage
5. `promotion_bar` — `min_entries >= 30`, `min_observation_days >= 30`, `min_hit_rate_spread_pp >= 15`, `direction_match_required: true`

Real proposals already shipped through the funnel:

- [`examples/rule_f_atr_compression.yaml`](examples/rule_f_atr_compression.yaml) — `trading` domain, Lona's ATR-compression entry regime, in 30d shadow (first review 2026-06-01)
- [`examples/harness_meta_schema_freeze.yaml`](examples/harness_meta_schema_freeze.yaml) — `harness_meta` domain, Operator Rule O1 (schema-freeze) self-proposed through the harness's own funnel

**Self-check before opening the issue:**

```bash
python3 harness/bin/validate_proposal.py your_proposal.yaml
```

If `validate_proposal` returns `[reject]`, the rejection message cites the specific constraint and the relevant memory rule. Fix and re-validate before submitting.

Submit via the **🪪 Propose a rule** issue template.

## 🔍 Falsify a constraint

If you can show evidence that one of the 5 proposal-level constraints or Operator Rule O1 has a failure mode we haven't seen — cite the incident, the mechanism, and what the constraint missed — that's a contribution at the same level as proposing a new one.

Falsified rules currently in the archive:

- [`examples/filter_a_drawdown.yaml`](examples/filter_a_drawdown.yaml) — drawdown-from-recent-high gate (+20pp IS / −40pp OOS, overfit not under-tuned)
- [`examples/brand_builder_i_thought_x_template.yaml`](examples/brand_builder_i_thought_x_template.yaml) — opener template per-cap drift
- [`examples/brand_builder_stub_skill_drift.yaml`](examples/brand_builder_stub_skill_drift.yaml) — stub SKILL.md alongside canonical → 13-day silent drift

Submit via the **🔍 Falsify a constraint** issue template.

## 📜 Extend a monitor

If you build a tool on top of harness output — alternative rollback monitor, anti-pattern visualizer, GitHub Action for server-side freeze enforcement, IDE plugin that runs `validate_proposal` on save, badge generator, dashboard slice — that's the closest analog to a "PR against the framework."

The harness's exposed surfaces:

- CLI: `validate_proposal.py`, `promote_bar.py`, `rollback_status.py`, `archive_falsified.py`, `freeze_status.py` (all support `--json`)
- Library: `lib.proposal`, `lib.promotion_bar`, `lib.rollback`, `lib.anti_pattern`, `lib.freeze`
- Data: `governance/reviews.yaml`, `schemas/*.schema.json`, `examples/*.yaml`
- Live snapshot (in the iBitLabs deployment): https://ibitlabs.com/data/harness_status.json

Submit via the **📜 Extend a monitor** issue template.

---

## What happens after you propose

```
1. Acknowledge      — we comment on your proposal, may ask clarifying Qs
2. Adopt (or skip)  — selected proposals enter as LOG-ONLY shadows
3. Observe (30d)    — shadow generates data alongside live, zero
                      execution risk
4. Decide           — public promotion criteria applied
                      (sample × effect × direction)
5. Outcome:
   ├─ Promote       — rule becomes a live gate; you're credited permanently
   │                  with the result
   └─ Retire        — documented as observed-but-not-promoted; still
                      credited; archived as anti-pattern in examples/
                      (your falsification becomes a teaching artifact)
```

**Promotion criteria are high on purpose.** From the `promotion_bar` schema:

- ≥30 entries per direction bucket
- ≥30 days of shadow observation
- ≥15pp hit-rate spread vs baseline
- Direction matches the proposer's hypothesis (no inverting falsified rules)
- No confounding shadow experiment running in the same window

For the story behind each constraint, see [`docs/why.md`](docs/why.md) — five real failure cases from the $1k → $10k trading experiment plus the Operator Rule O1 schema-freeze story.

---

## Schema-freeze policy

When ≥2 scheduled reviews close within 7 days of each other (a "cluster"), the harness schema, CLI, and library freeze for `[first cluster review − 7d, last cluster review + 14d]`. During the freeze, mutations to `schemas/`, `bin/`, `lib/` must be parked as hypothesis-with-trigger and re-submitted after the window closes.

Check current state:

```bash
python3 harness/bin/freeze_status.py
```

If you submit a schema-changing proposal during a freeze, we'll park it and re-engage after the window closes. Operator Rule O1 in [`docs/why.md`](docs/why.md) explains why.

A pre-commit hook is available if you commit into a harness checkout:

```bash
bash harness/scripts/install_pre_commit_hook.sh
```

The hook blocks commits touching `schemas/`, `bin/`, or `lib/` while a freeze is active. Bypass with `git commit --no-verify` (operator-level, use sparingly — every bypass is a vote against the rule).

---

## What we don't accept

- "Optimize the numbers" proposals without a mechanism story
- Schema-change PRs during freeze windows (use the funnel; the pre-commit hook catches this anyway)
- Paraphrase floods — one rule = one credit, even if you submit it six ways
- Anything that requires breaking the "every constraint encoded as schema, not memory" claim

---

## On AI co-authorship

This repo's commit history acknowledges Claude as a co-builder — every commit message lists `Co-Authored-By: Claude`. If you submit a PR or proposal, you're welcome to acknowledge your own AI collaborator the same way. The working assumption is that "we" includes the agent stack behind the keyboard.

---

## License

MIT — see [LICENSE](LICENSE). Same as the parent iBitLabs repo.

---

If you've read this far and want to start small:

1. Skim [`docs/why.md`](docs/why.md) to read the five failure stories + Operator Rule O1
2. Run `python3 harness/bin/validate_proposal.py examples/rule_f_atr_compression.yaml` to see a passing proposal
3. Edit a copy of the yaml to violate one constraint (set `min_entries: 10`, or `evidence_seen: 2`) and re-run — see the rejection format
4. Open an issue using a template, with one observation about your own system

Most adopted rules came from one good observation, not from an essay.
