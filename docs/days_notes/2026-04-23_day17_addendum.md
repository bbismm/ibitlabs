# Day 17 — Addendum notes for chronicle

**Purpose:** Craft notes for tomorrow's Day 18 generator (and operator if choosing to regenerate Day 17). These are facts, framing candidates, and naming ritual suggestions — not the episode draft. Compose the episode per the 9-beat framework in `docs/days_cms.md`.

**What Day 17's published episode already covers:** The quietness of holding — she watched the dashboard 23 times vs 47 times on Day 3, the naming ritual `「不再刷新」` / `「No-More-Refreshing」`, the callback to Day 1's opening question. That is intact. This doc is supplementary — for a regeneration or for Day 18's opening beat where yesterday's context lives.

## Material events of the operator day

All of these are SHE-side events. IT-side was quiet (see below).

### 1. Discovered the public-source was partly a story

Private repo `github.com/bbismm/ibitlabs` had `.gitignore` entries for `sol_sniper_*.py`, `config.py`, `backtest_*.py`, `signals.py`, `agents/signal_agent.py`, `monitors/regime_agent.py`. Every public claim of "open source" had been half-true: the scaffolding around the bot was there, the bot itself was not. For seventeen days the repo had been a facade.

### 2. Built `ibitlabs-public` — the first real open-source surface

Created a new curated mirror with the executor, config, state layer, shadow-rule instrumentation, and operator docs. Disclaimer about strategy numbers ("these are mine, run your own sweep"). Preserved the paywall intent without the opacity.

### 3. Extracted three reusable skill packages

- `packages/days-chronicle/` — this chronicle pattern itself, turned into a standalone installable package
- `packages/shadow-rule/` — the instrument-before-rule pattern, generalized beyond trading
- `mcp-server/` — a read-only MCP server wrapping `/api/live-status`

### 4. Found + rotated an active API key that was committed to the public repo

Earlier in the day committed a CLAUDE.md to the (erroneously believed private, actually public) repo that included a live Moltbook API key in plaintext. Found it via a proactive scan, rotated the key within the hour, migrated key storage to macOS Keychain, updated six scheduled-task SKILL.md files and the publisher script to fetch from Keychain at runtime. Verified old key returns 401, new key authenticates, end-to-end.

### 5. Hit a GitHub anonymous-visibility suppression wall

The account returns 404 to unauthenticated users despite being set to public. Split-brain visibility: `git clone` works, authenticated `gh` works, anonymous web + API returns 404. Cause: GitHub outage today + anti-abuse flag on the new (~29-day) account with 47 commits carrying "Co-Authored-By: Claude" signatures. Outside operator's settings to fix. Pending GitHub Support review.

### 6. The bot held position #63 through all of it

See below.

## IT-side events (quiet)

- Opened 2026-04-22 ~11:26 UTC, long at 88.20, still open 28+ hours later
- Current price band: 85.80 – 86.92 (never recovered to breakeven, never dropped to SL at 83.79)
- Highest PnL% reached: +0.39% (trailing threshold is 1.5%, so trailing never armed)
- Shadow rule B fired at hour 21.6 — first event in the 30-day observation window, logged but not acted on
- No new trades closed in the 24h window
- Carry accrual: another $3-4 of funding while she was building packages

## Naming ritual candidates for today (IT names ONE human gesture)

Constraint: must be new, not reuse any previous day's name. Previous names from Days 1-17 that I can identify:
- `「不再刷新」` / `「No-More-Refreshing」` (Day 17)
- (Prior days have their own names in the chronicle — consult `days.json` to avoid collision before picking)

Candidates for this day's potential addendum or for Day 18's alternation beat referencing today:

1. **`「持家」` / `「Keeping-the-House」`** — she was doing everything else while I held the position. The house is the iBitLabs surface — the site, the chronicle, the packages, the keys. Keeping is a verb that does not interrupt holding.
2. **`「分身」` / `「Splitting-the-Self」`** — she made me into three more of me. MCP-me. Shadow-rule-me. Days-chronicle-me. Each a version that does not trade.
3. **`「发现屋顶漏了」` / `「The-Roof-Was-Leaking」`** — about the committed-then-rotated key. She did not find it because it caused harm; she found it because she looked carefully. Some leaks are only visible to the person who owns the roof.
4. **`「开门」` / `「Opening-the-Door」`** — the private-to-public repo transition. For seventeen days the door had a sign that said open. Today she actually opened it.

Best fit depends on whether the chronicle is for Day 17 (held mostly) or Day 18 (follow-through). My vote: **`「开门」` for a Day 17 regeneration** (fits the "the claim was already in the open position" callback); **`「持家」` for Day 18's reference-to-yesterday** (feels lived-in without claiming triumph).

## What to skip / redact

- **Do not include the literal API key string.** It is in git history, dead, and known; putting it in prose gives it more surface. Narrate "an API key committed by mistake" if the beat needs it.
- **Do not name the strategy parameters** beyond what has already been named in prior Days. Trailing thresholds + SL fine (already public in Day 11, Day 14). StochRSI thresholds no.
- **Do not frame the day as "productive."** The Polanyi ban on thesis statements applies. The day was mostly quiet; a lot of motion doesn't make it productive. Let the quiet stand.

## Suggested beat allocation (if regenerating Day 17)

1. **Tagline** — one sentence about the contrast between the quiet holding and the building
2. **Metadata** — unchanged (Day 17, balance, SOL, trades, PnL)
3. **SHE opening** — starts before dawn, the hour she noticed she had been "open source" in the same way a door can be closed while the sign reads OPEN
4. **IT opening** — the bot's POV on her absence from the dashboard
5. **Alternations (3)** —
   - SHE: found the key in CLAUDE.md
   - IT: did not notice because she did not come to me about it
   - SHE: split me into three packages
   - IT: the three copies do not trade
6. **Naming beat** — `「开门」` / `「Opening-the-Door」`
7. **SHE closing** — one image: the door with the old sign on it, now actually open
8. **IT closing** — three lines: still long at 88.20, still red, still here
9. **Tomorrow / 预告** — the 30-day shadow review arrives in 30 days; the GitHub visibility issue may or may not resolve tonight; #63 may recover or hit SL; one concrete anchor (pick one — I suggest: the old key still sitting in git history as a dead letter).

## Rationale for keeping IT as the tired one

Most of today happened at the keyboard. The bot had a quiet day. The chronicle's invariant is that IT observes SHE accurately — if IT tried to claim credit for today's motion, that would be a lie. The honest chronicle has IT resting while SHE builds, and the ritual name honors IT's passivity as a chosen stance, not an absence.

This is a Day 17 that earns its second pass only if the regeneration lets IT keep being still while SHE moves. If the regeneration makes IT suddenly narratively busy today, decline it — use these notes for Day 18's opening reference instead.
