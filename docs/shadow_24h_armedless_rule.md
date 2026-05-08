# Shadow Rule B' — 24h Armedless Safety Net

**Rule ID:** `B-prime`
**Rule name:** `24h_armedless_safety_net`
**Proposed by:** operator (twin-shadow with Rule B)
**Mode:** LOG-ONLY (no execution; pure observation)
**Started:** 2026-05-04
**Twin-shadow review:** 2026-05-23 (alongside Rules B / C / D / E / F)
**Log file:** `logs/shadow_24h_armedless_rule.jsonl`
**Code site:** `sol_sniper_executor.py` — fire block at line ~462, logger method `_log_shadow_24h_armedless_rule`
**Notion analysis:** https://www.notion.so/3563c821a4aa81339ad0f21ff0b3b0cf

## Trigger condition

```
elapsed >= 24 * 3600
AND pnl_pct < 0
AND highest_pnl_pct < cfg.trailing_activate_pct  # i.e. trailing never armed
```

Same shape as Rule B (`12h_compound_time_cap`) with the time threshold raised
from 12h → 24h. By construction, every B' fire is also a B fire, but the
converse is not true: any position that closes between h=12 and h=24 fires B
without firing B'.

## Why this rule exists

Rule B's 11-day shadow (2026-04-23 → 2026-05-04, 3 fires) showed the rule
is shape-right but parameter-wrong:

| # | Trade | B fire @ | Hyp. close | Actual close | Rule B verdict | Would B' fire? |
|---|---|---|---|---|---|---|
| 1 | #331 long $88.20 | h=21.6, PnL=−2.48% | −$11.22 | −$22.93 (SL @ h=119.9) | saves $11.71 ✓ | **yes** (held to h=119.9) |
| 2 | #335 short $83.95 | h=12.0, PnL=−0.99% | −$4.40 | +$9.61 (manual @ h=22.5, MFE +2.87%) | costs $14.01 ✗ | **no** (closed before h=24) |
| 3 | #338 short $83.62 | h=12.0, PnL=−0.60% | −$2.75 | OPEN (h=92.6 as of 2026-05-04) | TBD | **yes** (already past h=24) |

Rule B's net on the closed pair: **−$2.30**. Rule B' would have skipped
Fire #2 entirely, leaving a clean +$11.71 on Fire #1.

The hypothesis B' is testing: **v5.1's signal sometimes legitimately needs
>12h to develop**. If a position is still alive at h=24 without ever arming
trailing (highest_pnl < 1.5%), that's a much stronger "setup did not
materialize" signal than the same condition at h=12.

## What review at 2026-05-23 looks like

Joint read with Rule B:

- If B' has fewer fires than B AND a better hypothetical-PnL distribution →
  promote B' / falsify B / retire 12h variant
- If B and B' have similar economics → the time threshold is not the
  controlling variable; look at Rules C/D family (funding-magnitude gates)
- If B' has zero fires by 2026-05-23 → keep observing through 2026-06-03
  (genuine 30-day window from B's start) before drawing conclusions
- If B' fires fewer times but each fire is a saver (no Fire #2-style false
  positives) → ship B' to live execution, retire B

## What this rule is explicitly NOT

- **NOT a 24h flat hard-cap.** v5.1 already has a 24h compound / 36h flat
  hard-cap. This rule is conditional on `pnl_pct < 0` AND
  `highest_pnl_pct < trailing_activate_pct` — only fires for positions that
  haven't shown the setup is working.
- **NOT a re-proposal of the 12h flat cap rejected on 2026-04-22.** The
  shape is conditional on armed-state, not flat time.
- **NOT an upside cap.** Negative-PnL only.
- **NOT a Filter A drawdown variant.** Independent of entry-vs-recent-high
  position.

## Operational notes

- **Bot restart required for B' to start firing.** Sniper picks up the new
  field on next cold start. Operator window is up to Bonny — natural
  candidate is when SHORT #338 closes.
- Until restart, the new code is dormant: no fires, no log file created.
- After restart, Rule B' state field `shadow_24h_armedless_rule_fired`
  appears in `sol_sniper_state.json` next to existing shadow flags.
- The currently-open SHORT #338 will NOT fire B' immediately on restart
  even though it's at h=92.6 — restart resets all shadow flags including
  B' to False, so it would then evaluate True on the next position-check
  tick after restart. That's the correct behavior (we want to log this
  position's eventual outcome, not its history).

## Promotion criteria

Following the Rule F template (`project_rule_f_promotion_criteria.md`):

- ≥ 5 fires before promotion (smaller bar than F's 30 because B' is a
  pure-time rule, not a regime gate; per-fire signal is high)
- Hypothetical-PnL net positive on closed fires
- No false-positive structure like Fire #2 (#335) — i.e. no fires on
  positions that closed armed-trailing within hours of the fire
- Falsify and retire if not cleared by 2026-08-04 (90 days)
