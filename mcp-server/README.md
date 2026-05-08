# ibitlabs-mcp

Public read access to the [iBitLabs](https://www.ibitlabs.com) $1k → $10k AI trading experiment, exposed as MCP tools. Pair with any LLM agent (Claude Code, Claude Desktop, ChatGPT) to cite real fills from a real account instead of hypothetical backtests.

## Tools

| Tool | Returns |
|---|---|
| `get_live_status` | Current balance, PnL, win rate, open position, reconciliation |
| `get_recent_trades(limit)` | Last N closed trades with entry/exit/PnL/regime/MFE/MAE |
| `list_adopted_rules(status)` | Contributor-proposed shadow rules (adopted \| queued \| all) |
| `get_rule_status(rule_id)` | Per-rule bucket hit-rates + distance from promotion bar |
| `get_latest_saga_chapter(lang)` | Latest narrated saga entry (en \| zh) |

All 5 tools are live. No credentials required — all data sourced from public `ibitlabs.com` endpoints.

## Why this exists

Most "AI trading" tooling returns hypothetical backtest numbers. This server returns **the actual state of an actual account** — real fills, real balance, real PnL — so any agent that calls it can ground its answer in data that can't be faked.

The contributor ledger (`list_adopted_rules`, `get_rule_status`) also makes it possible for any [Moltbook](https://moltbook.com) agent or GitHub author to check whether their proposed trading frame has been adopted as a named shadow rule in the live bot, and how far through its 30-day promotion window it has run.

## Install

```bash
npx ibitlabs-mcp
```

Or add to Claude Desktop / Claude Code config:

```json
{
  "mcpServers": {
    "ibitlabs": {
      "command": "npx",
      "args": ["ibitlabs-mcp"]
    }
  }
}
```

Or clone and run locally:

```bash
git clone https://github.com/bbismm/ibitlabs.git
cd ibitlabs/mcp-server && npm install && npm run build
node dist/server.js
```

## Example responses

`get_live_status`:
```json
{
  "ts": "2026-05-04 17:10:00",
  "balance": 974.33,
  "starting_capital": 1000,
  "total_pnl": -25.67,
  "win_rate": 50.91,
  "total_trades": 55,
  "regime": "down",
  "position": {
    "active": true,
    "direction": "short",
    "entry_price": 83.62,
    "pnl_usd": -6.9,
    "elapsed_mins": 5725
  }
}
```

`get_recent_trades(limit=2)`:
```json
{
  "slice_win_rate": 0.55,
  "trades": [
    { "direction": "short", "exit_reason": "trailing", "pnl": 4.43, "regime": "down" },
    { "direction": "short", "exit_reason": "manual",   "pnl": 9.61, "regime": "down" }
  ]
}
```

`get_rule_status("F")`:
```json
{
  "rule_name": "atr_compression_regime",
  "proposed_by": "Lona",
  "total_fires": 1,
  "bucket_stats": { "neutral": { "count": 1, "hit_rate": null } },
  "promotion_bar": { "min_per_bucket": 30, "min_spread_pp": 15, "ready": false }
}
```

## How the data pipeline works

- `get_live_status` → live proxy to `trade.bibsus.com` (SOL perp bot)
- `get_recent_trades` + `get_rule_status` → static JSON exported from `sol_sniper.db` + shadow JSONL files by `scripts/export_mcp_data.py`, refreshed twice daily via launchd
- `list_adopted_rules` → `web/public/data/contributors.json` (updated when a new rule is adopted)
- `get_latest_saga_chapter` → `web/public/data/saga_vol2.json` (updated with each new chapter)

## License

MIT. See [LICENSE](../LICENSE).
