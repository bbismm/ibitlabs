---
name: ibitlabs-mcp
description: Build/maintain the iBitLabs MCP server that exposes the $1k → $10k experiment as callable tools (live balance, contributor ledger, saga). Five tools: 3 wired to live public endpoints, 2 stubbed pending Cloudflare Pages functions.
---

# iBitLabs MCP Server — build & extend

This SKILL is for Claude Code sessions that touch `~/ibitlabs/mcp-server/`. Use it when adding tools, wiring new public endpoints, or debugging the deployed server.

## Tools (MVP, v0.1.0)

### Live (wired)

1. **`get_live_status`** → `https://www.ibitlabs.com/api/live-status`
   - Strips noisy fields (`snapshot_seq`, `source_watermark`, etc.) before returning.
   - Surfaces: balance, PnL (total / unrealized / daily), win rate, open position, regime, reconciliation timestamp.

2. **`list_adopted_rules`** → `https://www.ibitlabs.com/data/contributors.json`
   - Filterable by `status` (`adopted` | `queued` | `all`).
   - Returns the full schema (incl. proposer handle, source post URL, rule_id, shadow window).

3. **`get_latest_saga_chapter`** → `https://www.ibitlabs.com/data/saga_vol2.json`
   - Filterable by `lang` (`en` | `zh`).
   - Returns latest entry + full URL. Best-effort parse with a clean error envelope if `saga_vol2.json` index is malformed (current production file has unescaped quotes in `preview` strings — sanitize upstream when convenient).

### Pending (stubs)

4. **`get_recent_trades`** — needs `/api/recent-trades?limit=N`
5. **`get_rule_status`** — needs `/api/rule-status/:rule_id`

Both return `status: "pending"` with a `planned_schema` payload so callers know what they will get when the endpoint ships. Don't replace the stubs with mock data — the honest stub is better than a fake response.

## When you ship the pending Pages functions

For each, add the Cloudflare Pages function under `~/ibitlabs/web/functions/api/`, then in `src/server.ts` replace the stub handler body with a `fetchJson` call. Keep the input schema identical so existing callers don't break.

- **`/api/recent-trades`**: read from `sol_sniper.db` (or a published `trade_log.jsonl`). Match the `planned_schema` in the stub: trade_id, entry/exit ts + price, direction, pnl, hold_minutes, exit_reason, regime, atr_regime.
- **`/api/rule-status/:rule_id`**: aggregate the rule's shadow JSONL (`logs/shadow_<rule_name>.jsonl`). Compute n + hit_rate per bucket. Compare against the 4 promotion conditions in `project_rule_f_promotion_criteria.md`. Cheaper alternative: a nightly cron writes `/data/rule_status.json` and the Pages function just serves the static file.

## Adding a new tool

1. Append to `TOOLS` (description must be specific enough that an LLM picks it correctly — describe the use-case, not just the data).
2. Add a typed handler. Use `fetchJson<T>` for JSON endpoints; for HTML, fetch as text.
3. Add a `case` in the switch in `setRequestHandler(CallToolRequestSchema, ...)`.
4. Update the table in `README.md`.
5. `npm run build` — keep the bundle deterministic.

## What NOT to add

- ❌ Any `execute_trade` / `place_order` / write tool that touches the real account. Read-only until $10k milestone, no exceptions.
- ❌ Raw JSONL dump endpoints. Stay at the aggregate level — exposing internal schemas invites reverse-engineering for no upside.
- ❌ Strategy-code-generation tools. That's [lona.agency](https://lona.agency)'s lane; we differentiate on real receipts, not on generating new strategies for callers.
- ❌ Telegram / Twitter / social posting hooks. Social automation is paused (see `feedback_social_paused.md`).

## Distribution

- Stdio mode works today (above).
- Smithery listing: `smithery.yaml` is ready; submit at `https://smithery.ai/`.
- Remote HTTP transport: add a thin Worker that wraps the same handlers behind `https://mcp.ibitlabs.com/mcp`. Phase 2 — get stdio + Smithery in front of users first, see who calls what.

## Versioning

Bump `package.json` minor on every new tool. Patch on bug fixes. Major reserved for breaking schema changes (which should be rare — tool inputs/outputs are part of the public contract once a caller exists).
