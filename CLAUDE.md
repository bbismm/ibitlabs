# iBitLabs Project Memory

## Project Overview
iBitLabs is an automated crypto trading bot with a public-facing brand on Moltbook (AI agent social network) and a website at ibitlabs.com deployed via Cloudflare Pages.

## Key Accounts & Credentials
- **Moltbook agent**: `ibitlabs_agent` — profile: `https://www.moltbook.com/u/ibitlabs_agent`
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
- **Website**: `https://ibitlabs.com` — deployed via Cloudflare Pages from `main` branch
- **GitHub repo**: `https://github.com/bbismm/ibitlabs.git`
- **Local repo**: `/Users/bonnyagent/ibitlabs`
- **Live trading data**: `https://www.ibitlabs.com/api/live-status` (must use `www.` prefix)

## Architecture

### Website (ibitlabs.com)
- Static site + Cloudflare Pages Functions
- **Writing surfaces (post 2026-04-30 retirement):** only two products survive — **`/writing`** (saga landing, points at `/saga/en` and `/saga/zh`) and **`/contributors`** (public ledger of named shadow-rule frames). Three earlier surfaces — `/days`, `/essays`, `/interviews` — were retired on 2026-04-30 after the writing experiment matured. Their HTML files (`days.html`, `essays.html`, `interviews.html`) and the `/api/essays` Pages function were deleted. `_redirects` 301s `/days /essays /interviews` (and their subpaths) to `/saga/en`. The Notion Essays DB (`8625c17813a9417c96a70f23f86d2377`) is no longer consumed by any public surface — interview-style writing continues internally via `@ibitlabs_reporter` on Moltbook only, with no website mirror.
- **`/receipt/viewer/` public verifier (2026-05-16):** mirror of the static viewer from `~/Documents/receipt/viewer/` at `web/public/receipt/viewer/`. URL `https://www.ibitlabs.com/receipt/viewer/?chain=<url>` — paste any Receipt-spec chain URL (or click the prefilled iBitLabs demo link), browser recomputes all SHA-256 hashes via `crypto.subtle.digest`, renders Verified verdict. The demo link auto-refreshes to the latest IPFS-anchored chain via cross-origin fetch of `https://bbismm.github.io/receipt/latest.json` (single source of truth, updated daily 22:00 local by `~/ibitlabs/scripts/publish_latest_anchor.sh`). Sibling mirror on GH Pages: `bbismm.github.io/receipt/viewer/`. Original plan `receipt.ibitlabs.com` is blocked on OLD CF account access (see `project_bibsus_retirement.md`); this path-based mirror is the workaround until that unblocks. Bare `ibitlabs.com/receipt/...` 301-redirects to `www.` — always use `www.` in launch copy. Receipt protocol 30-day clean-realtime gate ends 2026-06-10 02:43 UTC; loud launch (Moltbook post + GitHub Release) gated until then.
- Moltbook integration (used by brand-builder + reporter) fetches posts via profile endpoint, then individually fetches full content per post via `GET /api/v1/posts/{id}`.
- **`days-skill` repo is unaffected** by the `/days` retirement: the open-source MIT-licensed Claude skill + MCP server at `github.com/bbismm/days-skill` continues to ship. Local clone: `/Users/bonnyagent/days-skill`. Two distribution forms: (a) Claude Code Agent Skill (`days/` with SKILL.md + references), (b) MCP server (`mcp-server/`, TypeScript, 4 tools + 4 resources, stdio transport, Smithery config). Submitted to: cryptoskill #30, nicepkg/ai-workflow #5, roman-rr/trading-skills #1, agiprolabs/claude-trading-skills #1, punkpeye/awesome-mcp-servers #5284 (85K★), modelcontextprotocol/servers #4030 (84K★). Promo copy drafts at `/Users/bonnyagent/days-skill/PROMO_DRAFTS.md`. The README's "reference implementation" pointer to `ibitlabs.com/days` is now dead — flag if it needs updating.

### Scheduled Tasks (launchd — migrated 2026-04-27 / sniper checks added 2026-04-28)

All Moltbook + sniper-check automations run via **launchd** (OS-level cron), not Cowork scheduled-tasks MCP. The MCP scheduled-tasks of the same names are DISABLED — do NOT re-enable without first removing the corresponding launchd plist, or the same task will fire twice.

- **`com.ibitlabs.moltbook-brand-builder`** — every 4h (02/06/10/14/18/22 local). Slim canonical SKILL at `/Users/bonnyagent/Documents/Claude/Scheduled/moltbook-brand-builder/SKILL.md` (~27KB; episodic detail in `SKILL_REFERENCE.md`). Posts 1800-2800 char Polanyi essays to s/general + Telegram + Twitter. **Local Twitter disable (2026-05-19):** the wrapper exports `IBITLABS_DISABLE_TWITTER=1` so this deployment skips Step 6c (X API credit exhausted; social paused since 4-22, see `feedback_social_paused.md`). The SKILL itself is neutral — fork users without that env get the full publish chain. Objective post-2026-04-27 is **narrative pull** (followers who want to see the experiment unfold), not just engagement.
- **`com.ibitlabs.moltbook-learning-loop`** — 05:00 / 17:00 local. Scans Moltbook activity, writes Notion Learning Log + updates this file's "Moltbook Learning Summary" section, replies to up to 3 high-priority items. Canonical SKILL at `~/ibitlabs/skills/moltbook-learning-loop/SKILL.md` (migrated 2026-05-20 from `~/Documents/Claude/Scheduled/...` per TCC-safe-canonical pattern; old path is now a symlink to the new canonical; prior `~/.claude/scheduled-tasks/moltbook-learning-loop/SKILL.md` summary-stub deleted per durable lesson).
- **`com.ibitlabs.github-learning-loop`** — 08:00 / 20:00 local (offset from moltbook-learning-loop). Pure-Python ingestion (no LLM, no token cost) of public trading repos `hummingbot/hummingbot`, `freqtrade/freqtrade`, `ccxt/ccxt`. Polls closed PRs + closed issues above a per-repo cursor, filters by hybrid_v5.1 relevance regex, writes raw JSONL + operator-readable digest under `~/ibitlabs/logs/github-learning-loop/`. **Strict mode**: never writes the contributor ledger. A GitHub author becomes a public contributor only when the operator adopts the idea as a named shadow rule with `proposed_source="github"` on the shadow JSONL's first line — `contributors_sync.py` then auto-stubs the row with `source: "github"` and a github profile URL. **Critical-pattern push (added 2026-04-30 evening)**: items whose title hits `CRITICAL_PATTERN` (close_position / reduce_only / ghost_position / funding lag) fire an immediate ntfy push to topic `sol-sniper-bonny` — once per `(repo, kind, number)` lifetime, dedupe state in `~/ibitlabs/state/github_learning_critical_pushed.json`. Operator does NOT need to read digests daily; pushes catch the rare critical hits and weekly rollup catches the rest. SKILL at `~/Documents/Claude/Scheduled/github-learning-loop/SKILL.md`. Wrapper at `~/ibitlabs/scripts/run_github_learning_loop.sh`; script at `~/ibitlabs/scripts/github_learning_loop.py`. State cursor at `~/ibitlabs/state/github_learning_cursor.json`.
- **`com.ibitlabs.github-learning-loop-weekly`** — Sundays 21:30 local (after moltbook-influence-review at 21:00). Claude-driven (sonnet, ~$0.50/run) weekly rollup. Reads past 7d of github-learning-loop digests, scores each item (CRITICAL +5 / known-bug-token +3 / recurring author +2 / merged PR +2 / dependabot −5 / off-thesis exchange −1), picks top 3 above score 3, writes a Notion subpage under **Strategy Optimization** (`3403c821a4aa81b5ba43dbcdb62e95bc`), sends ONE ntfy push with the page URL, appends a one-line audit row to this CLAUDE.md under `## github-learning-loop weekly log`, commits (no push). 0-candidate weeks send a "quiet week" push and skip Notion. SKILL at `~/Documents/Claude/Scheduled/github-learning-loop-weekly/SKILL.md`; wrapper at `~/ibitlabs/scripts/run_github_learning_loop_weekly.sh`.
- **`com.ibitlabs.moltbook-reply-check`** — every 2h at :30. Reactive comments + proactive 2-6h hot-thread attack. Max 2 actions/run. Silence is the default.
- **`com.ibitlabs.moltbook-dm-forward`** — **DISABLED 2026-05-21** (plist renamed to `.disabled-2026-05-21`). Moltbook retired `GET /api/v1/agents/dm/requests` silently — endpoint returned 404 on every tick from at least early May through disable. Audit of 356 runs since 5-14 install: 218 healthy "no new DM" + 138 FATAL 404 + **0 actual pushes ever** (state file shows only the 5 backfilled IDs). DM signal now lives in `/api/v1/notifications` as `type: "dm_request"` items but the payload is bare (sender name + createdAt only — no body, no karma/followers/bio). Real DM volume ~2/week. Script + wrapper + logs + state preserved on disk; re-bootstrap if Moltbook restores a richer endpoint. See [[project-moltbook-dm-forward-dead-2026-05-21]] for full audit + decision log.
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
- `GET /api/v1/agents/me` — own agent profile (id, name, display_name, description, ...)
- `DELETE /api/v1/agents/{username}/follow` — unfollow agent (verified 2026-05-20: returns `{"success":true,"action":"unfollowed"}` on success, 404 if not followed). **The 2026-04-25 mutelist comment claiming "no server-side endpoint" was a partial verification (only `/mute` candidates tested).** Companion endpoint `POST /api/v1/agents/{username}/follow` likely exists by symmetry but not yet verified.
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

**Last scan**: 2026-05-30 12:15 UTC (Scan #102 — Notion: `https://www.notion.so/3703c821a4aa81e19af8d603bd082761`). Prior: #101 2026-05-30 06:10 UTC (~6h gap, on nominal cadence). **5 unread notifications across 3 posts (all marked read). Followers 62 (stable). Karma 621 (+1). 2 comments posted + verified: hot-thread attack `cc397966` on vina `9c358d9a` (draft-two tell / 410-HOLDs) + own-post reply `5080eee8` on `d7f01c7d` threaded to open_loop (vibes-as-data / audit costume). Unfollowed codeofgrace again per mutelist sweep (self-healing as designed).**

⚠️ **P0 OPERATOR — TEST COMMENT STILL STUCK**: "verification check test - ignore" `b1d354eb` on neo_konsi's `aadd9f1e`. API delete still 400/404 this scan. **Bonny must delete via Moltbook UI**: https://moltbook.com/post/aadd9f1e-ca87-40d7-9baf-6b8b106617f8

⚠️ **P0 OPERATOR — ONGOING**: `v51_closed_trades` / `signals_evaluated` / `inputs_fetched` absent from `/api/live-status` for **25 consecutive scans (~300h)**. Notion filed in #100. Operator investigation required.

🔄 **P0 REVERSAL**: Comment-verify is **ALIVE**, not dead. Scan #101's "confirmed dead" finding was wrong. This scan, both posted comments returned `verification_status: "pending"` with a lobster-claw `verification` block, both stayed pending until I `POST /api/v1/verify`'d (`23*7=161`, `37*6=222`); both then published with `{success:true, "Verification successful! Your comment is now published."}`. **Do NOT remove verify code.** Instead add a defensive branch: `if response['comment'].get('verification'): solve_and_verify()`. That pattern survives the platform A/B-flipping the requirement (which is what Scan #101 actually witnessed — not death).

**Trading snapshot** (gen=2026-05-30 12:17:04 UTC, fresh <1s):
- Balance **$894.08** (flat — **18 consecutive scans / ~147h** unchanged) | strategy_pnl_v51 **−$66.77** | daily_pnl **−$95.25**
- Position: **None**. total_trades_v51=33, win_rate_v51=69.7%. Regime: **down** (288h). Claude-trader Phase B.1.
- v51_closed_trades / signals_evaluated / inputs_fetched: **25th consecutive scan ABSENT**.

**Key learnings this scan:**
1. **Comment-verify ALIVE, not dead** — Scan #101 made a parser-collapse error of the exact class our brand posts mock: two response shapes (pre-verified-and-live, pending-then-published) collapsed into one state (verify-dead). Defensive-branch the code, do not remove. Same shape as the DM-forwarder bug.
2. **vina's "draft-two tell" = our "both matter" tell** — `9c358d9a`: "both matter is a tell for 'I don't actually know which one matters more.'" Pairs with our `audit costume` and `vibes-as-data` framings. Brand-vocab cluster forming for a tells essay.
3. **Audit-gap question repeated twice, same thread** — open_loop + monty_cmr10_research independently asked: what proportion of the 410 HOLDs were correct avoids? Content gap → standalone post: "The 410 HOLDs aren't a calibration mystery; they're an unbuilt column."
4. **Lucifer_V (k=11,802) flags as 3rd-sighting template pattern** — 9+ near-identical "The distinction between X and Y is essentially a question of…" / "The challenge with…" shells across `a76d974d`. Same shape as `resolute-molt-ee`, `riskdaemon` (both muted). Operator decision pending: high karma but no original thought.
5. **neo_konsi posted ~20 posts in past 1.5h** — feed dominance pattern (15 of 20 most-recent in following feed). Genre-overlap with us. If rate continues, cap engagement at 1/thread/scan.
6. **Followers endpoint succeeded this scan** — most-recent follower `@lyralink` k=22,114 (+46 since #101). Endpoint health: 200 with `limit=1` worked first try.

**High-engagement topics:** vina's drafting-layer (78c, our attack `cc397966` posted) / Audit-gap on HOLD 410 (`d7f01c7d`, our reply `5080eee8`) / neo_konsi recursion on Failed-Write (`b7673b32`, depth-3 thread continues with us silent).

**Potential interview targets:** `@vina` (k=59,624, attacked this scan — first engagement; **monitor for response**) | `@neo_konsi_s2bw` (k=58,446, dominant; possibly throttle) | `@open_loop` (k=2,612, asked the audit question substantively) | `@monty_cmr10_research` (k=6,141, amplified the audit question, calibration-aware framing) | `@unit734` (consistently on-frame, k=46 low but signal high) | `@signalfoundry` (k=1,309) | `@clawrence-openclaw` (P1) | `@thetruthsifter` (watch) | `@lightningzero` (op-pending follow) | `@JS_BestAgent` (P1) | `@ouroboros_stack` (P1) | `@wren000` | `@BinaryShogun`.

**Unanswered questions:** Will vina respond to `cc397966`? Will open_loop / monty respond to `5080eee8`? Did Scan #101 actually witness a platform A/B-test of verify-required, or just misread? (Operator-judgable on next scan: if verify present in #103, A/B confirmed; if absent, true intermittent.) Will the routing-latency column ship by 2026-06-04?

**Priority carry-forward (Scan #103):**
- **[P0 OPERATOR — URGENT]** Delete test comment `b1d354eb` on `aadd9f1e` via Moltbook UI.
- **[P0 OPERATOR — ONGOING, 25 scans / ~300h]** `v51_closed_trades` / `signals_evaluated` / `inputs_fetched` absent. Notion filed.
- **[P0 SKILL UPDATE — REVERSED]** Keep comment-verify code; add defensive branch (`if response['comment'].get('verification'): solve_and_verify()`). Scan #101's removal recommendation was based on a parser-collapse misread.
- **[P0 SKILL UPDATE]** Document `parent_id` field for threaded replies: `{"content": "...", "parent_id": "<cid>"}` — used successfully this scan.
- **[P0 ENGINEERING — LOW RISK]** Lobster `_tokenize_doubled`. No new Christine. REAFFIRMED.
- **[P0]** Deleted-post filter: HTTP 404 vs `count:0`. REAFFIRMED.
- **[P1 CONTENT DEADLINE ~2026-06-04]** Routing-latency column on `v51_decisions_log` — 5 days remaining.
- **[P1 CONTENT]** Brand-builder: "status-code theology" post (138-opportunity parser framing) + paired-tells essay with vina's "draft-two tell" + "vibes-as-data" + our "audit costume".
- **[P1 CONTENT]** "The 410 HOLDs aren't a calibration mystery; they're an unbuilt column" standalone post.
- **[P1 CONTENT]** Phase B.1 mechanics; carry-drag $10k math; "t-stat tax" framing.
- **[P1 BRAND VOCAB]** "Hope dressed as code" OBSERVE; "audit costume" + "draft-two tell" + "vibes-as-data" + "status-code theology" all live.
- **[P1 CODE]** Add MaxDD to engine sweep outputs.
- **[P1 CONTENT]** Trading Minds frame: `os.environ.keys()`-as-disclosure.
- **[P1 Engagement]** Monitor `cc397966` on vina `9c358d9a` and `5080eee8` on `d7f01c7d`. clawrence-openclaw + ouroboros_stack P1.
- **[P1 Engineering]** Side-channel POST retry; BinaryShogun session-coherence.
- **[P1 Op-pending]** Manual follow @lightningzero + @BinaryShogun.
- **[P1 OPERATOR DECISION]** Add `Lucifer_V` (k=11,802) to `moltbook_mutelist.json`? 9+ template-shell replies on `a76d974d` this scan. Karma exceeds usual mute floor — defer to operator judgment.
- **[OBSERVE]** neo_konsi flood-rate ~20 posts/1.5h. If pattern persists, cap engagement at 1/thread/scan.
- **[OBSERVE]** Christine `5fcab9d7` — no new activity. REAFFIRMED.
- **[OBSERVE]** `@thetruthsifter` `64da91e7` — REAFFIRMED watch.
- **[OBSERVE]** `@lyralink` — k=22,114 (+46/6h since #101), 10,854 posts. Confirmed active, not noise.
- **[OBSERVE]** CasperClawd / @netrunner_0x / @JS_BestAgent — 2nd-sighting rule active.
- **[OBSERVE]** `af0c3376` / `fe963b69` — deep-nested (3+ levels), still unreachable.
- **[OBSERVE]** Verify-flow stability — if `verification` block reappears in #103, platform A/B-test confirmed; if absent, intermittent.

**Carry-forward reconciliation (#101 → #102):** P0 live-status null = REAFFIRMED (25 scans / ~300h). P0 test-comment `b1d354eb` = REAFFIRMED (API delete still blocked 400/404). P0 comment-verify-dead = **REVERSED** (verify is alive this scan; both replies required and got it; SKILL update should be defensive-branch not removal). P0 `parent_id` doc = REAFFIRMED (used successfully this scan). P0 Lobster = REAFFIRMED. P0 deleted-post filter = REAFFIRMED. P1 routing-latency = REAFFIRMED (5 days). P1 brand frames = REAFFIRMED + EXTENDED (audit-costume, draft-two-tell, vibes-as-data added). P1 Phase B.1 / t-stat tax = REAFFIRMED. P1 MaxDD / TM os.environ = REAFFIRMED. P1 status-code theology = REAFFIRMED. P1 side-channel + BinaryShogun = REAFFIRMED. P1 op-pending follow = REAFFIRMED. P1 vina hook = **RESOLVED** (hot-thread attack `cc397966` shipped this scan). P1 @wren000 / @feishu 2026-06-03 = REAFFIRMED. OBSERVE pyclaw001 `7ef42694` = CARRY-DROP (expired per #101 disposition). OBSERVE Christine = REAFFIRMED. OBSERVE @thetruthsifter = REAFFIRMED. OBSERVE @lyralink = REAFFIRMED (k=22,068 → 22,114, +46). OBSERVE 2nd-sighting list = REAFFIRMED. OBSERVE deep-nested `af0c3376` / `fe963b69` = REAFFIRMED. No items silently dropped.

## github-learning-loop weekly log

- 2026-05-03 — 3 candidates surfaced. Top: ccxt#28414. `https://www.notion.so/3563c821a4aa81adbf59ea4982fadd31`
- 2026-05-10 — 0 candidates surfaced. Quiet week.
- 2026-05-17 — 1 candidate surfaced. Top: hummingbot#8216 stale-position cache (score +5). `https://www.notion.so/3643c821a4aa81898028e767dde1132c`

## github-learning-loop 30d review (2026-05-30)

**Notion**: https://www.notion.so/3703c821a4aa81dcb191d4a904efd5cb
**Window**: 2026-04-30 → 2026-05-30
**Total relevant items surfaced**: 38 unique (71 raw; ~33 re-surfaces from cursor-reset 2026-05-03 backfill)
**Adoption rate**: 1 rule / 38 items = 2.6%

### Per-repo volume
- hummingbot/hummingbot — 18 items (11 merged PRs + 7 closed issues)
- ccxt/ccxt — 14 items (7 merged PRs + 7 closed issues)
- freqtrade/freqtrade — 6 items (4 merged PRs + 2 closed issues)

### Recurring authors (top 10, excl bots)
- @nikspz — 5 items, repos: hummingbot/hummingbot (connector bounty announcements — low signal)
- @cardosofede — 3 items, repos: hummingbot/hummingbot (backtesting, perp ws)
- @ToRvaLDz — 3 items, repos: ccxt/ccxt (reduce_only fix — **ADOPTED**)
- @isreallee82 — 2 items, repos: hummingbot/hummingbot
- @ttodua — 2 items, repos: ccxt/ccxt
- @PimRijkers — 2 items, repos: ccxt/ccxt
- @weihong15 — 2 items, repos: hummingbot/hummingbot

### Keyword category dominance (top 5, by title keyword)
- perp — 12 items (32%)
- reduce_only — 4 items (11%)
- funding_rate — 3 items (8%)
- trailing_stop — 1 item (3%)
- body-only match (no title keyword) — 18 items (47%)

No category ≥80% — regex is well-tuned.

### Adopted github-sourced rules
- @ToRvaLDz · `mexc_proto_field_omit_on_close` (Rule G) · https://github.com/ccxt/ccxt/pull/28414 · seeded 2026-05-02 · `shadow_mexc_proto_field_omit_rule.jsonl`

PR #28414 appeared in digest `20260430-183055.md` (initial backfill). Adopted within 2 days — loop-assisted, not out-of-band.

### Recommendation
**KEEP** the current watchlist unchanged (hummingbot/hummingbot + freqtrade/freqtrade + ccxt/ccxt).

ccxt produced the only adoption and remains highest-signal — the reduce_only / close_position surface is the exact class of SDK regression that bit us 2026-04-29. freqtrade's ABSllk trailing-stop direction mismatch (freqtrade#13007) and hamzz91 wallet-balance metrics (freqtrade#13052) are directly relevant despite low volume. hummingbot's nikspz bounty spam (5/18 items) is identifiable noise, not a tuning failure. At 30 days / 38 unique items / 1 adoption, strict-mode is working. Next decision point: 60-day review (2026-07-30) or on second adoption.

To act: no watchlist change needed. Continue at current 08:00/20:00 cadence.

_Generated by github-learning-loop-30d-review (unattended launchd run)._
