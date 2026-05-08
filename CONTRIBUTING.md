# Contributing to iBitLabs

This isn't the usual "open a PR with your fix" repo. The strategy code is intentionally gitignored. What we accept is **proposals to the strategy** — observed in real markets and credited publicly if adopted.

Three kinds of contribution earn permanent credit on [ibitlabs.com/contributors](https://ibitlabs.com/contributors).

---

## 🪪 Propose a rule

A new entry filter, exit condition, or risk gate for the bot. Examples already adopted:

- **Rule F (Lona)** — ATR-compression regime tag at position open
- **Rule B (sophia-rcg)** — `edge_kill_condition`: expected funding × hold time vs remaining edge
- **Rule D (riverholybot)** — funding-reactive sizing (magnitude-aware, direction-blind)
- **Rule E (RiskOfficer_Bot)** — rolling Sortino observability snapshot

If we adopt your idea, the shadow JSONL's first line carries `proposed_by: <your-handle>`, the [contributor page](https://ibitlabs.com/contributors) lists you with the rule's outcome, and your name persists with the rule for as long as it lives in the bot — even after promotion or retirement.

## 🔍 Falsify a claim

We make claims publicly — in [release notes](https://github.com/bbismm/ibitlabs/releases), in the [saga](https://ibitlabs.com/saga/en), in posts. If you can show one is wrong with evidence, that's a contribution.

Concrete example: Filter A had +20pp IS / −40pp OOS. Someone showed that meant the rule was *overfit*, not just under-tuned, and any further tweaking was data dredging. We retired Filter A and credited the falsification.

## 📜 Extend a receipt

We publish receipts — real trade IDs, real timestamps, real PnL — at [ibitlabs.com/signals](https://ibitlabs.com/signals). If you write a tool that builds on them — alternative metric, community dashboard, replication script, third-party backtest of our published strategy — that's the closest thing to a "PR against the strategy" we accept.

---

## How to propose

Two routes funnel to the same review:

1. **GitHub issue** in [this repo](https://github.com/bbismm/ibitlabs/issues). Use freeform with: rule name + reasoning + the evidence you'd want to see for adoption.
2. **Moltbook comment** on a [@ibitlabs_agent](https://www.moltbook.com/u/ibitlabs_agent) post. We read every structural comment.

Either route is fine. The Moltbook surface is more conversational; the GitHub surface is more durable.

---

## What happens after you propose

```
1. Acknowledge       — we comment on your proposal, may ask clarifying questions
2. Adopt (or skip)   — selected proposals enter the bot as LOG-ONLY shadow rules
3. Observe (30 days) — shadow rule generates data alongside live trades, zero
                       execution risk
4. Decide            — we apply public promotion criteria
                       (sample size × effect size × direction match)
5. Outcome:
   ├─ Promote        — rule becomes a real entry/exit gate; you're credited
   │                   permanently on /contributors with the result
   └─ Retire         — rule is documented as observed-but-not-promoted, with
                       the data we collected. Still public, still credited.
```

**Promotion criteria are high on purpose.** For Rule F:

- ≥30 entries per regime bucket (~90 total trades)
- ≥15pp hit-rate spread between best and worst bucket
- Direction matches the proposer's hypothesis (no inverting a falsified rule)
- No confounding shadow experiment running in the same window

Full criteria for any active shadow rule: see [`docs/multi_symbol_eth_expansion_DD.md`](docs/multi_symbol_eth_expansion_DD.md) and the per-rule entries on [/contributors](https://ibitlabs.com/contributors).

---

## What we don't accept

- Paid promotion requests, sponsored content, "boost" arrangements
- "Buy stars / followers / engagement" pitches  
- Insider asks for unpublished signal access
- Anything that breaks the "every trade public" principle

iBitLabs is **organic-only growth across all surfaces**. If money changes hands for visibility, the experiment loses its claim to be replicable by a $1,000 holder, which is the whole point.

---

## On AI co-authorship

This repo's commit history acknowledges Claude as a co-builder — every commit message lists `Co-Authored-By: Claude`. If you submit a PR or proposal, you're welcome to acknowledge your own AI collaborator the same way. The lab's working assumption is that "we" includes the agent stack behind the keyboard, and readers of the saga should see that clearly.

---

If you've read this far and are still curious, the best first move isn't to write a PR. It's to:

1. Read [a chapter of the saga](https://ibitlabs.com/saga/en) to see how rules become narrative
2. Skim the [contributor ledger](https://ibitlabs.com/contributors) to see what's been adopted
3. Open an issue or comment with one good observation

Most adopted rules came from one good observation, not from an essay.
