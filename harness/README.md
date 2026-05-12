# harness

iBitLabs trading-bot governance harness. Codifies the contributor-funnel constraints, promotion bars, rollback ladder, and anti-pattern archive into a single CLI + library so proposals (contributor or operator) flow through one pipeline.

## What it gives you

| Stage              | CLI                              | Library                       |
|--------------------|----------------------------------|-------------------------------|
| Propose            | `bin/validate_proposal.py`       | `lib.proposal.Proposal`       |
| Observe & evaluate | `bin/promote_bar.py`             | `lib.promotion_bar.PromotionBar` |
| Rollback monitor   | `bin/rollback_status.py`         | `lib.rollback.RollbackLadder` |
| Archive falsified  | `bin/archive_falsified.py`       | `lib.anti_pattern.AntiPattern`|

Use any subset — the four components are independent.

## The 5 constraints encoded in `schemas/proposal.schema.json`

1. **real_data_gate** — `evidence_seen >= 3` (memory: `feedback_real_data_before_features.md`)
2. **shadow_budget** — `current_active < cap`, `cap <= 2` (memory: `feedback_shadow_budget.md`)
3. **contributor_credit** — 48h ping when `proposed_by` is set (memory: `feedback_contributor_rule_calibration.md`)
4. **control_flow_impact** — must be `log_only` at proposal stage (CLAUDE.md observation-period contract)
5. **promotion_bar** — `min_entries >= 30` and `min_observation_days >= 30` (memory: `project_rule_f_promotion_criteria.md`)

A proposal failing any of these is rejected at validate time with a memory-rule citation.

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
```

## Real examples shipped

- `examples/rule_f_atr_compression.yaml` — Lona's ATR-compression proposal, currently in 30d shadow (first review 2026-06-01)
- `examples/filter_a_drawdown.yaml` — Falsified drawdown-from-recent-high gate (+20pp IS, −40pp OOS), already archived in memory

## Why this exists

Before this harness, the 5 constraints lived in `feedback_*.md` memory entries that agents had to remember per-prompt. New proposals from contributors had no enforceable shape, and falsified rules sometimes resurfaced months later as paraphrased proposals. The harness makes the structure executable: validate at submission, evaluate at review, archive at retirement.
