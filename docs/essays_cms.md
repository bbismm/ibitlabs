# Essays CMS — how `/essays` works now

**TL;DR:** `https://www.ibitlabs.com/essays` is now backed by a Notion database. Write an essay in Notion → check Published → it appears on the live site within ~10 minutes. Zero terminal, zero code edit.

---

## Architecture

```
Notion "Essays" database
        │
        │ (Notion API, 10 min edge cache)
        ▼
Cloudflare Pages Function  /api/essays
        │
        │ (fetch on page load)
        ▼
essays.html  →  renders cards

Fallback path:  if /api/essays returns 503 or empty,
                essays.html renders from its hardcoded
                FALLBACK_ESSAYS array (disaster recovery).
```

### Files

| File | Role |
|------|------|
| `web/public/essays.html` | Frontend. Fetches `/api/essays` on load, falls back to hardcoded `FALLBACK_ESSAYS` if the API is down. |
| `web/functions/api/essays.js` | Cloudflare Pages Function. Queries Notion, renders blocks → HTML, caches for 10 min at the edge. |

### Notion

- **Parent page:** `iBitLabs — Project Hub` (`33c3c821-a4aa-81f4-995d-e0a71e4d6e91`)
- **Database:** `Essays` (`8625c17813a9417c96a70f23f86d2377`)
- **Database URL:** https://www.notion.so/8625c17813a9417c96a70f23f86d2377

---

## Adding a new essay (Bonny's workflow)

1. Write the long-form piece on Moltbook.
2. Open Notion → `iBitLabs — Project Hub` → `Essays` database → **New** row.
3. Fill in:
   - **Title** — the headline
   - **Slug** — URL fragment, lowercase-dash-separated, e.g. `state-layer-lies`. Must be unique. Used in the page anchor (`/essays#state-layer-lies`).
   - **Date** — publication date
   - **Published** — check this to publish
   - **Featured** — check this to give it the purple glow treatment (only the latest/top piece should usually be featured)
   - **Badge** (optional) — short label, e.g. `Thread edit`
   - **Moltbook URL** (optional) — link to the original on Moltbook
4. Open the row and write the body as regular Notion content. Supported blocks:
   - Paragraphs
   - Headings 1/2/3 (all render as `<h2>`/`<h3>`)
   - Bulleted / numbered lists
   - Bold, italic, inline code, links
   - Code blocks
   - Quotes / callouts (both render as blockquote)
5. Wait ~10 min for the edge cache to expire. Essay is live at `https://www.ibitlabs.com/essays`.

### Forcing an immediate refresh

Two options:
- **Redeploy** (busts cache and is always zero-risk): `cd web && wrangler pages deploy public --project-name=bibsus --commit-dirty=true`
- **Wait it out:** max 10 min at any edge location.

If you want shorter cache in the future, change `CACHE_SECONDS` at the top of `web/functions/api/essays.js` and redeploy.

---

## One-time setup (do this once, before the CMS is active)

The Pages Function needs a Notion integration token. Until you set it, the API returns 503 and the site renders from the hardcoded fallback (still works, still looks right).

### Step 1 — Create a Notion internal integration

1. Go to https://www.notion.so/my-integrations
2. **New integration** → name: `iBitLabs Essays` → associated workspace: pick yours
3. Capability: **Read content** (nothing else needed)
4. Submit → copy the **Internal Integration Token** (starts with `secret_` or `ntn_`)

### Step 2 — Share the Essays database with the integration

1. Open the Essays database in Notion: https://www.notion.so/8625c17813a9417c96a70f23f86d2377
2. Click the **`⋯`** menu (top right) → **Connections** → **Connect to** → pick `iBitLabs Essays`
3. Confirm. Without this step the integration can see nothing.

### Step 3 — Add the token to Cloudflare Pages

```bash
cd /Users/bonnyagent/ibitlabs/web
wrangler pages secret put NOTION_TOKEN --project-name=bibsus
# paste the token from Step 1 when prompted
```

Optional — override the default database ID (only if you ever recreate it):

```bash
wrangler pages secret put NOTION_ESSAYS_DB_ID --project-name=bibsus
# paste: 8625c17813a9417c96a70f23f86d2377
```

The function already defaults to the current DB ID, so this is only needed if the DB ever changes.

### Step 4 — Redeploy (picks up the new env var)

```bash
cd /Users/bonnyagent/ibitlabs/web
wrangler pages deploy public --project-name=bibsus --commit-dirty=true
```

### Step 5 — Verify

```bash
curl -s https://www.ibitlabs.com/api/essays | head -c 200
```

Should return a JSON array starting with `[{"slug":"state-layer-lies",...}`. If it still returns `{"error":"notion_token_missing"}`, the secret did not take — redeploy once more. If it returns `{"error":"notion_unavailable",...}`, either the token is wrong or you forgot Step 2 (share the DB with the integration).

---

## What not to touch

- **Don't rename the database properties.** The Pages Function looks them up by name: `Title`, `Slug`, `Date`, `Published`, `Featured`, `Badge`, `Moltbook URL`. Renaming any of these breaks the API.
- **Don't delete the `FALLBACK_ESSAYS` array in `essays.html`.** It's the disaster recovery if Notion ever goes down.
- **Don't commit the Notion token anywhere.** It lives only in Cloudflare Pages secrets.

---

## Troubleshooting

**API returns `{"error":"notion_token_missing"}`**
→ Secret not set, or the deploy happened before the secret was added. Run Step 3 + Step 4.

**API returns `{"error":"notion_unavailable"}`**
→ Token is set but the Notion API call failed. Almost always: you didn't share the database with the integration (Step 2). Second most common: token typo.

**New essay is not appearing on the site**
→ (1) Is the row's `Published` checkbox on? (2) Is the `Slug` non-empty? (3) Has 10 minutes passed since you published? (4) Try a hard refresh (Cmd+Shift+R). (5) Redeploy to bust the cache instantly.

**Site renders the old 8 essays but none of my new ones**
→ This is the fallback kicking in. It means `/api/essays` is returning an error or empty. Check `curl https://www.ibitlabs.com/api/essays` — the error message tells you which case.

---

## Cost / limits

- Notion API: free tier is plenty. Each `/api/essays` hit = 1 query + N block-fetches (one per essay). With 10 min edge cache, at worst 144 cold hits per day globally.
- Cloudflare Pages Functions: well within the free tier.
