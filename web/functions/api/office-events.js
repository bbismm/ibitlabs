// ═══════════════════════════════════════════════════════════════
// iBitLabs · office-events.js · GET /api/office-events
// Edge-cached proxy for the pixel-office webapp at /office.
//
// Reads from trade.bibsus.com/data/office-events.json (cloudflared
// path-match → receipt-viewer at localhost:8090 → file written by
// pixel_office_bridge launchd daemon). The bridge hard-codes the
// PUBLIC_WHITELIST in Python — wallet_sniper / polymarket_sniper
// physically cannot reach this endpoint.
//
// Fully public, no auth. Mirrors the live-status.js cache pattern.
// ═══════════════════════════════════════════════════════════════

const ORIGIN = 'https://trade.bibsus.com/data/office-events.json';
const CACHE_TTL = 2; // seconds — short, public supervision wants near-realtime

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

export async function onRequestGet({ request }) {
  // Edge cache by URL + cursor (each ?since=N is a distinct cache key)
  const cacheUrl = new URL(request.url);
  const cacheKey = new Request(cacheUrl.toString(), request);
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  let upstream;
  try {
    upstream = await fetch(ORIGIN, { cf: { cacheTtl: CACHE_TTL, cacheEverything: true } });
  } catch (err) {
    return new Response(
      JSON.stringify({ cursor: 0, agents: [], events: [], error: String(err) }),
      {
        status: 502,
        headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
      },
    );
  }

  if (!upstream.ok) {
    return new Response(
      JSON.stringify({ cursor: 0, agents: [], events: [], error: `upstream ${upstream.status}` }),
      {
        status: upstream.status,
        headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
      },
    );
  }

  const body = await upstream.text();
  const res = new Response(body, {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': `public, max-age=${CACHE_TTL}`,
      ...CORS_HEADERS,
    },
  });
  // Best-effort cache write (don't block response)
  // event.waitUntil is not in plain Pages Functions context; just attempt sync put
  try {
    await cache.put(cacheKey, res.clone());
  } catch {
    /* ignore cache write failures */
  }
  return res;
}
