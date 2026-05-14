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
// 2026-05-14: dropped 5s → 1s so the /office MTM row updates visibly. The
// front-end polls every 2s; with TTL=5 the user saw the same number for
// long stretches even though the bot's price was moving. TTL=1 still
// absorbs traffic bursts (single-digit RPS) but stays imperceptible to
// the human eye.
const CACHE_TTL = 1; // seconds

// 2026-05-14: bot's scan loop only writes current_price every ~20-30s, so
// even with TTL=1 the public MTM looked frozen. Fix: fetch Coinbase spot
// ticker in parallel and overwrite position.current_price + pnl_usd with
// the edge-fresh value. Bot's entry/qty/direction stay canonical; only the
// mark price gets refreshed. SOL only — when a live ETH/BTC bot ships,
// extend SPOT_PRODUCT_BY_SYMBOL accordingly.
const SPOT_PRODUCT_BY_SYMBOL = {
  'SLP-20DEC30-CDE': 'SOL-USD',
  'ETP-20DEC30-CDE': 'ETH-USD',
};

async function fetchSpotPrice(productId) {
  try {
    const res = await fetch(
      `https://api.exchange.coinbase.com/products/${productId}/ticker`,
      { cf: { cacheTtl: 0 }, headers: { 'User-Agent': 'ibitlabs-pages/1.0' } }
    );
    if (!res.ok) return null;
    const j = await res.json();
    const p = parseFloat(j.price);
    return Number.isFinite(p) ? p : null;
  } catch {
    return null;
  }
}

function freshenPosition(data, spotPrice) {
  const pos = data && data.position;
  if (!pos || !pos.active || typeof pos.entry_price !== 'number'
      || typeof pos.contracts !== 'number' || typeof pos.notional !== 'number'
      || (pos.direction !== 'long' && pos.direction !== 'short')
      || spotPrice === null) {
    return data;
  }
  // contract_size = notional / (entry × qty) — derived so we don't hardcode per symbol.
  const denom = pos.entry_price * pos.contracts;
  if (denom <= 0) return data;
  const contractSize = pos.notional / denom;
  const sign = pos.direction === 'long' ? 1 : -1;
  const freshPnl = sign * (spotPrice - pos.entry_price) * pos.contracts * contractSize;
  const freshPct = freshPnl / pos.notional;
  pos.current_price = spotPrice;
  pos.pnl_usd = Math.round(freshPnl * 100) / 100;
  pos.pnl_pct = Math.round(freshPct * 100000) / 100000;
  return data;
}

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
    // Cache miss → fetch bot status + Coinbase spot price in parallel.
    // The bot's current_price ticks every ~20-30s (slow scan loop); the spot
    // ticker is real-time and lets us recompute MTM at edge cadence.
    try {
      const origPromise = fetch(ORIGIN, {
        headers: { 'Accept': 'application/json' },
        cf: { cacheTtl: 0 },
      });

      const res = await origPromise;
      if (!res.ok) {
        return new Response(JSON.stringify({ error: 'origin_error', status: res.status }), {
          status: 502,
          headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
        });
      }
      const rawBody = await res.text();
      let parsed;
      try {
        parsed = JSON.parse(rawBody);
      } catch {
        // Origin returned non-JSON — pass through unchanged.
        body = rawBody;
        const cacheResp = new Response(body, {
          status: 200,
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': `public, s-maxage=${CACHE_TTL}, max-age=${CACHE_TTL}`,
          },
        });
        context.waitUntil(cache.put(cacheKey, cacheResp));
        parsed = null;
      }

      if (parsed) {
        const sym = parsed?.position?.symbol;
        const productId = sym ? SPOT_PRODUCT_BY_SYMBOL[sym] : null;
        if (productId && parsed?.position?.active) {
          const spot = await fetchSpotPrice(productId);
          if (spot !== null) freshenPosition(parsed, spot);
        }
        body = JSON.stringify(parsed);
        const cacheResp = new Response(body, {
          status: 200,
          headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': `public, s-maxage=${CACHE_TTL}, max-age=${CACHE_TTL}`,
          },
        });
        context.waitUntil(cache.put(cacheKey, cacheResp));
      }
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
