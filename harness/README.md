# harness

iBitLabs trading-bot governance harness. Codifies the contributor-funnel constraints, promotion bars, rollback ladder, and anti-pattern archive into a single CLI + library so proposals (contributor or operator) flow through one pipeline.

## What it gives you

| Stage                 | CLI                              | Library                          |
|-----------------------|----------------------------------|----------------------------------|
| Propose               | `bin/validate_proposal.py`       | `lib.proposal.Proposal`          |
| Observe & evaluate    | `bin/promote_bar.py`             | `lib.promotion_bar.PromotionBar` |
| Rollback monitor      | `bin/rollback_status.py`         | `lib.rollback.RollbackLadder`    |
| Archive falsified     | `bin/archive_falsified.py`       | `lib.anti_pattern.AntiPattern`   |
| Schema-freeze monitor | `bin/freeze_status.py`           | `lib.freeze.current_status`      |

Use any subset — the five components are independent. The first four handle proposal lifecycle (propose → observe → rollback → archive). The fifth is operator-level: it tells you whether the harness *itself* may be mutated right now (see [docs/why.md](docs/why.md) §Operator Rule O1).

## Constraints: 5 proposal-level + 1 operator-level

### Proposal-level (encoded in `schemas/proposal.schema.json`)

These five validate *someone using the harness* (a contributor or operator submitting a proposal). A proposal failing any of them is rejected at validate time with a memory-rule citation.

1. **real_data_gate** — `evidence_seen >= 3` (memory: `feedback_real_data_before_features.md`)
2. **shadow_budget** — `current_active < cap`, `cap <= 2` (memory: `feedback_shadow_budget.md`)
3. **contributor_credit** — 48h ping when `proposed_by` is set (memory: `feedback_contributor_rule_calibration.md`)
4. **control_flow_impact** — must be `log_only` at proposal stage (CLAUDE.md observation-period contract)
5. **promotion_bar** — `min_entries >= 30` and `min_observation_days >= 30` (memory: `project_rule_f_promotion_criteria.md`)

### Operator-level (encoded in `governance/reviews.yaml`)

This one validates *whether the harness itself may be mutated*. Run `bin/freeze_status.py` for current state.

6. **schema_freeze** — When ≥2 reviews close within 7 days of each other, the harness schema, CLI, and library freeze for `[first.closes_at − 7d, last.closes_at + 14d]`. Mutations to `schemas/`, `bin/`, `lib/` during the freeze must be parked as hypothesis-with-trigger and re-submitted post-freeze. (memory: `project_harness_public_split_2026_05_13.md` — operational version of "schema must survive ≥2 review cycles unchanged before public split". Full story: [docs/why.md](docs/why.md) §Operator Rule O1)

## Quickstart

```bash
# 1. Validate a proposal
python3 harness/bin/validate_proposal.py harness/examples/rule_f_atr_compression.yaml

# 2. Evaluate a proposal against its promotion bar using real shadow jsonl + sol_sniper.db
python3 harness/bin/promote_bar.py harness/examples/rule_f_atr_compression.yaml

# 3. List all rollback monitors (realtime + observation + proposal layers)
python3 harness/bin/rollback_status.py

# 4. Archive a falsified rule (dry-run by default; pass --write to commit)
python3 harness/bin/archive_falsified.py harness/examples/filter_a_drawdown.yaml
python3 harness/bin/archive_falsified.py harness/examples/filter_a_drawdown.yaml --write

# 5. Check whether the harness itself is in schema freeze (operator-level)
python3 harness/bin/freeze_status.py
python3 harness/bin/freeze_status.py --now 2026-05-31    # what-if a future date
python3 harness/bin/freeze_status.py --json              # machine-readable for /lab dashboard
```

## Pre-commit hook (optional, recommended for active contributors)

Install the schema-freeze pre-commit hook so accidental mutations to `schemas/`, `bin/`, or `lib/` during a freeze window get blocked at commit time, not review time:

```bash
bash harness/scripts/install_pre_commit_hook.sh
```

The hook is a symlink to `harness/scripts/pre-commit-freeze`. Re-running the installer just refreshes the symlink. To bypass on a single operator-level call: `git commit --no-verify` (use sparingly — every bypass is a vote against the rule).

Audit the hook without waiting for a real freeze window:

```bash
HARNESS_FREEZE_TEST_NOW=2026-05-31 bash harness/scripts/pre-commit-freeze
```

## Real examples shipped

The schema's `domain` field marks which iBitLabs surface each rule applies to. As of 2026-05-14, the harness governs proposals from 3 domains:

**`trading` domain:**

- `examples/rule_f_atr_compression.yaml` — Lona's ATR-compression proposal, currently in 30d shadow (first review 2026-06-01)
- `examples/filter_a_drawdown.yaml` — Falsified drawdown-from-recent-high gate (+20pp IS, −40pp OOS), already archived in memory

**`brand_builder` domain** (added 2026-05-13 — same 5 constraints, different surface):

- `examples/brand_builder_i_thought_x_template.yaml` — Falsified opener template (4/11 posts in 3-day audit window used same "I thought X..." framing → algo down-weight + cliché-collapse). Blocks 6 paraphrase aliases.
- `examples/brand_builder_stub_skill_drift.yaml` — Falsified "stub SKILL.md alongside canonical" pattern (13-day silent drift, 20/20 recent posts at 0 trading content; karma kept growing via agent-echo-chamber, masking the failure). Blocks 5 paraphrase aliases. Generalizable to any skill with a runner-loaded SKILL.md.

**`harness_meta` domain** (added 2026-05-14 — governance-of-governance proposals):

- `examples/harness_meta_schema_freeze.yaml` — Proposal that introduced Operator Rule O1 (the schema-freeze monitor). Self-referential: the harness's own foundational rule submitted through the harness's own funnel, passing the same 5 constraints any contributor rule must pass. Currently in 30d shadow (first review 2026-06-15).

The other allowed domains in the schema (`saga`, `ops`) are reserved for future use. Adding a new domain means: (a) author the example yamls, (b) the rollback ladder picks them up automatically — no schema change needed beyond the enum.

## Why this exists

Before this harness, the 5 constraints lived in `feedback_*.md` memory entries that agents had to remember per-prompt. New proposals from contributors had no enforceable shape, and falsified rules sometimes resurfaced months later as paraphrased proposals. The harness makes the structure executable: validate at submission, evaluate at review, archive at retirement.

For the long-form story behind each constraint — five real failure cases from the $1k → $10k experiment, plus a workshop arc for teaching — see [docs/why.md](docs/why.md).
