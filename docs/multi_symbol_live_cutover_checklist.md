# Multi-symbol live cut-over checklist (ETH paper → live)

Target window: **2026-05-20 14:49 UTC** (Phase 3 review). Companion doc:
`docs/multi_symbol_eth_expansion_DD.md`. Producer + frontend wiring landed
2026-05-13 (`multi_symbol_status.py`, `scripts/write_launch_anchor.py`,
`signals.html` Multi-Symbol card).

## Decision gate (T-1h, 2026-05-20 13:49 UTC)

Run before doing anything irreversible. Re-bar from 2026-05-13 supersedes the
original `≥10 trades` bar (see saga of that day's session):

| Check | Command / source | Pass when |
|---|---|---|
| ETH ≥1 LONG + ≥1 SHORT closed | `sqlite3 sol_sniper_eth_paper.db "SELECT side, COUNT(*) FROM trade_log WHERE exit_price IS NOT NULL GROUP BY side"` | Both sides appear |
| ETH ≥2 regime tags closed | `sqlite3 sol_sniper_eth_paper.db "SELECT regime, COUNT(*) FROM trade_log WHERE exit_price IS NOT NULL GROUP BY regime"` | ≥2 rows |
| Zero PnL/notional asymmetry bugs | round-trip fee ≈ 0.16% of notional (Coinbase taker × 2) | True |
| ≥14 clean run-days since 2026-05-06 14:49 UTC | `launchctl print gui/$(id -u)/com.ibitlabs.sniper-eth \| grep "last exit"` | "never exited" |
| risk_officer 2c wired | `grep risk_officer ~/ibitlabs/sol_sniper_executor.py` | Returns hits |
| 2d module loads on dashboard | `curl -s http://127.0.0.1:8086/api/live-status \| python3 -c "import sys,json;print(json.load(sys.stdin)['multi_symbol'])"` | `{"launched": false}` |

If any row fails → extend paper window, do NOT proceed.

## Pre-flight (T-30min, 2026-05-20 14:19 UTC)

```bash
# 1. SOL bot health
curl -s http://127.0.0.1:8086/api/live-status | \
  python3 -c "import sys,json;d=json.load(sys.stdin);print('alive=',d['alive'],'mode=',d['mode'],'balance=',d['balance'],'reconcile_clean=',d['reconciliation']['clean'])"

# 2. ETH paper bot still running clean (we want to compare its last balance)
launchctl print gui/$(id -u)/com.ibitlabs.sniper-eth | grep -E "state|pid|last exit"

# 3. Coinbase ETH-perp credential present
# (SOL key already authorized for SLP/ETP/etc — confirm by reading the actual
# env var the live plist will see, NOT just the .env file)
grep -A1 "CB_API_KEY" ~/Library/LaunchAgents/com.ibitlabs.sniper.plist | head

# 4. No open ETH position right now (clean state preferred)
python3 -c "import json;d=json.load(open('sol_sniper_state_eth_paper.json'));print('paper position:', d.get('position'))"
# If non-null: wait for paper to close before cut-over. If urgent, cut over
# anyway — paper position is in paper DB only, won't carry to live.

# 5. Ghost-watchdog scope review — does it monitor sniper-eth too?
grep -E "sniper-eth|com.ibitlabs.sniper-eth" ~/ibitlabs/ghost_watchdog.py
# If MISS: ghost-watchdog still only watches SOL. Acceptable for day-1
# (margin gap on ETH is small with $1k seed) but file follow-up issue.
```

## Cut-over (T-0, 2026-05-20 14:49 UTC)

**Strict order — do NOT reorder.** The anchor must capture SOL's balance
*before* ETH starts trading live, and the ETH live plist must be the source
of the ETH state file the anchor points at.

```bash
# Step 1. Bootout ETH paper bot
launchctl bootout gui/$(id -u)/com.ibitlabs.sniper-eth
# Verify gone:
ps aux | grep sol_sniper_main | grep eth_paper | grep -v grep || echo "OK paper stopped"

# Step 2. Archive paper DB + state (forensic preservation, not used post-launch)
cp ~/ibitlabs/sol_sniper_eth_paper.db \
   ~/ibitlabs/sol_sniper_eth_paper.db.archived-pre-live-$(date -u +%Y%m%d-%H%M%S)
cp ~/ibitlabs/sol_sniper_state_eth_paper.json \
   ~/ibitlabs/sol_sniper_state_eth_paper.json.archived-pre-live-$(date -u +%Y%m%d-%H%M%S)

# Step 3. Edit ~/Library/LaunchAgents/com.ibitlabs.sniper-eth.plist:
#   - Remove --paper
#   - Add --live (or whatever the executor calls it — match com.ibitlabs.sniper)
#   - Change --instance-name eth_paper  → eth_live
#   - Change --db   sol_sniper_eth_paper.db   → sol_sniper_eth.db
#   - Change --state-file sol_sniper_state_eth_paper.json → sol_sniper_state_eth.json
#   - Change --grid-state-file grid_state_eth_paper.json  → grid_state_eth.json
#   - Change --log-file sniper_eth_paper.log → sniper_eth.log
#   - In <EnvironmentVariables>, ADD:
#       CB_API_KEY = <copy from com.ibitlabs.sniper.plist>
#       CB_API_SECRET = <copy from com.ibitlabs.sniper.plist>
#     (Public ETH-PERP shares the same authorized portfolio as SOL-PERP)
#   - Keep SNIPER_PAPER_NOTIFY=0 (we still want quiet pushes from a brand-new
#     bot until it has 10 trades on the record)
# Save.

# Step 4. Bootstrap ETH live bot with sub-account starting capital
# (paper used $1000 default; live uses whatever Bonny has allocated — must
# match --starting-capital if executor expects an arg; otherwise this is
# implicit from the exchange sub-account balance)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ibitlabs.sniper-eth.plist
sleep 5
launchctl print gui/$(id -u)/com.ibitlabs.sniper-eth | grep -E "state|pid"
# Expect: state=running, pid=<new>

# Step 5. Wait ~30s for ETH bot to write its first state file
sleep 30
ls -la ~/ibitlabs/sol_sniper_state_eth.json ~/ibitlabs/sol_sniper_eth.db
# Both files must exist before next step. If either is missing → tail the
# log: `tail -50 ~/ibitlabs/logs/sniper_eth.log`. Fix and re-bootstrap.

# Step 6. WRITE THE ANCHOR. One-shot. This is the irreversible step.
python3 ~/ibitlabs/scripts/write_launch_anchor.py \
    --eth-mode live \
    --eth-state ~/ibitlabs/sol_sniper_state_eth.json \
    --eth-db ~/ibitlabs/sol_sniper_eth.db \
    --eth-starting-capital 1000.0
# Expect: "OK Anchor written: ..." with SOL/ETH/Combined balances.
# If it errors: read the message. Common causes:
#   - SOL endpoint unreachable → bot died; investigate before retry
#   - ETH state/db missing → step 5 didn't complete; wait + retry
#   - Anchor already exists → only happens if a previous run wrote one.
#     Use --force only if you're certain a misfire happened in last few min.

# Step 7. Kick the dashboard so it picks up the new anchor on next build
launchctl kickstart -k gui/$(id -u)/com.ibitlabs.dashboard
sleep 5
curl -s http://127.0.0.1:8086/api/live-status | \
  python3 -c "import sys,json;ms=json.load(sys.stdin)['multi_symbol'];print(json.dumps(ms, indent=2))"
# Expect: launched=true, eth_mode='live', combined_balance ≈ SOL + $1000.

# Step 8. Public verification
curl -s https://www.ibitlabs.com/api/live-status | \
  python3 -c "import sys,json;ms=json.load(sys.stdin)['multi_symbol'];print('launched=',ms.get('launched'),'eth_mode=',ms.get('eth_mode'))"
# May lag 30-60s behind localhost while CF cache turns over.
# Then load https://www.ibitlabs.com/signals in a browser — Multi-Symbol
# card should appear in the left column. Badge=LIVE, Combined>$1900.

# Step 9. Commit the anchor (it's a public commitment record)
cd ~/ibitlabs
git add state/multi_symbol_launch_anchor.json
git status   # ONLY the anchor should be staged
git commit -m "Multi-symbol live: ETH-PERP joins SOL-PERP at $(date -u +%Y-%m-%d)"
git push
```

## Post-flight (T+30min)

```bash
# A. ETH bot is scanning + healthy
tail -30 ~/ibitlabs/logs/sniper_eth.log | grep -E "scan|signal|skip|HOLD|OPEN"
# Expect: scan messages, no Tracebacks, no auth errors.

# B. Combined PnL surface is live
curl -s http://127.0.0.1:8086/api/live-status | \
  python3 -c "import sys,json;ms=json.load(sys.stdin)['multi_symbol'];print('eth_alive=',ms['eth_alive'],'combined=',ms['combined_balance'])"

# C. SOL bot is unperturbed
curl -s http://127.0.0.1:8086/api/live-status | \
  python3 -c "import sys,json;d=json.load(sys.stdin);print('SOL balance=',d['balance'],'snapshot_seq=',d['snapshot_seq'],'reconcile=',d['reconciliation']['clean'])"
# snapshot_seq should be incrementing every ~3s — proves dashboard is rebuilding.

# D. Risk officer sees the new symbol
grep -i "ETH\|ETP" ~/ibitlabs/logs/sniper.log | tail -10
# If risk_officer logs portfolio exposure: should now reflect both legs.

# E. ghost-watchdog still firing (didn't get confused by 2 bots)
launchctl print gui/$(id -u)/com.ibitlabs.ghost-watchdog | grep -E "state|last exit"
```

## Post-flight (T+24h)

- ETH ≥1 trade closed live (or scan loop steady through ≥1 signal candidate)
- SOL's reconciliation still clean (multi-symbol did not break it)
- /signals public page still rendering Multi-Symbol card on every load
- No 401/403 in `logs/sniper_eth.log` (CB key authorized for ETH-PERP)

## Rollback (if any of above fail)

```bash
# Stop ETH live (paper kept its archive, so this is reversible)
launchctl bootout gui/$(id -u)/com.ibitlabs.sniper-eth

# REMOVE the anchor — this is the only way to revert /signals to SOL-only
rm ~/ibitlabs/state/multi_symbol_launch_anchor.json
launchctl kickstart -k gui/$(id -u)/com.ibitlabs.dashboard

# Optionally restore ETH paper for forensics
# (the live DB stays for review — don't delete)
```

After rollback, file a written postmortem in Notion under Strategy
Optimization with the failure mode, what we tried, and what changed in
the rollback ladder before retry. Multi-symbol is the kind of expansion
that should not be retried impatiently.

## Open follow-ups (post-launch, not blockers)

1. **Ghost-watchdog scope**: extend to monitor sniper-eth alongside sniper.
   Currently only watches SOL. Acceptable day-1 (small ETH seed) but file
   issue same day.
2. **Risk-OFF brake**: confirm 7d DD calculation is now portfolio-level
   (was already portfolio in 2c, but verify across symbols with real data).
3. **/signals chart redesign**: today's Multi-Symbol card is text-only.
   DD #4 specifies a combined equity curve + per-symbol panels + vertical
   launch line. Defer to follow-up session — anchor data + JSON shape are
   ready to drive any chart implementation.
4. **Saga chapter**: 2026-05-20 multi-symbol launch is a dated milestone.
   Schedule the writeup for the next ai-creator-saga run.
5. **Contributors ledger**: no new credit attribution on cut-over day; if
   any shadow rule is adopted *because* of multi-symbol data, it earns a
   row on /contributors after the standard 30-day window.
