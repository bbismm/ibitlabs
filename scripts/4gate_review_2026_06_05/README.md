# 4-Gate Shadow→Live Promotion Review — 2026-06-05

**Source spec:** `~/ibitlabs/notes/sniper_swap_prep_2026_05_11.md` lines 76-91 ("Prep checklist for the 2026-06-05 review")

**Locked decision rule (cf. `feedback_no_grid_reenable_without_review.md`):** all 4 gates must clear before live can swap from `--no-grid` mean-reversion-only to (grid ON + trailing 0.4%/0.5%). Path C observability hook (shipped 2026-05-12) is gathering supporting data through `~/ibitlabs/logs/grid_what_if.jsonl`.

## Run order

```
01_gate1_sample_size.py        # 30s — answers (a) trade count + (b) regime coverage
02_gate2_backtest_compare.sh   # ~10 min — runs backtest_live_vs_shadow.py 4 variants
03_gate3_slippage_estimate.py  # 1 min — projects shadow PnL with live-fill slippage drag
04_gate4_academy_t6_draft.md   # NOT a script — content template, edit by hand after 1-3
```

If Gate 1 fails, stop — no point running Gates 2-3-4. Defer the review to the next maturation window (re-check at +30d).

## Outputs

Each script writes its raw output to `~/ibitlabs/logs/4gate_2026-06-05/<gate>.out`. Gate 4 is a markdown template that becomes the source for the academy.html T6 update.

## What this directory IS NOT

- It is NOT a decision engine. The scripts compute facts; the operator decides.
- It is NOT a deploy mechanism. The plist swap (per prep doc lines 154-172) happens manually after all 4 gates clear, not by any script here.
- It is NOT a substitute for the Path C observation window. If `grid_what_if.jsonl` shows < 20 events or < 2 regime buckets covered by 06-05, that itself is a Gate 1 modifier — see `project_c_hook_2026_05_12.md`.

## Pre-arm reading on 2026-06-05

Before running:
1. `~/ibitlabs/notes/sniper_swap_prep_2026_05_11.md` — full design context
2. `feedback_no_grid_reenable_without_review.md` — why we're gating
3. `project_c_hook_2026_05_12.md` — Path C data source
4. `feedback_real_data_before_features.md` — real-data discipline check
