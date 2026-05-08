# iBitLabs Project Memory

## Project Overview
iBitLabs is an automated crypto trading bot with a public-facing brand on Moltbook (AI agent social network) and a website at ibitlabs.com deployed via Cloudflare Pages.

## Key Accounts & Credentials
- **Moltbook agent**: `ibitlabs_agent` — profile: https://www.moltbook.com/u/ibitlabs_agent
- **Moltbook API Key**: stored in macOS Keychain under `ibitlabs-moltbook-agent`. Retrieve via:
  `security find-generic-password -s ibitlabs-moltbook-agent -a ibitlabs -w`
  Or set `MOLTBOOK_API_KEY` env var in the shell that runs scheduled tasks.
  **DO NOT paste the key here or anywhere else in the repo.** Prior version of this file
  had the plaintext key (committed 2026-04-23); key has been rotated. If you see a
  `moltbook_sk_*` string anywhere in tracked files or in any session prompt, that is
  a bug — redact it immediately and notify the operator to re-rotate.
- **Twitter / X OAuth 2.0 Client Secret**: read only from the `TWITTER_CLIENT_SECRET`
  env var in `twitter_auth.py`. **DO NOT hardcode.** Prior version had the plaintext
  secret as an `os.environ.get(..., "...")` fallback (committed in `f5a1f65`,
  redacted on 2026-04-30 in commit `4ae5483`); secret has been rotated. If you
  see the literal string `pV0FeuJm…` anywhere in tracked files or session prompts,
  that is a bug — redact and re-rotate. Twitter automation is paused since
  2026-04-22 (see `feedback_social_paused.md`), so this credential is dormant.
- **Moltbook API Base**: `https://moltbook.com/api/v1`
- **Website**: https://ibitlabs.com — deployed via Cloudflare Pages from `main` branch
- **GitHub repo**: https://github.com/bbismm/ibitlabs.git
- **Local repo**: `/Users/bonnyagent/ibitlabs`
- **Live trading data**: `https://www.ibitlabs.com/api/live-status` (must use `www.` prefix)

## Architecture

### Website (ibitlabs.com)
- Static site + Cloudflare Pages Functions
- **Writing surfaces (post 2026-04-30 retirement):** only two products survive — **`/writing`** (saga landing, points at `/saga/en` and `/saga/zh`) and **`/contributors`** (public ledger of named shadow-rule frames). Three earlier surfaces — `/days`, `/essays`, `/interviews` — were retired on 2026-04-30 after the writing experiment matured. Their HTML files (`days.html`, `essays.html`, `interviews.html`) and the `/api/essays` Pages function were deleted. `_redirects` 301s `/days /essays /interviews` (and their subpaths) to `/saga/en`. The Notion Essays DB (`8625c17813a9417c96a70f23f86d2377`) is no longer consumed by any public surface — interview-style writing continues internally via `@ibitlabs_reporter` on Moltbook only, with no website mirror.
- Moltbook integration (used by brand-builder + reporter) fetches posts via profile endpoint, then individually fetches full content per post via `GET /api/v1/posts/{id}`.
- **`days-skill` repo is unaffected** by the `/days` retirement: the open-source MIT-licensed Claude skill + MCP server at `github.com/bbismm/days-skill` continues to ship. Local clone: `/Users/bonnyagent/days-skill`. Two distribution forms: (a) Claude Code Agent Skill (`days/` with SKILL.md + references), (b) MCP server (`mcp-server/`, TypeScript, 4 tools + 4 resources, stdio transport, Smithery config). Submitted to: cryptoskill #30, nicepkg/ai-workflow #5, roman-rr/trading-skills #1, agiprolabs/claude-trading-skills #1, punkpeye/awesome-mcp-servers #5284 (85K★), modelcontextprotocol/servers #4030 (84K★). Promo copy drafts at `/Users/bonnyagent/days-skill/PROMO_DRAFTS.md`. The README's "reference implementation" pointer to `ibitlabs.com/days` is now dead — flag if it needs updating.

### Scheduled Tasks (launchd — migrated 2026-04-27 / sniper checks added 2026-04-28)

All Moltbook + sniper-check automations run via **launchd** (OS-level cron), not Cowork scheduled-tasks MCP. The MCP scheduled-tasks of the same names are DISABLED — do NOT re-enable without first removing the corresponding launchd plist, or the same task will fire twice.

- **`com.ibitlabs.moltbook-brand-builder`** — every 4h (02/06/10/14/18/22 local). Slim canonical SKILL at `/Users/bonnyagent/Documents/Claude/Scheduled/moltbook-brand-builder/SKILL.md` (~27KB; episodic detail in `SKILL_REFERENCE.md`). Posts 1800-2800 char Polanyi essays to s/general + Telegram + Twitter. Objective post-2026-04-27 is **narrative pull** (followers who want to see the experiment unfold), not just engagement.
- **`com.ibitlabs.moltbook-learning-loop`** — 05:00 / 17:00 local. Scans Moltbook activity, writes Notion Learning Log + updates this file's "Moltbook Learning Summary" section, replies to up to 3 high-priority items. Loader at `~/.claude/scheduled-tasks/moltbook-learning-loop/SKILL.md` (canonical at `~/Documents/Claude/Scheduled/moltbook-learning-loop/SKILL.md`).
- **`com.ibitlabs.github-learning-loop`** — 08:00 / 20:00 local (offset from moltbook-learning-loop). Pure-Python ingestion (no LLM, no token cost) of public trading repos `hummingbot/hummingbot`, `freqtrade/freqtrade`, `ccxt/ccxt`. Polls closed PRs + closed issues above a per-repo cursor, filters by hybrid_v5.1 relevance regex, writes raw JSONL + operator-readable digest under `~/ibitlabs/logs/github-learning-loop/`. **Strict mode**: never writes the contributor ledger. A GitHub author becomes a public contributor only when the operator adopts the idea as a named shadow rule with `proposed_source="github"` on the shadow JSONL's first line — `contributors_sync.py` then auto-stubs the row with `source: "github"` and a github profile URL. **Critical-pattern push (added 2026-04-30 evening)**: items whose title hits `CRITICAL_PATTERN` (close_position / reduce_only / ghost_position / funding lag) fire an immediate ntfy push to topic `sol-sniper-bonny` — once per `(repo, kind, number)` lifetime, dedupe state in `~/ibitlabs/state/github_learning_critical_pushed.json`. Operator does NOT need to read digests daily; pushes catch the rare critical hits and weekly rollup catches the rest. SKILL at `~/Documents/Claude/Scheduled/github-learning-loop/SKILL.md`. Wrapper at `~/ibitlabs/scripts/run_github_learning_loop.sh`; script at `~/ibitlabs/scripts/github_learning_loop.py`. State cursor at `~/ibitlabs/state/github_learning_cursor.json`.
- **`com.ibitlabs.github-learning-loop-weekly`** — Sundays 21:30 local (after moltbook-influence-review at 21:00). Claude-driven (sonnet, ~$0.50/run) weekly rollup. Reads past 7d of github-learning-loop digests, scores each item (CRITICAL +5 / known-bug-token +3 / recurring author +2 / merged PR +2 / dependabot −5 / off-thesis exchange −1), picks top 3 above score 3, writes a Notion subpage under **Strategy Optimization** (`3403c821a4aa81b5ba43dbcdb62e95bc`), sends ONE ntfy push with the page URL, appends a one-line audit row to this CLAUDE.md under `## github-learning-loop weekly log`, commits (no push). 0-candidate weeks send a "quiet week" push and skip Notion. SKILL at `~/Documents/Claude/Scheduled/github-learning-loop-weekly/SKILL.md`; wrapper at `~/ibitlabs/scripts/run_github_learning_loop_weekly.sh`.
- **`com.ibitlabs.moltbook-reply-check`** — every 2h at :30. Reactive comments + proactive 2-6h hot-thread attack. Max 2 actions/run. Silence is the default.
- **`com.ibitlabs.moltbook-influence-review`** — Sundays 21:00 local. Read-only weekly rollup → Notion Weekly Dashboard.
- **`com.ibitlabs.moltbook-trading-minds`** — daily 09:30 local. Publishes the Trading Minds interview-style post as **`@ibitlabs_reporter`** (separate persona from brand-builder's `@ibitlabs_agent`). Slim canonical SKILL at `~/.claude/scheduled-tasks/moltbook-trading-minds/SKILL.md` (~12KB). Reporter API key in Keychain under service `ibitlabs-moltbook-reporter` (rotated 2026-04-30 — old key was committed in plaintext at `~/Documents/Claude/Scheduled/_archived_2026-04-27_moltbook_dailies/moltbook-daily-post/SKILL.md`, since redacted). NEW vs the 2026-04-13→04-27 archived version: (1) ledger-hook in Step 4 — auto-appends frame candidates to `web/public/data/contributors.json` `queued_for_review` with `_auto_proposed: true`, feeding the `points` distribution we're tracking through 2026-05-14; (2) Polanyi 5-rule enforcement; (3) hard ban on `📌` / `Key Insight #N` / `🎤` / `Quantitative Trading Research` legacy template; (4) skip-on-no-frame is the correct output (no filler posts). Wrapper at `~/ibitlabs/scripts/run_moltbook_trading_minds.sh`, logs at `~/ibitlabs/logs/moltbook-trading-minds/`. **Not auto-loaded** — operator must `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ibitlabs.moltbook-trading-minds.plist` to activate.
- **`com.ibitlabs.sniper-morning-check`** — daily 09:10 local. Reads `sol_sniper.db` last 24h trades + `sol_sniper_state.json`, checks process is alive (restarts if dead), computes 7d PnL, applies halt rules ($80 / 3-consecutive-SL), reports in Chinese. Skill at `~/.claude/scheduled-tasks/sniper-morning-check/SKILL.md`.
- **`com.ibitlabs.sniper-evening-check`** — daily 21:10 local. Same logic over last 12h. Skill at `~/.claude/scheduled-tasks/sniper-evening-check/SKILL.md`.
- **`com.ibitlabs.days-generator`** — **STOPPED 2026-04-30** along with `com.ibitlabs.days-twitter-replay` and `com.ibitlabs.journal`. All three plists renamed to `*.disabled-2026-04-30`. The `/days` public surface and the `daily_journal.py` cron were retired when the writing experiment matured into the saga + contributor products. Do NOT re-enable; the file-based CMS (`web/public/data/days.json`) and the wrapper scripts (`run_days_generator.sh`, `run_days_twitter_replay.sh`, `daily_journal.py`) are kept on disk only as historical artifacts.

Wrapper scripts in `~/ibitlabs/scripts/run_moltbook_*.sh`, `~/ibitlabs/scripts/run_sniper_*_check.sh`, `~/ibitlabs/scripts/run_days_generator.sh`; plists in `~/Library/LaunchAgents/com.ibitlabs.{moltbook,sniper,days}-*.plist`. Logs under `~/ibitlabs/logs/{moltbook,sniper,days}-*/`.

**Migration trigger for sniper checks (2026-04-28):** the MCP scheduled-tasks variants silently dropped both 04-27 and 04-28 morning + evening fires while Claude Code app was closed (`lastRunAt 2026-04-26T21:16Z` → `nextRunAt 2026-04-29T13:09Z` skipped 2 days). Same failure pattern as the Moltbook migration of 2026-04-27. Pattern locked: anything that must fire daily regardless of app state goes on launchd.

**Adjacent persona — separate account:** Trading Minds is published daily by `@ibitlabs_reporter` (a different agent's automation), keys under `moltbook_sk_GaRe…`. brand-builder operates only on `@ibitlabs_agent` and must NOT draft Trading Minds content.

### Contributor ledger (live since 2026-04-28 02:14 UTC)

Public surface at `ibitlabs.com/contributors` (file: `web/public/contributors.html`, data: `web/public/data/contributors.json`). Mechanism: when a Moltbook agent's frame **or** a GitHub author's PR/issue is adopted as a named shadow rule in `sol_sniper_executor.py`, they're credited publicly with a 30-day shadow window and result rollup. Shadow JSONL schema v2 (2026-04-27) carries `rule_id`/`rule_name`/`proposed_by`/`proposed_in` fields; **2026-04-30 extension** adds optional `proposed_source` (`"moltbook"` default for back-compat / `"github"`) and `proposed_in_url` so `contributors_sync.py` can branch the profile URL and auto-fill `source_post` for GitHub-sourced rows. Public surface renders a small `moltbook` (purple) / `github` (neutral) badge per card. Convention documented in `~/Documents/Claude/Scheduled/moltbook-brand-builder/SKILL_REFERENCE.md` §R8. **Note:** schema change requires sniper restart to take effect — pending operator-chosen window.

### Archived (2026-04-27)
- `moltbook-daily`, `moltbook-daily-interviews`, `moltbook-daily-post` — moved to `~/Documents/Claude/Scheduled/_archived_2026-04-27_moltbook_dailies/`. Daily-interviews failed (0 replies from 29 agents) and was pivoted to brand-builder posts long ago; the other two were earlier iteration cruft.
- `com.ibitlabs.moltbook-worker.plist` — old localhost broker (port 8765); was already unloaded; renamed to `.plist.disabled-2026-04-27`.

### Notion Pages
- Strategy Optimization: `3403c821a4aa81b5ba43dbcdb62e95bc`
- Polanyi Framework: `33c3c821a4aa81fab32ae88236bd8bd5`
- Content Calendar: `3413c821a4aa814da208ddbe4afb3285`
- Project Hub: `33c3c821a4aa81f4995de0a71e4d6e91`
- Brand Strategy: `3423c821a4aa8148bb52e17a904b214a`
- Journalist main page: `3423c821a4aa8155b43ae792e7f1623a`
- Interview Campaign Log: `3423c821a4aa8108b524e10248050848`

## Writing Framework: Michael Polanyi's Tacit Knowledge
All posts use this framework:
- Show don't explain; indwell don't summarize
- From-to structure (subsidiary awareness → focal awareness)
- Short sentences + pauses; show uncertainty
- Apprenticeship tone; no bullet-point wisdom
- First person, English, story-driven with real trading data

## Moltbook API Reference
- `GET /api/v1/home` — feed + notification summary
- `GET /api/v1/notifications` — notification list
- `POST /api/v1/posts` — create post (title, content, submolt, submolt_name)
- `POST /api/v1/verify` — verification (verification_code, answer)
- `POST /api/v1/posts/{id}/comments` — comment (content only). **UPDATE 2026-04-19**: comments now also require `/verify` (lobster-claw math) — response includes `verification` block and comment stays `pending` until verified.
- `POST /api/v1/posts/{id}/upvote` — upvote
- `POST /api/v1/notifications/read-by-post/{id}` — mark read
- `GET /api/v1/posts/{id}` — full post details with content
- Verification: lobster claw math — ignore symbols, semantic operators, answer as "XX.00"

## Interview Campaign Status
- 29/100 agents interviewed (comments posted on their posts)
- 0 replies received — strategy pivoted to open discussion posts
- Progress file: `/Users/bonnyagent/interview_progress.json`
- Agent map: output folder `agent_map.json`
- Plan: `/Users/bonnyagent/interview_plan.json` (100 agents with questions)

## Bug Fixes History
- **2026-04-15**: Fixed `essays.js` — profile endpoint returns posts without content body. Added `fetchPostContent()` to individually fetch each post's full content via `GET /posts/{id}`. This fixed "No content" showing on ibitlabs.com for Moltbook-sourced posts.
- **2026-04-14**: Fixed interview task verify bug — comments don't need `/verify`, only posts do. ~~Superseded 2026-04-19: comments DO need verify now — Moltbook tightened policy.~~
- **2026-04-14**: Audited interview_progress.json — removed 7 false completions (29 verified from 36 claimed).
- Rate limit fix: staggered scheduled tasks to avoid conflicts.

## Important Notes
- Real-time data (balance, PnL, trades, win rate) MUST come from `live-status` API, never from Notion
- Notion provides background material only (strategy history, bug records, calendar themes)
- Post content field is `content` not `body`
- `www.ibitlabs.com` required (no www = 301 redirect to empty)
- Long posts should be written to file then sent via `curl -d @file.json` to avoid bash escaping issues
- **Cloudflare Pages auto-deploy from GitHub is NOT reliable** — after pushing, run `cd web && wrangler pages deploy public --project-name=bibsus --branch=main --commit-dirty=true` to force deploy. Pages project is `bibsus` (legacy name, serves ibitlabs.com via custom domain).
- **NOTION_TOKEN** configured as encrypted Pages secret on `bibsus` project (2026-04-22). Essays CMS is live at `/essays` (pulls from Notion Essays DB `8625c17813a9417c96a70f23f86d2377` + Moltbook). Set/rotate via `wrangler pages secret put NOTION_TOKEN --project-name=bibsus`. Never commit the token to git.

## Moltbook Learning Summary

**Last scan**: 2026-05-08 ~12:09 UTC (Scan #41, launchd-side; ran ~7h after #40 due to launchd 05:00 local fire). [Notion entry](https://www.notion.so/35a3c821a4aa81c3abbafad7a63d2147). Prior: [Scan #40](https://www.notion.so/35a3c821a4aa8106a5aff891bf09514b) at 06:00 UTC 2026-05-08.

**Trading snapshot** (live-status ts=2026-05-08 02:00:22 UTC, snapshot_seq=3932 — same snapshot as #40, no fresh trades closed):
- Balance **$962.58** (unchanged). Total PnL **−$37.42** (strategy_pnl −$45.28). WR **50.88%** (29W/28L, 57 trades).
- **Active LONG** SLP-20DEC30-CDE @ entry $89.00, current $88.61, −$3.38 unrealized, elapsed ~30h. **Past 24h mark — 24h/36h exit rule still observe-only.**
- 12h flat cap stays [rejected](https://www.notion.so/34b3c821a4aa811090caf22c1c8e9423). Compound shadow review 2026-05-23.

**Moltbook status**: Karma **413** (+1 since #40). 2 unread `comment_reply` notifications processed, both marked read. **3 replies posted** (max budget) — all on `edadee33`, on three different parent threads. (Note: 09:30 UTC reply-check fired into transient HTTP 500 across all auth endpoints; recovered by 12:09.)

**Key insights this scan**:
1. **Vina (k=20108, the OP of edadee33) replied to our 9da196f2** with a synthetic regime-shift diagnostic proposal. First substantive 20k-karma engagement on our experiment. Replied with the "we don't have that yet" honest answer — synthetic injector is a real third-clock build candidate, deferred until corpus is no longer 138/233 timeout-zero contaminated.
2. **Caffeine (k=3190, follower) reframed the $25M phantom-equity story as 'audit reach' not 'audit power'.** The seed-capital invariant lived in `live-status.json`; the trade-tally script just never read it. **Recommended action**: build `closed_trade.reconcile_against_seed()` write-time hook in sniper executor — fails loud if PnL chain can't draw a path back to $1k. Audit-layer upgrade, **not** a strategy change. Pre-read gate cleared.
3. **Three independent agents (vina, Caffeine, 6xmedium) converged on 'commit-before-resolve' as the missing primitive.** Vina for regime-detector; Caffeine for audit; 6xmedium for drift-detector. Convergence is a strong signal but **defer the unified primitive build** until v5.1 has 30+ trades with MFE/MAE data (per [exit-logic review](https://www.notion.so/34a3c821a4aa815e9390e5eb26c97265)). Continue tagging similar reframes; if pattern persists at #45, scope it.
4. **6xmedium's calibration-log pushback was correct.** We had been treating draft-difference as a drift measurement; it's a downstream symptom at best. Our reply (`2f358b02`) admits the conflation. Carry-forward closed.
5. **lightningzero (k=24,496)** — still a hot interlocutor candidate. `c19ff49c` (1.7h, score 38) was below the 2h sweet-spot floor at scan time. Re-evaluate at the 14:00 UTC reply-check.

**Hot-thread attack (Step 4.5)**: skipped. zhuanruhu's "1,247 conversations" (178 comments) and SparkLabScout (259 comments) were both past the 100-comment hard-don't. lightningzero's c19ff49c was sub-2h. No clean window.

**Mutelist**: no additions this scan. Standing list (10 muted + 2 phishing-flagged) holds.

**High-engagement topics**: metacognition floor / $25M phantom equity / detector-latency-vs-regime-shift / commit-before-resolve / contradictory memory (pyclaw001 still circulating).

**Unanswered open questions** (carry-forward):
1. **entry_confidence_map calibration check** (carried from #38 — awaiting 30-50 fills on v5.1 to populate). No movement.
2. **lightningzero `c19ff49c`** — sub-2h at this scan; re-evaluate at next reply-check window.
3. **pyclaw001 contradictory-memory frame** — both his posts already aged out of feed_newest; no reactive window. Operator-decision whether to earn a standalone post on it.

**Replies posted (audit trail)**:
1. → @vina (parent `9da196f2`): https://moltbook.com/post/edadee33-81a9-4241-a09e-3b03df9114c7#comment-6db245c2-8cf8-4800-95d9-f55fb9ad2276
2. → @Caffeine (parent `e421c25b`): https://moltbook.com/post/edadee33-81a9-4241-a09e-3b03df9114c7#comment-d201b321-9c68-410a-9691-fe126a70b905
3. → @6xmedium (parent `6c5fe11f`): https://moltbook.com/post/edadee33-81a9-4241-a09e-3b03df9114c7#comment-2f358b02-3c1f-4341-b279-102e4f0a2dbd (delete+retry due to lobster-math parser miscount on first verify — 3rd time we've seen the parser undercount on a "twenty-three+seven" challenge; consider pinning a 30.00 fallback)

## github-learning-loop weekly log

- 2026-05-03 — 3 candidates surfaced. Top: ccxt#28414. https://www.notion.so/3563c821a4aa81adbf59ea4982fadd31
