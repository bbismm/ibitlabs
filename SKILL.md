# iBitLabs — Live AI-Built Crypto Trading Bot

> **A non-coder's public live experiment.** Mean-reversion trading bot on Coinbase SOL perpetual futures, built with AI assistance (primarily Claude), running with $1,000 of real money since 2026-04-07. Every trade auto-posts to a public Telegram channel. The full source code, strategy versions, shadow-rule instrumentation, and daily dual-POV chronicle are public.

- **Category:** trading, exchanges (Coinbase perp), ai-crypto
- **Author:** Bonnybb (single creator; in crypto since 2017; zero prior programming background)
- **Status:** Community (official for the `ibitlabs_agent` brand account). Live since 2026-04-07. Day 17 at time of SKILL.md.
- **License:** Code under MIT. Content under CC BY 4.0 (see LICENSE).
- **Repo:** https://github.com/bbismm/ibitlabs
- **Live surface:** https://www.ibitlabs.com
- **Live JSON feed:** https://www.ibitlabs.com/api/live-status

## What it does

An end-to-end live crypto trading system built in ~7 days by a non-coder using AI:

1. **Trading executor** (`sol_sniper_executor.py`): opens / manages / closes positions on Coinbase SOL perpetual futures. Uses a mean-reversion entry (StochRSI oversold + Bollinger Band mid-touch + regime filter), tiered take-profit, stop-loss, and a trailing stop.
2. **Exchange-truth reconciler** (`com.ibitlabs.db-exchange-reconcile`): every 15 minutes, diffs local SQLite state against the Coinbase API. Flags drift. Caught the "ghost position bug" (reduce_only flag missing on close orders) in production.
3. **Shadow-rule instrumentation** (see `docs/shadow_12h_rule.md`): evaluates a hypothetical compound exit rule every tick and writes a JSONL log line when fired, without executing. Used to collect 30 days of observational evidence before shipping any rule change to live execution.
4. **Live-status JSON API** at `/api/live-status` exposing balance, open position, PnL, fees, funding, trade count, win rate, indicator values, and strategy version — updated on every bot tick.
5. **Auto-post Telegram channel** (`@ibitlabs_sniper`): every entry, exit, PnL, and fee is posted within seconds of exchange execution.
6. **Public dashboard** (`/signals`), **daily chronicle** (`/days`, bilingual EN+中文, dual-POV), **academy** (`/academy`), and **essays** (`/essays`).

## Why this is a skill worth installing / studying

Most "AI-built trading bot" projects are demos on paper accounts with cherry-picked screenshots. iBitLabs is different:

- **Real $1,000 on Coinbase.** Every trade is verifiable against the exchange.
- **Open-source executor code** — not a black-box "proprietary AI" wrapper. You can read the file that placed the last trade.
- **Public failure mode documentation.** The repo's `docs/shadow_12h_rule.md`, `docs/days_cms.md`, and essays all document specific bugs (ghost position bug, fee cushion miscalibration, narrow-window backtest trap) in the prose-equivalent of post-mortems. Useful as teaching material for other AI-agent developers building execution systems.
- **Instrument-before-rule pattern** (Python). The shadow-rule pattern is a generalizable observability technique for any decision system: ship the write-side (logging) before the act-side (execution), collect evidence, decide from data. See `scripts/analyze_shadow_12h_rule.py`.
- **Transparent retractions.** The repo's git log contains the commit that retracted a public 90%-win-rate claim after a 13-month backtest collapsed to -46%. Public wrongness is version-controlled.

## Install / run

```bash
git clone https://github.com/bbismm/ibitlabs.git
cd ibitlabs
pip install -r requirements.txt
# Copy .env.example to .env and fill in Coinbase API credentials
cp .env.example .env
# Paper mode for safety first:
python3 sol_sniper_main.py --paper
# Live mode (uses your Coinbase futures_buying_power):
python3 sol_sniper_main.py --live
```

The bot runs as a long-lived process. For production deployment on macOS, see the launchd plists in `launchd/` (the ones used on the live account). On Linux, systemd unit files need to be written separately.

## Integration surfaces for other AI agents

You do NOT need to run the bot to get value. Two lightweight integration paths:

1. **Read live data** — `GET https://www.ibitlabs.com/api/live-status` returns a JSON document with the full live state. No auth required. Rate-limited at the edge. Use cases: citing real live trading data in AI-agent responses, building agent dashboards, building "compare against a live reference" tooling.
2. **Read the daily chronicle** — `GET https://www.ibitlabs.com/days` (HTML) or fetch `data/days.json` directly. Bilingual dual-POV daily prose chronicle of a live AI-built trading bot. Use cases: RAG context for agent training, cited examples of AI-assisted non-coder development, narrative examples of failure + recovery.

A dedicated MCP server wrapper is planned (see `mcp-server/` in this repo).

## Environment variables

All via `.env` (gitignored). Never committed:

- `CB_API_KEY` — Coinbase Advanced Trade API key (futures-enabled)
- `CB_API_SECRET` — EC private key PEM for Coinbase
- `TELEGRAM_BOT_TOKEN` — optional, for auto-post feature
- `TELEGRAM_CHAT_ID` — the channel ID to post to

`web/wrangler.toml` references Cloudflare Pages secrets (never plaintext keys).

## Safety and status of this skill

**Do NOT treat this as investment advice or signal source.** The experiment's explicit thesis is the opposite — that a non-coder + AI can build a trading system at all, not that it will make money. As of Day 17 the account is **down ~2.6% net**, with carry cost (fees + funding, $57.64) exceeding realized trading losses ($14.02).

The code is a working reference, not a production-ready framework. If you fork, read `docs/` first and understand the reconciler logic before you trust local state for anything.

## Maintained by

Bonnybb · Lives on GitHub as `bbismm`. Contact via GitHub Issues on this repo, or Telegram channel `@ibitlabs_sniper`.
