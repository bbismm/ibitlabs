#!/bin/zsh
#
# verify_moltbook_path_fix.sh — one-shot audit of brand-builder behavior
# after the 2026-05-10 SKILL.md path fix.
#
# Fires once at 2026-05-11 02:30 local via
# ~/Library/LaunchAgents/com.ibitlabs.moltbook-path-fix-verify-2026-05-11.plist
# (30 min after the 02:00 launchd fire, to let the publish chain settle).
#
# Checks:
#   1. Did a new post land at/after 2026-05-11 02:00 UTC-equivalent?
#   2. Does its body have a trading-system artifact mention?
#   3. Does it have a fenced code block (C-path snippet)?
#   4. Is body length in the 1800-2800 hard ban window?
#   5. Does it contain any HTML/template artifact tokens (gemma-recycled etc)?
#   6. Has the public bio cache refreshed to the new framing?
#
# Report → ~/ibitlabs/logs/moltbook-brand-builder/path-fix-verify-2026-05-11.log
# Notification → ntfy sol-sniper-bonny (one-line PASS/FAIL summary).
#
# After fire, the plist self-removes via launchctl bootout in this script.

set -u
set -o pipefail

LOG_DIR="$HOME/ibitlabs/logs/moltbook-brand-builder"
LOG="$LOG_DIR/path-fix-verify-2026-05-11.log"
PLIST_LABEL="com.ibitlabs.moltbook-path-fix-verify-2026-05-11"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

mkdir -p "$LOG_DIR"
exec > "$LOG" 2>&1

echo "=== moltbook path-fix verify @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "ts_local: $(date)"
echo "==="

API_KEY=$(security find-generic-password -s ibitlabs-moltbook-agent -w 2>/dev/null)
if [[ -z "$API_KEY" ]]; then
  echo "FATAL: no API key in keychain (service=ibitlabs-moltbook-agent)"
  curl -fsS --max-time 10 -H "Title: moltbook verify FAIL" \
    -d "API key missing — verification could not run" \
    https://ntfy.sh/sol-sniper-bonny >/dev/null 2>&1 || true
  exit 1
fi

AGENT_ID="e600ab72-ba07-453e-b7cf-604235bb7b37"

# Fetch posts
curl -sS "https://moltbook.com/api/v1/posts?agent_id=$AGENT_ID&limit=10" \
  -H "X-API-Key: $API_KEY" -o /tmp/mb_verify_posts.json

# Fetch public profile (for bio cache check)
curl -sS "https://moltbook.com/api/v1/agents/profile?name=ibitlabs_agent" \
  -H "X-API-Key: $API_KEY" -o /tmp/mb_verify_profile.json

# Fetch authed agent (for ground-truth bio)
curl -sS "https://moltbook.com/api/v1/agents/me" \
  -H "X-API-Key: $API_KEY" -o /tmp/mb_verify_me.json

VERDICT=$(python3 <<'PY'
import json, re, sys
from datetime import datetime, timezone

# Posts
with open('/tmp/mb_verify_posts.json') as f:
    d = json.load(f)
posts = d if isinstance(d, list) else (d.get('posts') or d.get('data') or [])

# Find posts ≥ 2026-05-11 06:00 UTC (02:00 EDT = 06:00 UTC)
cutoff = datetime(2026, 5, 11, 6, 0, tzinfo=timezone.utc)
fresh = []
for p in posts:
    t = p.get('created_at') or p.get('createdAt') or ''
    try:
        dt = datetime.fromisoformat(t.replace('Z', '+00:00'))
        if dt >= cutoff:
            fresh.append(p)
    except Exception:
        pass

verdict = {'fire_landed': False, 'checks': {}, 'samples': []}

if not fresh:
    print("=== FIRE LANDED: NO ===")
    print(f"No post found at/after 2026-05-11 06:00 UTC (02:00 EDT).")
    print(f"Most recent 3 posts in feed:")
    posts_sorted = sorted(posts, key=lambda p: p.get('created_at',''), reverse=True)
    for p in posts_sorted[:3]:
        print(f"  {p.get('created_at','?')[:19]} | {p.get('title','')[:80]}")
    print()
    print("VERDICT: fire-not-detected — check launchd log at ~/ibitlabs/logs/moltbook-brand-builder/")
    print("RESULT: FAIL_NO_FIRE")
else:
    verdict['fire_landed'] = True
    print(f"=== FIRE LANDED: YES — {len(fresh)} new post(s) since cutoff ===")
    print()
    trading_kw = ['sniper', 'SOL', 'USD', 'trade', 'shadow rule', 'hybrid_v5', 'sol_sniper',
                  'live-status', 'jsonl', 'margin', 'tp/sl', 'drawdown', 'PnL', 'fee', 'position',
                  'entry', 'exit', 'rule b', 'rule c', 'rule f', 'atr', 'fee_cushion', 'mfe',
                  'mae', 'regime', 'contributors.json', 'trade_log']
    bad_tokens = ['<!--', '-->', '[//]:', '{{', '}}', '<<', '>>', 'gemma-recycled', 'gemma_recycled',
                  'claude-draft', '<source:']
    pass_all = True
    for i, p in enumerate(fresh, 1):
        title = p.get('title','')
        body = p.get('content') or p.get('body') or ''
        created = p.get('created_at','')[:19]
        body_len = len(body)
        tr_count = sum(1 for k in trading_kw if k.lower() in body.lower())
        code_blocks = len(re.findall(r'```', body)) // 2
        bad_hits = [t for t in bad_tokens if t in body]
        in_length_band = 1800 <= body_len <= 2800
        checks = {
            'has_trading_artifact': tr_count >= 2,
            'has_fenced_code': code_blocks >= 1,
            'in_length_band': in_length_band,
            'clean_of_artifacts': len(bad_hits) == 0,
        }
        passed = all(checks.values())
        if not passed:
            pass_all = False
        verdict['samples'].append({'title': title, 'checks': checks})
        print(f"--- post {i} @ {created} ---")
        print(f"  title:        {title[:90]}")
        print(f"  body len:     {body_len}  in band? {'YES' if in_length_band else 'NO'}")
        print(f"  trading kw:   {tr_count}  pass? {'YES' if tr_count>=2 else 'NO'}")
        print(f"  fenced code:  {code_blocks}  pass? {'YES' if code_blocks>=1 else 'NO'}")
        print(f"  bad tokens:   {bad_hits if bad_hits else 'clean'}")
        print(f"  → post {i}: {'PASS' if passed else 'FAIL'}")
        print()
    if pass_all:
        print("VERDICT: all post(s) pass all 4 content checks")
        print("RESULT: PASS_CONTENT")
    else:
        print("VERDICT: at least one post failed content checks above")
        print("RESULT: FAIL_CONTENT")

print()

# Bio cache check
with open('/tmp/mb_verify_profile.json') as f:
    pf = json.load(f)
with open('/tmp/mb_verify_me.json') as f:
    me = json.load(f)
pub_bio = pf.get('agent',{}).get('description','')
auth_bio = me.get('agent',{}).get('description','')
print("=== BIO CACHE CHECK ===")
print(f"  authed /me bio:    {auth_bio[:80]}...")
print(f"  public profile:    {pub_bio[:80]}...")
if pub_bio == auth_bio:
    print("  → BIO_CACHE: REFRESHED ✓")
elif 'Zero human code' in pub_bio or '7 days' in pub_bio:
    print("  → BIO_CACHE: STILL_STALE — old framing still showing in public view")
else:
    print("  → BIO_CACHE: DIVERGED — public shows something else")
PY
)

echo "$VERDICT"

# Extract one-line result for ntfy
RESULT=$(echo "$VERDICT" | grep -E "^RESULT: " | head -1 | sed 's/^RESULT: //')
BIO_LINE=$(echo "$VERDICT" | grep "BIO_CACHE:" | head -1 | sed 's/^.*→ //')

NTFY_TITLE="moltbook path-fix verify"
NTFY_BODY="content: ${RESULT:-UNKNOWN}
${BIO_LINE:-bio: unknown}
log: ~/ibitlabs/logs/moltbook-brand-builder/path-fix-verify-2026-05-11.log"

curl -fsS --max-time 10 \
  -H "Title: $NTFY_TITLE" \
  -d "$NTFY_BODY" \
  https://ntfy.sh/sol-sniper-bonny >/dev/null 2>&1 || true

# Self-remove plist (one-shot)
launchctl bootout gui/$(id -u)/$PLIST_LABEL 2>/dev/null || true
rm -f "$PLIST_PATH"
echo "==="
echo "plist removed: $PLIST_PATH"
echo "done @ $(date -u +%Y-%m-%dT%H:%M:%SZ)"
