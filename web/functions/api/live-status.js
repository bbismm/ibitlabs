// ═══════════════════════════════════════════════════════════════
// iBitLabs · live-status.js · GET /api/live-status
// Edge-cached proxy: fetches from the live trading host.
// Returns full indicators (indicators_pro) to everyone — site is
// fully public, no paywall. Plan gating retained but inert in case
// it's needed again later.
//
// NOTE 2026-04-30: ORIGIN still points at trade.bibsus.com/api/status
// because that is the hostname the bot's Cloudflare Tunnel currently
// terminates at. When the tunnel is re-pointed at trade.ibitlabs.com
// (or another ibitlabs.com host), update ORIGIN here in lockstep.
// ═══════════════════════════════════════════════════════════════

const ORIGIN = 'https://trade.bibsus.com/api/status';
const CACHE_TTL = 5; // seconds

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

const PAID_PLANS = new Set(['dashboard', 'autopilot', 'autopilot_yearly', 'pro', 'lifetime', 'granted']);

async function getUserPlan(request, env) {
  const auth = request.headers.get('Authorization') || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : null;
  if (!token || !env.REPLOT_REPORTS) return 'free';
  try {
    const raw = await env.REPLOT_REPORTS.get(`session:${token}`);
    if (!raw) return 'free';
    const session = JSON.parse(raw);
    // Check user record for latest plan
    const userRaw = await env.REPLOT_REPORTS.get(`user:${session.email}`);
    if (userRaw) {
      const user = JSON.parse(userRaw);
      return user.plan || session.plan || 'free';
    }
    return session.plan || 'free';
  } catch {
    return 'free';
  }
}

export async function onRequestGet(context) {
  const { request, env } = context;

  // Determine user plan (non-blocking for cache path)
  const planPromise = getUserPlan(request, env);

  // Check edge cache (shared across all users — contains full data)
  const cache = caches.default;
  const cacheKey = new Request('https://ibitlabs.com/__internal/live-status-full', { method: 'GET' });

  let body;
  let cached = await cache.match(cacheKey);
  if (cached) {
    body = await cached.text();
  } else {
    // Cache miss → fetch from origin
    try {
      const res = await fetch(ORIGIN, {
        headers: { 'Accept': 'application/json' },
        cf: { cacheTtl: 0 },
      });

      if (!res.ok) {
        return new Response(JSON.stringify({ error: 'origin_error', status: res.status }), {
          status: 502,
          headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
        });
      }

      body = await res.text();

      // Store full response in edge cache
      const cacheResp = new Response(body, {
        status: 200,
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'Cache-Control': `public, s-maxage=${CACHE_TTL}, max-age=${CACHE_TTL}`,
        },
      });
      context.waitUntil(cache.put(cacheKey, cacheResp));
    } catch (e) {
      return new Response(JSON.stringify({ error: 'fetch_failed', message: e.message }), {
        status: 502,
        headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
      });
    }
  }

  // Site is fully public — return everything to every caller.
  // (Plan lookup retained above so the gate can be re-enabled later
  // by reinstating the strip block.)
  await planPromise;

  let data;
  try {
    data = JSON.parse(body);
  } catch {
    return new Response(body, {
      status: 200,
      headers: { 'Content-Type': 'application/json', ...CORS_HEADERS, 'X-Cache': cached ? 'HIT' : 'MISS' },
    });
  }

  data._plan = 'pro';

  return new Response(JSON.stringify(data), {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',  // personalized response — don't cache at browser
      'X-Cache': cached ? 'HIT' : 'MISS',
      ...CORS_HEADERS,
    },
  });
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS_HEADERS });
}
