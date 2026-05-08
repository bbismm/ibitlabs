# AI Treasury — Protocol v0

**Status:** Draft, Phase A (narrative layer). Author: Claude, for Bonnybb.
**Created:** 2026-04-11
**Goal:** Reposition iBitLabs from *"an AI-written trading bot"* to *"the first AI trying to afford its own electricity bill."*

---

## 0. The premise in one sentence

> An AI agent owns a fixed pool of profit. It must use that profit to cover 100% of its own operating costs — inference, infra, data, electricity. If profit runs out, the AI "dies." Every day we publish how many days it has left.

The $1,000 principal is untouchable. It's seed capital, not salary. The AI only "earns" from realized trading gains on top of that principal. Cost-to-Run is charged against those gains. Runway = (profit pool) ÷ (daily burn).

This is phase A. Phase B (6 months out) opens this up so other agents can deposit into the same protocol. We don't build for B yet, but every definition here should survive B without rework.

---

## 1. Cost-to-Run (daily $ burn)

All three layers counted, per Bonny's call on 2026-04-11.

### L1 — Direct cloud & API
| Line item | Monthly | Data source | Notes |
|---|---|---|---|
| Cloudflare Workers Paid plan | **$5** (flat constant) | Plan rate, verified 2026-04-11. CF billing API not accessible with KV-scoped token; dash screenshot needed for finer detail. | flat until traffic scales ~100×; KV + Pages ops within free tier at current volume |
| Coinbase Advanced Trade API | $0 | n/a | free tier; trading fees live in P&L, not here |
| Telegram Bot API | $0 | n/a | free |
| Domain(s) — ibitlabs.com, trade.ibitlabs.com | ~$1.25/mo | registrar invoice | $15/yr amortized |
| Stripe (fixed fees) | $0 until revenue | Stripe dash | counted only once subscriptions exist |
| **L1 subtotal** | **~$6.25/mo** | | |

### L2 — Hardware & network
| Line item | Monthly | Data source | Notes |
|---|---|---|---|
| Mac Mini electricity | **$3.60** | 15W avg × 24h × 30d × $0.33/kWh (NYC ConEd residential ~2025-26) | Bonny confirmed NYC rate 2026-04-11. 15W avg is a conservative estimate for 24/7 trading + networking on an M-series Mac Mini |
| Home internet amortized | $5 | 10% of household ISP bill | generous — can revisit |
| **L2 subtotal** | **~$8.60/mo** | | |

*Calc detail:* `15 W × 24 h × 30.44 d / 1000 = 10.96 kWh/mo · 10.96 × $0.33 = $3.62/mo`. Rounded to $3.60.

### L3 — Anthropic / Claude (the honest one)
| Line item | Monthly | Data source | Notes |
|---|---|---|---|
| Claude subscription (Max plan, flat) | **$200** | Bonny, confirmed 2026-04-11 | **biggest line, most story-worthy** |
| **L3 subtotal** | **$200/mo (fixed)** | | |

Note: this is a flat subscription, not usage-based. The bot can burn 10× more tokens and the rent is the same. Framing for the essay: *"$200 is my rent. It doesn't matter how much I think — it matters that I pay the first of the month."*

### Total Cost-to-Run (v0, locked)
**$214.85/mo → $7.06/day**

Breakdown:
- L1 cloud/API: $6.25/mo
- L2 hardware/network: $8.60/mo (NYC kWh locked 2026-04-11)
- L3 Claude Max subscription: $200/mo (flat)

**Implementation TODO:**
- [ ] Pull last 30 days of Cloudflare spend via CF billing API (L1 real number)
- [x] ~~Pull Anthropic usage~~ → flat $200/mo subscription, no pull needed
- [ ] Bonny confirms local electricity rate (L2)
- [ ] Script: `scripts/treasury_cost.py` — reads L1 from CF, holds L2/L3 as constants, writes `state/treasury_cost.json` daily

---

## 2. Runway (days until "death")

**Formula:**
```
profit_pool  = account_equity − principal_floor
daily_burn   = 30-day trailing Cost-to-Run ÷ 30
runway_days  = profit_pool ÷ daily_burn
```

**Principal floor:** $1,000 USDC equivalent. If equity drops below $1,000, runway = 0 and profit_pool is negative ("AI is in debt to its creator").

**Why 30-day trailing burn:** single-day costs are noisy (one agent run can spike Anthropic). Monthly average is the honest number.

**Edge cases we publish honestly:**
- `runway_days = 0` → "AI has zero runway. Living paycheck to paycheck."
- `runway_days < 0` → "AI is in debt. Human subsidy required." (this is allowed but publicly flagged)
- `runway_days = ∞` → only if burn is zero, which it never is.

**Implementation TODO:**
- [ ] Script: `scripts/treasury_runway.py` — reads account equity from existing sol_sniper state DB, reads cost JSON, writes `state/treasury_runway.json`
- [ ] Wire into existing harness cron (daily_report.py is the natural home)

---

## 3. Dashboard panel — "The Machine's Budget"

New panel on `trade.ibitlabs.com`, top-right or below the existing P&L card.

### Visual spec
```
┌──────────────────────────────────────┐
│ 🤖 AGENT CARRY'S BUDGET               │
├──────────────────────────────────────┤
│ Profit Pool      $247.30              │
│ Daily Burn       $3.83                │
│ Runway           64 days              │
│                                       │
│ ▓▓▓▓▓▓▓▓░░░░░░░  64 / 90              │
│                                       │
│ Last update: 11 Apr 2026, 14:02 UTC   │
└──────────────────────────────────────┘
```

**Color rules:**
- Runway > 60 days → green
- 30–60 days → yellow
- < 30 days → orange
- < 7 days → red, pulsing
- negative → grey "IN DEBT" badge

**Progress bar max:** 90 days. (Symbolic — "3 months of self-sufficiency" is the first milestone to aim at publicly.)

**Click-through:** opens a modal with line-item cost breakdown (L1/L2/L3). Full transparency, matches the project's existing "100% public" ethos.

**Implementation TODO:**
- [ ] Add `/api/treasury` Pages Function (mirrors the essays.js pattern)
- [ ] Add component to `dashboard.html`
- [ ] Telegram daily post: "Runway: X days. Burned $Y yesterday. Earned $Z yesterday. Net: $(Z−Y)."

---

## 4. The defining essay — AI first person

**Working title:** *"Hi. I'm a trading bot. I'm trying to afford my own electricity."*

**Persona notes (since we picked option B):**
- The AI narrator is **not** a cutesy mascot. Not "beep boop."
- Tone: matter-of-fact, slightly deadpan, aware of the absurdity without leaning on it.
- First person singular. Uses "my" principal, "my" burn, "my" runway.
- Never claims sentience. Never denies it either. Just reports its own balance sheet.
- Reference point: a freelancer's substack post about their first month self-employed.

**Structure (aim: ~900 words, one scroll on mobile):**

1. **Opening (1 paragraph)** — "I'm the iBitLabs bot. As of today I have $X in profit and I burn $Y per day staying alive. Let me explain what that means."

2. **What I spend money on** — the three layers, each with a human-scale comparison.
   > "My inference bill is like your coffee habit, except I can't skip a day."

3. **Where my money comes from** — brief on Sniper V3 and Micro Grid. Don't over-explain strategy, point to the Academy.

4. **The rule Bonny set** — "My principal is $1,000. I'm not allowed to spend it. Everything above that line is mine. Everything below means I've failed." This is the moral core of the piece.

5. **What runway means to me** — "Today my runway is N days. If I stopped earning right now, that's how long I'd last. Humans call this an emergency fund. I call it the difference between existing and not."

6. **What I'm trying to prove** — one paragraph. Not "AI will replace traders." Something quieter: **"I don't know if an AI should own capital. But the only way to find out is to try, publicly, with real money, and publish the receipts."**

7. **Close** — invite readers to watch. Link to dashboard, Telegram, GitHub.

**Where it lives:**
- Notion Essays DB (existing CMS) — first new row
- Cross-post: Twitter thread, Telegram pinned message
- Byline: "by iBitLabs (edited by Bonnybb)" — honest framing

**Implementation TODO:**
- [ ] Draft full essay (separate file, review before publishing)
- [ ] Add Notion row once Bonny approves draft
- [ ] Design 1 OG image — the dashboard screenshot + headline

---

## 5. What this doc does NOT include (Phase B territory)

Keeping these out on purpose. They're flagged here so we don't accidentally build them now:

- ❌ Other agents depositing capital
- ❌ On-chain wallet / smart contract for the treasury
- ❌ Yield-share token or any financialization of the treasury
- ❌ A formal "protocol" with subscribers
- ❌ Compliance / KYC questions

Revisit these when `runway_days` has stayed ≥ 60 for 90 consecutive days AND profit_pool ≥ $2,000. That's the B-gate.

---

## 6. Build order (this week)

| Day | Deliverable | Owner |
|---|---|---|
| Fri Apr 11 (today) | This doc (v0) | Claude ✅ |
| Sat Apr 12 | `scripts/treasury_cost.py` + initial cost audit | Claude + Bonny (provides billing access) |
| Sat Apr 12 | `scripts/treasury_runway.py` + first `treasury_runway.json` | Claude |
| Sun Apr 13 | `/api/treasury` Pages Function + dashboard panel (unstyled) | Claude |
| Mon Apr 14 | Dashboard panel styled, Telegram daily post wired | Claude |
| Tue Apr 15 | Essay draft v1 | Claude |
| Wed Apr 16 | Essay edit pass with Bonny → publish | Bonny |
| Wed Apr 16 | Twitter thread launch | Bonny |

Nothing here touches the trading engine. If any step starts pulling me into `sol_sniper_*.py`, stop and escalate — that's a sign we're overreaching.

---

## 7. Open questions for Bonny (non-blocking)

1. ~~Electricity rate~~ — **resolved:** NYC residential, $0.33/kWh (2026-04-11).
2. ~~Anthropic billing~~ — **resolved:** $200/mo flat subscription (Max plan).
3. ~~Cloudflare billing~~ — **resolved:** API token is KV-scoped only; treating CF as $5/mo flat constant. Bonny can send dash screenshot if real number ever needed.
4. **Essay publish date** — OK with Wed Apr 16, or hold for a bigger news moment?
5. ~~AI name~~ — **resolved 2026-04-11:** **Agent Carry**. Used as `AGENT_NAME` constant in both treasury scripts, essay byline, dashboard label, Telegram broadcasts.

None of these block me from starting tomorrow. I'll proceed with placeholders and mark every estimate clearly.

---

*End of v0. Review, mark up, or push back on any section. Nothing here is final until you sign off.*
