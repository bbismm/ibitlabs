# BIBSUS Alpha - Full Product Test Plan

## Test Environment

| Service | Port | Process | Status |
|---------|------|---------|--------|
| Owner Dashboard | 8080 | owner_harness.py | Check |
| Preview (Public) | 8081 | preview_harness.py | Check |
| Signals Marketplace | 8082 | signals_harness.py | Check |
| Autopilot | 8083 | autopilot_harness.py | Check |
| Crazy Dashboard | 8085 | crazy_dashboard_harness.py | Check |
| Sniper Dashboard | 8086 | sol_sniper_dashboard_harness.py | Check |
| Monitor (bg) | -- | monitor_harness.py | Check |
| Security (bg) | -- | security_harness.py | Check |
| Sniper Trading | -- | sol_sniper_main.py --paper | Check |
| Scalper Trading | -- | scalper.py | Check |

---

## Phase 1: Infrastructure Health (5 min)

### 1.1 Process Alive Check
- [ ] All 10 services running (`ps aux | grep python`)
- [ ] No zombie/duplicate processes
- [ ] Memory usage normal (scalper < 500MB, others < 100MB)

### 1.2 Port Connectivity
- [ ] curl localhost:8080 returns HTML (Owner)
- [ ] curl localhost:8081 returns HTML (Preview)
- [ ] curl localhost:8082 returns HTML (Signals)
- [ ] curl localhost:8083 returns HTML (Autopilot)
- [ ] curl localhost:8085 returns HTML (Crazy)
- [ ] curl localhost:8086 returns HTML (Sniper)

### 1.3 API Endpoints
- [ ] GET localhost:8080/api/status returns JSON
- [ ] GET localhost:8086/api/status returns JSON
- [ ] GET localhost:8085/api/status returns JSON

### 1.4 Database Integrity
- [ ] sol_sniper.db readable, tables exist (grid_orders, trade_log, cooldowns)
- [ ] scalper.db readable, not corrupted
- [ ] crazy_trader.db readable

### 1.5 External Connectivity
- [ ] Coinbase API reachable (SOL/USD ticker)
- [ ] ntfy.sh reachable

---

## Phase 2: Sniper Dashboard (8086) (10 min)

### 2.1 Layout & Display
- [ ] Page loads without JS errors (check console)
- [ ] BIBSUS ALPHA header with PAPER badge
- [ ] LIVE indicator dot pulsing green
- [ ] Timestamp updating every 3s

### 2.2 Balance Card
- [ ] Balance shows correct value (matches sol_sniper_state.json cash)
- [ ] Starting capital displays $1000
- [ ] Return % calculated correctly

### 2.3 PnL Cards
- [ ] Total PnL matches DB sum(pnl) from trade_log
- [ ] Today PnL filters by current date
- [ ] Trade count accurate (W/L breakdown)

### 2.4 Win Rate
- [ ] Percentage accurate vs DB
- [ ] Progress bar width matches %
- [ ] Badge shows correct trade count

### 2.5 Indicators (Real-time)
- [ ] StochRSI value updates (0-1 range)
- [ ] StochRSI badge: OVERSOLD (<0.12) / OVERBOUGHT (>0.88) / NEUTRAL
- [ ] Bollinger Bands: upper/mid/lower prices displayed
- [ ] BB thermometer dot position matches price vs bands
- [ ] Regime label: BULLISH/BEARISH/NEUTRAL with 30d detail

### 2.6 Micro-Grid Panel (NEW)
- [ ] Panel ALWAYS visible (not hidden when inactive)
- [ ] ATR Volatility gauge shows current % value
- [ ] ATR bar color: green (sideways <2.5%), accent (normal), red (volatile >3.5%)
- [ ] Badge states: ACTIVE (purple) / STANDBY (yellow) / OFF (gray)
- [ ] When active: shows filled/total levels, PnL, trade count
- [ ] When inactive: shows "Waiting for sideways market"
- [ ] Grid orders render correctly: SELL descending, MID line, BUY descending
- [ ] Filled orders highlighted with purple left border

### 2.7 Entry Conditions
- [ ] Long conditions: 4 rows with check/cross icons
- [ ] Short conditions: 4 rows with check/cross icons
- [ ] Score displays X/4 format
- [ ] "ENTRY READY" alert appears when 4/4 met
- [ ] Values update in real-time

### 2.8 Trade History (NEW)
- [ ] Grid fills show with GRID tag and "OPEN" / "pending" (yellow)
- [ ] Grid TP completions show PnL with GRID tag
- [ ] Sniper trades show without GRID tag
- [ ] Direction badges: LONG (green) / SHORT (red)
- [ ] PnL color coding: green positive, red negative
- [ ] Exit reason labels: TP, SL, TRAIL, TIME, OPEN, CLOSE

### 2.9 Signal History
- [ ] Signal feed populates when conditions 4/4
- [ ] Shows direction pill, price, time
- [ ] Max 10 items, newest first

### 2.10 Market Score
- [ ] Score value and direction badge
- [ ] BTC 1h price + change %
- [ ] Fear & Greed index with color
- [ ] Funding rate display
- [ ] Order Flow direction

### 2.11 Active Mode Strip
- [ ] SCANNING (gray) when idle
- [ ] SNIPER - LONG/SHORT (green/red) when position open
- [ ] GRID - SIDEWAYS (purple) when grid active

---

## Phase 3: Sniper + Grid Trading Logic (15 min)

### 3.1 Sniper Signal Detection
- [ ] Scan runs every 30s (check logs)
- [ ] StochRSI crossing threshold triggers signal
- [ ] BB touch confirmed
- [ ] Volume filter working
- [ ] Regime filter working

### 3.2 Sniper Position Management
- [ ] Position opens at correct price
- [ ] 80% capital allocation
- [ ] Maker fee deducted (0.04%)
- [ ] Position card shows on dashboard
- [ ] TP at 1.5% triggers close
- [ ] SL at 5% triggers close
- [ ] Trailing stop activates at 1.0%, closes at 0.5% drawdown
- [ ] 48h timeout close
- [ ] Cooldown 4h after SL

### 3.3 Micro-Grid Activation
- [ ] ATR < 2.5% activates grid
- [ ] ATR > 3.5% deactivates grid
- [ ] 6 levels built around mid price (3 buy + 3 sell)
- [ ] 0.5% spacing between levels
- [ ] $100 per level

### 3.4 Grid Order Execution
- [ ] Buy order fills when price <= grid level
- [ ] Sell order fills when price >= grid level
- [ ] TP set at next level (0.5%)
- [ ] TP execution on price touch
- [ ] Level resets after TP for reuse
- [ ] 2% drift triggers grid rebuild

### 3.5 Grid <-> Sniper Interaction
- [ ] Sniper signal deactivates grid
- [ ] Grid open positions closed on deactivation
- [ ] Grid PnL syncs to executor.cash (NEW)
- [ ] Grid trades written to trade_log DB (NEW)

### 3.6 Data Integrity
- [ ] Balance = starting_capital + sniper_pnl + grid_pnl
- [ ] DB trade_log count matches dashboard trade count
- [ ] sol_sniper_state.json updates every cycle
- [ ] Grid status in state file matches dashboard display

---

## Phase 4: Notifications (5 min)

### 4.1 iMessage
- [ ] Sniper open → iMessage sent
- [ ] Sniper close → iMessage sent
- [ ] Grid activate → iMessage sent (NEW)
- [ ] Grid trade TP → iMessage sent (NEW)
- [ ] Grid deactivate → iMessage sent (NEW)
- [ ] Grid -> Sniper switch → iMessage sent (NEW)

### 4.2 ntfy.sh Push
- [ ] Sniper open → push received
- [ ] Sniper close → push received
- [ ] Grid activate → push received (NEW)
- [ ] Grid trade TP → push received (NEW)
- [ ] Grid deactivate → push received (NEW)

### 4.3 Log Files
- [ ] sol_sniper.log writing (no errors)
- [ ] notifications.log entries correct
- [ ] sniper_notifications.log entries correct

---

## Phase 5: Owner Dashboard (8080) (10 min)

### 5.1 Page Load
- [ ] HTML renders correctly
- [ ] No JS console errors
- [ ] All 7 agents responding

### 5.2 Balance Agent
- [ ] Coinbase balance accurate
- [ ] USD/USDC breakdown
- [ ] Crypto holdings listed

### 5.3 Price Agent
- [ ] SOL real-time price
- [ ] BTC/ETH prices
- [ ] 24h change %

### 5.4 Orders Agent
- [ ] Active orders listed (scalper grid orders)
- [ ] Order count accurate
- [ ] Cancel functionality works

### 5.5 Trade Agent
- [ ] Recent fills displayed
- [ ] PnL per trade accurate
- [ ] Pagination working

### 5.6 Monitor Agent
- [ ] Market conditions dashboard
- [ ] Regime classification
- [ ] Whale activity
- [ ] Funding rates

### 5.7 Security Agent
- [ ] Health status green
- [ ] All processes alive
- [ ] No balance anomalies
- [ ] API latency normal

### 5.8 Report Agent
- [ ] Daily summary available
- [ ] PnL breakdown by strategy
- [ ] Win rate stats

---

## Phase 6: Public Tiers (8081/8082/8083) (10 min)

### 6.1 Preview (8081)
- [ ] Page loads without auth
- [ ] Market data visible
- [ ] Performance metrics shown
- [ ] No trading controls exposed
- [ ] No API keys or sensitive data leaked

### 6.2 Signals (8082)
- [ ] Access code gate working
- [ ] DEMO2026 code accepted
- [ ] Invalid code rejected
- [ ] Signal data displayed after auth
- [ ] No execution capabilities

### 6.3 Autopilot (8083)
- [ ] Access code required
- [ ] Customer key encryption working
- [ ] No plaintext keys in responses
- [ ] API endpoints require auth

### 6.4 Security Audit
- [ ] No API keys in HTML source
- [ ] No keys in API JSON responses
- [ ] No keys in console logs
- [ ] Access codes expire correctly
- [ ] Customer key vault encrypted

---

## Phase 7: Crazy Dashboard (8085) (5 min)

### 7.1 Display
- [ ] Balance + equity display
- [ ] Position card (if active)
- [ ] Daily P&L tracking
- [ ] Target progress ($1000 -> $3000)

### 7.2 Data
- [ ] crazy_state.json updates
- [ ] crazy_trader.db records
- [ ] Trade count accurate

---

## Phase 8: Background Services (5 min)

### 8.1 Monitor Harness
- [ ] monitor_state.json updating
- [ ] 5 agents running (sentiment, funding, whale, regime, social)
- [ ] Data fresh (< 5 min old)

### 8.2 Security Harness
- [ ] security_state.json updating
- [ ] Health checks passing
- [ ] No active alerts
- [ ] Auto-restart tested (kill a process, verify restart)

### 8.3 Scalper
- [ ] Process running
- [ ] scalper.db writing
- [ ] Grid orders placed on Coinbase
- [ ] Fills detected and logged
- [ ] Daily loss limit enforced

---

## Phase 9: Edge Cases & Error Handling (10 min)

### 9.1 Network Failures
- [ ] Exchange API timeout → graceful retry (no crash)
- [ ] ntfy.sh unreachable → logged, trading continues
- [ ] iMessage send failure → logged, trading continues

### 9.2 Data Corruption
- [ ] sol_sniper_state.json deleted → fresh state created
- [ ] DB locked → timeout retry

### 9.3 Trading Edge Cases
- [ ] Sniper signal during grid active → grid yields correctly
- [ ] Grid + Sniper concurrent → no double-count PnL
- [ ] Balance goes to $0 → no negative trades
- [ ] Price gap > 2% → grid rebuilds correctly

### 9.4 Dashboard Edge Cases
- [ ] Trading engine offline → dashboard shows OFFLINE
- [ ] Empty trade history → "No trades yet" message
- [ ] Very long running → no memory leak (check after 1h)

---

## Phase 10: Performance (5 min)

### 10.1 Response Times
- [ ] Dashboard API < 500ms
- [ ] Price updates < 3s latency
- [ ] Grid execution < 1s decision time

### 10.2 Resource Usage
- [ ] CPU < 30% total across all services
- [ ] Memory < 1GB total
- [ ] Disk: DB files not growing unbounded
- [ ] scalper.db size check (currently 462MB — may need cleanup)

### 10.3 Log Rotation
- [ ] Log files not exceeding 100MB
- [ ] Old logs archived or rotated

---

## Test Priority

| Priority | Phase | Est. Time | Risk |
|----------|-------|-----------|------|
| P0 | Phase 1 (Infra) | 5 min | System down |
| P0 | Phase 3 (Trading) | 15 min | Money at risk |
| P0 | Phase 4 (Notifications) | 5 min | Missed alerts |
| P1 | Phase 2 (Sniper UI) | 10 min | User experience |
| P1 | Phase 5 (Owner UI) | 10 min | User experience |
| P1 | Phase 9 (Edge Cases) | 10 min | Stability |
| P2 | Phase 6 (Public Tiers) | 10 min | Customer-facing |
| P2 | Phase 7 (Crazy) | 5 min | Challenge tracking |
| P2 | Phase 8 (Background) | 5 min | Data freshness |
| P3 | Phase 10 (Perf) | 5 min | Long-term health |

**Total estimated time: ~80 minutes**
