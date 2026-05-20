// ═══════════════════════════════════════════════════════════════
// iBitLabs · spot-bots-status.js · GET /api/spot-bots-status
// Edge-cached proxy of the 3 paper spot bots' dashboard JSONs.
// Origin lives on the local dashboard harness (sol_sniper_dashboard_harness.py)
// exposed via cloudflared at trade.bibsus.com.
//
// Cached 1s at the edge — same TTL as /api/live-status. The bots write
// their JSON every 60s; 1s cache is imperceptible drift to the human eye
// but cleanly absorbs traffic bursts.
//
// Wire-compatible with the build_report.py spot-bot renderer:
//   { updated_at, bots: { breakout_v01, pump_v01, pump_v02_tighttrail } }
// where each value is the bot's dashboard JSON written by its sniper script.
// ═══════════════════════════════════════════════════════════════

const ORIGIN = 'https://trade.bibsus.com/api/spot-bots-status';
const CACHE_TTL = 1;

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export async function onRequestGet(context) {
  const cache = caches.default;
  const cacheKey = new Request('https://ibitlabs.com/__internal/spot-bots-status', { method: 'GET' });

  let cached = await cache.match(cacheKey);
  if (cached) {
    const body = await cached.text();
    return new Response(body, {
      status: 200,
      headers: {
        ...CORS_HEADERS,
        'Content-Type': 'application/json; charset=utf-8',
        'X-Cache': 'HIT',
      },
    });
  }

  try {
    const res = await fetch(ORIGIN, {
      headers: { 'Accept': 'application/json' },
      cf: { cacheTtl: 0 },
    });
    if (!res.ok) {
      return new Response(
        JSON.stringify({ error: 'origin_error', status: res.status }),
        { status: 502, headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } }
      );
    }
    const body = await res.text();
    const response = new Response(body, {
      status: 200,
      headers: {
        ...CORS_HEADERS,
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': `public, max-age=${CACHE_TTL}`,
        'X-Cache': 'MISS',
      },
    });
    context.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  } catch (err) {
    return new Response(
      JSON.stringify({ error: 'fetch_failed', message: String(err) }),
      { status: 502, headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } }
    );
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}
