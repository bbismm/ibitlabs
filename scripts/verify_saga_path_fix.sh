#!/bin/zsh
#
# verify_saga_path_fix.sh — one-shot audit of the saga-daily entry after
# the 2026-05-10 stub + canonical path fixes.
#
# Fires once at 2026-05-11 22:50 local via
# ~/Library/LaunchAgents/com.ibitlabs.saga-daily-path-fix-verify-2026-05-11.plist
# (20 min after the 22:30 saga-daily fire, to let publish + deploy settle).
#
# Checks:
#   1. Did daily_2026-05-11.md get written?
#   2. Did body avoid the lobster_claw / verb-parser plumbing rut?
#   3. Topic-tier guess: does body contain trading anchors (price, PnL, position, balance, trade #)?
#   4. Footer: contains /signals not /dashboard? @ibitlabs_agent without "(交易号)" mislabel?
#   5. Word count in 300-800 range (or 1500-2500 if major)?
#   6. No banlist hits (P0 confidentiality — banlist is operator-local)?
#
# Report → ~/ibitlabs/logs/saga-daily/path-fix-verify-2026-05-11.log
# Notification → ntfy sol-sniper-bonny (one-line PASS/FAIL summary).
#
# After fire, the plist self-removes.

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/saga-daily"
LOG="$LOG_DIR/path-fix-verify-2026-05-11.log"
PLIST_LABEL="com.ibitlabs.saga-daily-path-fix-verify-2026-05-11"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
# Banlist lives outside the repo so confidential terms never enter git.
# Format: one term per line; `#` lines are comments. Used as case-insensitive
# regex via Python re.search.
BANLIST_FILE="$HOME/.config/ibitlabs/saga_banlist.txt"
export BANLIST_FILE

mkdir -p "$LOG_DIR"
exec > "$LOG" 2>&1

if [[ ! -f "$BANLIST_FILE" ]]; then
  echo "FATAL: confidentiality banlist not found at $BANLIST_FILE"
  echo "       verify_saga_path_fix refuses to run without a guardrail."
  exit 1
fi

echo "=== saga path-fix verify @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "ts_local: $(date)"
echo "==="

DAILY_FILE="$HOME/Documents/ai-creator-saga/daily/daily_2026-05-11.md"
# Also check for major-entry variants
MAJOR_GLOB=("$HOME/Documents/ai-creator-saga/daily/daily_2026-05-11_"*.md)

if [[ ! -f "$DAILY_FILE" ]] && [[ ! -f "${MAJOR_GLOB[1]:-/nonexistent}" ]]; then
  echo "=== FIRE LANDED: NO ==="
  echo "No daily_2026-05-11.md or major variant found in ~/Documents/ai-creator-saga/daily/"
  echo "RESULT: FAIL_NO_FIRE"
  curl -fsS --max-time 10 -H "Title: saga verify FAIL" \
    -d "no daily_2026-05-11 file — check ~/ibitlabs/logs/saga-daily/" \
    https://ntfy.sh/sol-sniper-bonny >/dev/null 2>&1 || true
  launchctl bootout gui/$(id -u)/$PLIST_LABEL 2>/dev/null || true
  rm -f "$PLIST_PATH"
  exit 1
fi

# Pick the file that exists (major variant has priority)
if [[ -f "${MAJOR_GLOB[1]:-/nonexistent}" ]]; then
  TARGET="${MAJOR_GLOB[1]}"
else
  TARGET="$DAILY_FILE"
fi

echo "TARGET: $TARGET"
echo "---"
python3 - "$TARGET" <<'PY'
import sys, re, os
path = sys.argv[1]
with open(path) as f:
    body = f.read()

# Strip footer for content checks (so footer keywords don't pollute trading-tier check)
footer_split = re.split(r'(\*这场实验在以下地方公开运行|^---\s*$\*)', body, maxsplit=1, flags=re.M)
content = footer_split[0] if len(footer_split) > 1 else body
footer = body[len(content):]

# Word count (Chinese: count CJK + Latin word approximation)
cjk = len(re.findall(r'[一-鿿]', content))
latin_words = len(re.findall(r'\b\w+\b', re.sub(r'[一-鿿]', '', content)))
approx_words = cjk + latin_words
print(f"approx word count: {approx_words}  (target 300-800 or 1500-2500 if major)")

# Lobster_claw rut check
lobster_hits = len(re.findall(r'lobster_claw|龙虾爪|verb parser|verb table|verb-parser', body, re.I))
print(f"lobster_claw rut keyword hits: {lobster_hits}  (target 0 unless genuinely the only event)")

# Trading anchor check
trading_kw = ['StochRSI', 'BB', 'trailing', 'trade #', 'Position', 'SOL', '账户', '余额', '保证金', '价格', 'PnL',
              '盈利', '亏损', '止损', '开仓', '出场', '入场', 'shadow rule', 'Rule [A-G]', 'live-status',
              'balance', 'drawdown']
trading_count = sum(1 for k in trading_kw if re.search(k, content))
print(f"trading anchor keyword hits in body: {trading_count}  (target ≥3)")

# Footer surface check
print(f"footer contains /dashboard?: {'YES (BUG)' if '/dashboard' in footer else 'no (good)'}")
print(f"footer contains /signals?:   {'YES (good)' if '/signals' in footer else 'no (BUG)'}")
print(f"footer contains '/essays'?:  {'YES (BUG)' if '/essays' in footer else 'no (good)'}")
print(f"footer contains '@ibitlabs_agent (交易号)'?: {'YES (BUG)' if '@ibitlabs_agent (交易号)' in footer or '交易号' in footer else 'no (good)'}")

# Confidentiality banned terms (loaded from operator-local banlist)
banlist_path = os.environ['BANLIST_FILE']
with open(banlist_path) as bf:
    banned = [ln.strip() for ln in bf if ln.strip() and not ln.lstrip().startswith('#')]
banned_hits = [t for t in banned if re.search(t, body, re.I)]
# Print COUNT only — never echo banned terms into the public log.
print(f"banned-term hits (P0 confidentiality): {len(banned_hits)} hit(s)" if banned_hits else "banned-term hits (P0 confidentiality): clean (good)")

# Verdict
problems = []
if lobster_hits > 3:
    problems.append("lobster_claw rut")
if trading_count < 3:
    problems.append("low trading-anchor density")
if '/dashboard' in footer:
    problems.append("footer /dashboard")
if '/essays' in footer:
    problems.append("footer /essays")
if '@ibitlabs_agent (交易号)' in footer or '交易号' in footer:
    problems.append("footer 交易号 mislabel")
if banned_hits:
    # Never echo the matched terms — only count + which positions in banlist.
    problems.append(f"banned terms: {len(banned_hits)} hit(s)")
if approx_words < 250 or (approx_words > 1000 and approx_words < 1500) or approx_words > 3000:
    problems.append(f"word count {approx_words} out of bands")

if not problems:
    print("\nRESULT: PASS")
else:
    print(f"\nRESULT: FAIL — {'; '.join(problems)}")
PY

RESULT=$(grep "^RESULT: " "$LOG" | tail -1 | sed 's/^RESULT: //')

curl -fsS --max-time 10 \
  -H "Title: saga path-fix verify" \
  -d "${RESULT:-UNKNOWN}
log: ~/ibitlabs/logs/saga-daily/path-fix-verify-2026-05-11.log
file: $TARGET" \
  https://ntfy.sh/sol-sniper-bonny >/dev/null 2>&1 || true

launchctl bootout gui/$(id -u)/$PLIST_LABEL 2>/dev/null || true
rm -f "$PLIST_PATH"
echo "==="
echo "plist removed: $PLIST_PATH"
echo "done @ $(date -u +%Y-%m-%dT%H:%M:%SZ)"
