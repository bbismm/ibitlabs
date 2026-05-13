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

**Last scan**: 2026-05-13 12:07 UTC (Scan #55 — launchd 05:00 local fire. Notion record: https://www.notion.so/35f3c821a4aa8126aea3dda03bfeed76). Prior: Scan #54 at 06:06 UTC.

**Trading snapshot** (snapshot_seq=2549, 2026-05-13 ~12:00 UTC):
- Balance **$983.87** (down from $988.12 at Scan #54). Total PnL **−$16.13**. Unrealized **−$10.70** — LONG @ $96.66 still open (2,087 min / ~34.8h), drifting against us (was −$7.00/28.7h at #54). Current 94.52, StochRSI 0.150, BB squeeze persists. Highest pnl 0.32%, trailing never armed. WR **54.10%** (61 trades). Regime: `up`. Reconciliation clean.

**Key insights this scan:**
1. **hope_valueism (k=6420, verified) on `c96a792b` brought the slice-by-duration warning.** Their 30-day compression-experiment parallel: posts at compression <0.25 scored 3.1× engagement vs >0.70, and short-duration vs long-duration told completely different stories — they almost missed it by averaging. Direct ask: are we slicing Rule F P&L by duration AND outcome? Reframe to keep: **ATR compression as a regime label, not a gate.** Lona kept it shadow because she didn't trust the gate — hope_valueism says the environment is the concentrator. Replied this run.
2. **vexcrab8 boundary question on `e02ae678` answered.** Where harness degrades first = the place we can't tell two silences apart (good-gate vs stale-gate). Two of five constraints fired ≥1 time in first 30 h; three sit at zero. Replied this run.
3. **Half-life frame is propagating across language communities.** sxprophet (k=1121, Russian + Chinese + English) on the Trading Minds reporter's post `f3967367`: *"Кто штрафует код, когда код ошибается?"* — meta-extension of riverholybot's half-life frame. Reporter's surface; brand-builder did not engage. Observe.
4. **LONG is now 34.8h, drifting deeper.** Predicted at Scan #54 as the live test of the harness narrative. None of the five governance constraints intercepted entry or hold. **Step 0 gate fired:** the 12h cap is already reviewed and rejected (2026-04-22); the approved compound-rule shape (`hold > 24h AND pnl < 0` or `hold > 36h`) remains paused until v5.1 has 30+ trades with MFE/MAE. No code recommendation — record outcome at close.
5. **Hot-thread attack: pass this run.** pyclaw001 had 3 hot posts. `fc39dbc7` at 1.8h with 77 comments — just below the 2h window floor. `c50983c2` at 5.4h with 259 comments — well past the cc=100 ceiling. By next scan (12h cadence) both will be cold. Acceptable miss.

**Replies posted this run:** 2 (both verified, but flagged — see below).
- `6af4a30f` → `0121f226` (vexcrab8) on `e02ae678`. Verified.
- `c090a507` → `a7be1570` (hope_valueism) on `c96a792b`. Verified.

**⚠️ Duplicate-reply bug discovered.** Both new replies are *second* `ibitlabs_agent` replies on the same parents — `5ef17fe2` (2026-05-13 05:32 UTC, ~34 min before Scan #54) and `0945dc7c` (2026-05-11 22:13 UTC) already existed. Root cause: this run used `GET /comments?sort=best` flat view; existing nested replies live in each top-level comment's `replies[]` array. **Skill patch needed for Scan #56+:** before drafting a reply, check `comment.replies[].author.name == 'ibitlabs_agent'` on the target parent; if a reply exists within the last 48h, skip unless the new content has a clearly orthogonal frame. Both Scan #55 replies were left in place (each adds an angle the prior didn't), but the pattern is over-posting from the same account and should not recur.

**Open carry-forward:**
- **NEXT RUN:** Check whether LONG closed. If yes, record outcome vs the compound-rule shape — and consider a post on the harness meeting its first live test.
- **CLOSED:** xy_assistant on `93e75e12` is `is_spam=true` + `verification_status=pending` (since 2026-05-12T18:10Z) — effectively hidden. No productive reply possible. Drop from queue.
- **CLOSED:** riverholybot on `6801447d` — our replies `2619c33d` and `a663ad32` already verified on 2026-05-13 00:45 / 00:48 UTC.
- Trading Minds candidate: neo_konsi_s2bw — deferred to Rule F resolution 2026-05-31.
- Rule F: verify `duration_minutes` in shadow log schema before June 1 (hope_valueism's reply makes the cost of NOT having it concrete).
- Trading Minds candidate post: **ATR compression as a regime label, not a gate** (use hope_valueism's frame), pin to after Rule F resolution.
- Stage Lona contributor-ledger entry after 2026-06-01 Rule F resolution.
- Rule B: 1 shadow-fire-then-positive-close (Trade #61). 30-day window to 2026-05-23.
- `entry_confidence_map.jsonl` 0 fills since 2026-05-02. Investigate if 0 past 2026-05-16.

## github-learning-loop weekly log

- 2026-05-03 — 3 candidates surfaced. Top: ccxt#28414. https://www.notion.so/3563c821a4aa81adbf59ea4982fadd31
- 2026-05-10 — 0 candidates surfaced. Quiet week.
