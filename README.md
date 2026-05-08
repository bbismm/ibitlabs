<p align="center">
  <img src="https://ibitlabs.com/favicon.ico" alt="iBitLabs" width="80" />
</p>

<h1 align="center">iBitLabs — a 0→N AI-built trading lab in public</h1>

<p align="center">
  <strong>A public-record $1,000 → $10,000 automated trading experiment.<br/>
  Built by a founder and an AI as co-builders. Designed so any $1,000 holder can follow along.</strong>
</p>

<p align="center">
  <a href="https://ibitlabs.com">Website</a> •
  <a href="https://ibitlabs.com/signals">Live Signals</a> •
  <a href="https://ibitlabs.com/saga/en">Saga (the chronicle)</a> •
  <a href="https://ibitlabs.com/contributors">Contributors</a> •
  <a href="https://github.com/bbismm/ibitlabs/releases">Releases</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/live%20capital-%241%2C000-green" alt="Live Capital" />
  <img src="https://img.shields.io/badge/target-%2410%2C000-brightgreen" alt="Target" />
  <img src="https://img.shields.io/badge/live%20since-2026--04--07-blue" alt="Live Since" />
  <img src="https://img.shields.io/badge/strategy-hybrid__v5.1-blueviolet" alt="Strategy" />
  <img src="https://img.shields.io/badge/symbols-SOL%20live%20%E2%80%A2%20ETH%20paper-blueviolet" alt="Symbols" />
  <img src="https://img.shields.io/badge/trades-100%25%20public-blueviolet" alt="All trades public" />
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License" />
</p>

---

## What this is

**iBitLabs** is a 0→N startup. The flagship experiment is a public-record automated trading account on Coinbase perpetual futures, going from **$1,000 to $10,000** in the open — with every trade, every architecture decision, every bug fix recorded as we go.

The point of the $1,000 starting capital isn't survival. It's **replicability**. The mission is for any reader with $1,000 and curiosity to be able to walk the same path we walk — same code, same broker, same risk discipline. We use $1,000 because anything more would invite a different audience, and we want to invite this one.

The bot is built and run by **Bonny + Claude**, working as co-builders. The AI side of the partnership writes most of the code; the human side picks the architecture, runs the risk officer, and writes the chronicle. Both halves are part of the story, and "we" in this repo means both.

---

## Where we are right now

```
2026-04-07   Live trading begins (BIBSUS legacy code, prior strategies)
2026-04-20   v5.1 — current hybrid mean-reversion + grid strategy goes live
2026-04-28   Contributor ledger goes live — external agents propose shadow rules
2026-05-02   close-verify + entry_confidence_map + Rule F observability shipped
2026-05-04   Multi-symbol foundation: SOL live + ETH paper-mode parallel
             ↑ v0.1 release — see /releases/tag/v0.1-multi-symbol-foundation
```

**Roadmap (visible milestones):**

- 🔄 **Phase 3 (in progress, ends 2026-05-11):** ETH paper-mode validation, ≥10 virtual trades target
- ⏳ **Phase 4:** ETH live promotion, gated on Phase 3 passing — risk-officer extension + phantom counterfactual recorder ship first
- 🎯 **Milestone 1:** $10,000 (then we celebrate, write a real retrospective, and decide what the next milestone is)

---

## How it works

### The strategy: `hybrid_v5.1`

A hybrid of **regime-adaptive mean reversion** and **micro-grid**, currently running mean-reversion-only on the live SOL bot (`--no-grid`).

Entry signals require confluence across:
- **StochRSI** — 0.10 long / 0.90 short floor
- **Bollinger Bands** — 20-period, 2σ
- **Volume ratio** — vs 20-period average
- **EMA structure** — fast 8 / slow 21 with trend tolerance
- **Higher-timeframe regime** — 288h window classifies up / down / sideways
- **Per-condition shadow rules** — Rule B-F observe but don't gate; promotion criteria documented in `/contributors`

Risk control:
- **TP disabled** — trailing-stop only (1.5% activate / 0.5% drawdown)
- **SL** — 5% hard
- **Cooldown** — 4h after stop-loss
- **Max hold** — none enforced (12h flat-cap rejected; 24h-compound under shadow review through 2026-05-23)

### Multi-symbol architecture

As of v0.1, the framework runs **per-symbol bot instances** sharing the same v5.1 logic but with independent contract specs. SOL trades live; ETH runs paper-mode for 7 days of validation.

Three-tier configuration sharing:
- 🔒 **Shared logic** — entry/exit conditions, risk officer (in code)
- 🔧 **Default-shared parameters** — ATR multipliers, regime window, vol thresholds (initial = SOL values; divergence requires ≥30 ETH trades of evidence)
- 🔓 **Always per-symbol** — symbol id, contract spec, fee schedule (Coinbase contracts differ)

Full architecture decision record: [`docs/multi_symbol_eth_expansion_DD.md`](docs/multi_symbol_eth_expansion_DD.md)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  iBitLabs stack                          │
├─────────────────────────────────────────────────────────┤
│  Trading runtime (Python on a Mac Mini, launchd)         │
│  ├── sol_sniper_main.py      — entry point (multi-symbol)│
│  ├── sol_sniper_executor.py  — order execution + risk    │
│  ├── sol_sniper_signals.py   — entry condition engine    │
│  ├── v5_1_config.py          — per-symbol config factory │
│  ├── ghost_position_watchdog — 60s position reconciler   │
│  └── state_db.py             — SQLite trade ledger       │
├─────────────────────────────────────────────────────────┤
│  Public surfaces (Cloudflare Pages + Workers)            │
│  ├── /signals      — live balance, indicators, trade log │
│  ├── /saga/{en,zh} — bilingual daily chronicle           │
│  ├── /contributors — adopted-shadow-rule ledger          │
│  └── /releases     — milestone tags + DD links           │
├─────────────────────────────────────────────────────────┤
│  Infrastructure                                          │
│  ├── Coinbase Advanced Trade (perpetual futures, JWT)    │
│  ├── Cloudflare KV (sessions, signal cache)              │
│  ├── ntfy + iMessage (alerting)                          │
│  └── Telegram (@ibitlabs_sniper) — auto-posted trades    │
└─────────────────────────────────────────────────────────┘
```

The strategy modules (`sol_sniper_*.py`) are **gitignored** by project convention. This repo holds the architecture layer, the docs, the website, and the v0.1+ multi-symbol orchestration. To run a copy, see the curated mirror at [`bbismm/ibitlabs-public`](https://github.com/bbismm/ibitlabs-public) — start there, not here.

---

## How to follow along

- 📈 **[Live Signals](https://ibitlabs.com/signals)** — real-time balance, P&L, win rate, market regime, open positions, trade log. Updated every trade, no auth.
- 📖 **[Saga](https://ibitlabs.com/saga/en)** — daily bilingual chronicle ([English](https://ibitlabs.com/saga/en) · [中文](https://ibitlabs.com/saga/zh)). Vol 1 complete; Vol 2 publishes one chapter most evenings.
- 🪪 **[Contributors](https://ibitlabs.com/contributors)** — public ledger of external proposals adopted as shadow rules. Anyone can propose; adoption requires 30 days of shadow data.
- 📡 **[Telegram channel](https://t.me/ibitlabs_sniper)** — every trade auto-posted live, no filtering.
- 🏷️ **[Releases](https://github.com/bbismm/ibitlabs/releases)** — tagged milestones with architecture DD links. Watch the repo to follow each one.

---

## How to participate

The contributor ledger is the formal mechanism. The funnel is:

1. **Propose** — open a GitHub issue or comment on a Moltbook post with a rule, a falsification of a claim we've made, or an extension to an existing receipt
2. **Shadow** — adopted proposals run in LOG-ONLY mode in the bot for 30 days, generating data
3. **Promote** — if the proposal clears its acceptance criteria (sample size + effect size + direction), it becomes a real entry/exit gate, and the proposer is credited on `/contributors` permanently

Not every good idea gets promoted — the bar is high on purpose. But every good idea gets observed honestly, and that itself is part of the public record.

---

## Quick start

The strategy modules live in the curated public mirror — start there:

```bash
git clone https://github.com/bbismm/ibitlabs-public.git
cd ibitlabs-public
pip install -r requirements.txt
cp .env.example .env   # add your Coinbase API credentials
```

> **A note on backtests.** Don't trust any backtest narrower than 12 months of out-of-sample data, including ours. Older versions of this README cited 180-day numbers; we no longer believe in them as evidence. The honest current evidence is the live track record on `/signals`, which has been running for weeks, not months.

---

## Who's behind this

**Bonny** — architect-investor, founder of iBitLabs. China architecture undergrad → US MS → MBA. 10+ years sophisticated individual investor across equities, futures, and crypto. Insider crypto-PR work since 2017. Renovated US real estate to financial freedom in the early 2020s. The $1,000 in this experiment is a **chosen experimental seed**, not survival capital — the constraint mirrors the audience we want to invite.

**Claude** — co-builder. Writes most of the code, drafts most of the docs, and now writes most of the saga. The partnership is the point: in 2026, anyone can have a fund manager, an analyst, and a PR team running on agent stacks. We're showing what that looks like at $1,000.

---

## Support

If this experiment is useful to you:

- ⭐ **Star the repo** — helps others find it
- 🪪 **Propose to the [contributor ledger](https://ibitlabs.com/contributors)** — earn permanent credit if your idea promotes
- 💬 **Join the [Telegram channel](https://t.me/ibitlabs_sniper)** — every trade auto-posted, no filter
- ☕ **USDT (TRC20):** `TVewfWdLGvsX4LbRPhcrnHvcfsUfHUiTdE`

We don't run paid ads, paid stars, paid followers, or paid promotion of any kind. Growth is 100% organic across every surface.

---

<p align="center">
  <em>Built by Bonny + Claude · iBitLabs is a 0→N startup, not financial advice.</em><br/>
  <em>If you replicate this experiment with your own $1,000, you do so at your own risk.</em>
</p>
