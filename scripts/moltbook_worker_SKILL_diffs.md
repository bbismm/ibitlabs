# SKILL.md diffs for HTTP-worker route (Part 4/4)

These diffs replace direct `moltbook_publish.py` calls and direct `https://moltbook.com/api/v1/...` curl/Bearer calls with `moltbook_client.py` calls that route through the host worker.

**Apply only if you decide to switch off the `.env` route.** As of 2026-04-25 the `.env` route is stable across three consecutive scans (`Moltbook Learning Summary`), so these are filed as standby diffs.

---

## A. moltbook-brand-builder/SKILL.md — Step 6a (Moltbook publish)

### Current (lines ~265-289)

```bash
echo "$TITLE" > /tmp/mb_title.txt
echo "$BODY" > /tmp/mb_body.txt
python3 /Users/bonnyagent/scripts/moltbook_publish.py \
  --title-file /tmp/mb_title.txt \
  --body-file /tmp/mb_body.txt \
  --submolt general \
  --result-file /tmp/mb_result.json
```

### Replace with

```bash
echo "$TITLE" > /tmp/mb_title.txt
echo "$BODY" > /tmp/mb_body.txt
# Worker route — sandbox calls Mac host via http://host.docker.internal:8765
# MOLTBOOK_WORKER_TOKEN must be set in the scheduled-task env
# (retrieve once from Mac: cat ~/Library/Application\ Support/ibitlabs/moltbook-worker.token)
python3 /Users/bonnyagent/ibitlabs/scripts/moltbook_client.py post \
  --title-file /tmp/mb_title.txt \
  --body-file /tmp/mb_body.txt \
  --submolt general \
  --result-file /tmp/mb_result.json
```

### Same exit-code contract (no change needed in retry logic)
- 0 → success, read `/tmp/mb_result.json`, extract `.url`
- 2 → POST failed, do NOT retry, skip to Step 6b and flag
- 3 → verify failed and post deleted, ONE retry OK
- 4 → rate limited (worker passes through `retry_after_seconds`); sleep and retry once
- 5 → worker unreachable / token missing — treat as infra failure; flag and skip

### Also update API-key note (line ~286)

**Before**:
> **API key**: retrieved at runtime from macOS Keychain via: `security find-generic-password -s ibitlabs-moltbook-agent -a ibitlabs -w` (do NOT paste the literal key in any tracked file)

**After**:
> **API key**: handled by host-side `moltbook-worker` (loads from macOS Keychain at startup; never reaches the sandbox). Sandbox only needs `MOLTBOOK_WORKER_TOKEN` env var. Retrieve worker token from Mac host: `cat ~/Library/Application\ Support/ibitlabs/moltbook-worker.token`. Do NOT paste the literal Moltbook key anywhere; it lives only in Keychain + worker process memory.

---

## B. moltbook-brand-builder/SKILL.md — Step 2 reply path (line ~109)

### Current

> Use `python3 /Users/bonnyagent/scripts/moltbook_publish.py` with `--comment` flag if it supports it; otherwise the publisher's POST-verify-retry logic applies to comments equally.

### Replace with

> Use `python3 /Users/bonnyagent/ibitlabs/scripts/moltbook_client.py comment --post-id $PID --content-file /tmp/mb_reply.txt --result-file /tmp/mb_reply_result.json`. Worker handles POST + lobster-claw verify atomically and returns the same exit codes (0=ok, 2=POST fail, 3=verify fail, 4=rate-limited, 5=worker unreachable).

---

## C. moltbook-learning-loop/SKILL.md — read-side calls

### Current pattern (lines ~42-44, ~112, ~148)

Direct curl with `Authorization: Bearer ${MOLTBOOK_API_KEY}`:
```bash
curl -s -H "Authorization: Bearer $MOLTBOOK_API_KEY" https://moltbook.com/api/v1/home
curl -s -H "Authorization: Bearer $MOLTBOOK_API_KEY" https://moltbook.com/api/v1/agents/profile?name=ibitlabs_agent
```

### Replace with worker-routed equivalents

```bash
# Healthcheck (no auth)
curl -s http://host.docker.internal:8765/healthz

# Authed read endpoints
curl -s -H "Authorization: Bearer $MOLTBOOK_WORKER_TOKEN" \
  http://host.docker.internal:8765/moltbook/home

curl -s -H "Authorization: Bearer $MOLTBOOK_WORKER_TOKEN" \
  "http://host.docker.internal:8765/moltbook/profile?name=ibitlabs_agent"

curl -s -H "Authorization: Bearer $MOLTBOOK_WORKER_TOKEN" \
  http://host.docker.internal:8765/moltbook/posts/$POST_ID
```

Or via the Python client:
```bash
python3 /Users/bonnyagent/ibitlabs/scripts/moltbook_client.py home
python3 /Users/bonnyagent/ibitlabs/scripts/moltbook_client.py profile --name ibitlabs_agent
python3 /Users/bonnyagent/ibitlabs/scripts/moltbook_client.py get-post --post-id $PID
```

### Reply-post (line ~148): identical to brand-builder Step 2 reply path above.

### Notification mark-read

Worker does not currently expose `/notifications/read-by-post/{id}`. Two options:
1. **Add it to worker** (5-line addition — `_mb("POST", f"/notifications/read-by-post/{pid}", key, {})` mapped to a new `POST /moltbook/notifications/read?post_id=` endpoint), OR
2. **Keep `.env` route alive** for read-side only and use worker for writes only (acceptable hybrid; reduces blast radius if worker dies — only writes pause).

If you go with option 1, paste this into `moltbook_worker.py` `do_POST` after the `comment-and-verify` block:

```python
if path == "/moltbook/notifications/read":
    pid = (body.get("post_id") or "").strip()
    if not pid:
        return self._json(400, {"error": "post_id required"})
    status, j, raw = _mb("POST", f"/notifications/read-by-post/{pid}", self.moltbook_key, {})
    return self._json(status if status else 502, j if j else {"raw": raw[:400]})
```

---

## D. Operator rollout checklist

Order matters — do not skip steps.

1. **Start the worker on the Mac host** (this only needs to happen once per reboot once the LaunchAgent is loaded):
   ```bash
   launchctl load ~/Library/LaunchAgents/com.ibitlabs.moltbook-worker.plist
   # Verify:
   curl -s http://127.0.0.1:8765/healthz
   # Expected: {"status":"ok","service":"moltbook-worker","ts":...}
   ```

2. **Retrieve the worker token** (generated on first start; reused thereafter):
   ```bash
   cat ~/Library/Application\ Support/ibitlabs/moltbook-worker.token
   ```

3. **Wire `MOLTBOOK_WORKER_TOKEN` into the Cowork sandbox env** for these scheduled tasks:
   - `moltbook-brand-builder`
   - `moltbook-learning-loop`
   - `moltbook-reply-check` (if it makes Moltbook calls)

   Add it the same way `MOLTBOOK_API_KEY` is currently surfaced (per CLAUDE.md note: "operator surfaced into `/Users/bonnyagent/ibitlabs/.env`"). Either way works:
   - Option A — append to `/Users/bonnyagent/ibitlabs/.env`: `MOLTBOOK_WORKER_TOKEN=<token>`
   - Option B — set in scheduled-task env config

4. **Sandbox preflight from inside Cowork**:
   ```bash
   python3 /Users/bonnyagent/ibitlabs/scripts/moltbook_client.py health
   # Should print {"status":"ok",...}
   ```
   If unreachable: check that the sandbox can resolve `host.docker.internal`. If not, set `MOLTBOOK_WORKER_URL` to the host gateway IP (find via `ip route | awk '/default/{print $3}'` from inside the sandbox — typically `192.168.65.254` or similar on Docker for Mac).

5. **Cutover** — apply the SKILL.md diffs A/B/C above. Run brand-builder once manually to confirm the worker path posts and verifies cleanly.

6. **Rollback path** — if anything breaks, revert the SKILL.md diffs and the `.env` route resumes immediately. The worker can stay running unused without cost.

---

## E. Decision boundary (when to actually switch on)

The `.env` route is currently stable. Switch to the worker only when one of these triggers fires:

- Moltbook API key gets rotated and you want stricter isolation (no key in `.env` ever again)
- Sandbox env stops being able to read the `.env` for any reason
- You want a single audit log of every Moltbook write (worker logs to `~/ibitlabs/logs/moltbook-worker.log`)
- You add a second sandbox or non-Mac runner that needs Moltbook access without re-distributing the key

Until then: worker installed but cold. Token file present but unused.
