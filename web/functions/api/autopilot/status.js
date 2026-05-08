// ═══════════════════════════════════════════════════════════════
// BIBSUS Alpha · autopilot/status.js · GET /api/autopilot/status
// Returns autopilot customer status, P/L, and position info
// Query: ?code=BA-XXXXXXXX or ?email=user@example.com
// ═══════════════════════════════════════════════════════════════

const CORS_HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Access-Code',
};

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: CORS_HEADERS });

export async function onRequestGet(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  const url = new URL(context.request.url);
  let email = url.searchParams.get('email');
  const code = url.searchParams.get('code') || context.request.headers.get('X-Access-Code');

  // Resolve email from code if needed
  if (!email && code) {
    try {
      const codeRaw = await KV.get(`code:${code.trim().toUpperCase()}`);
      if (codeRaw) {
        const codeData = JSON.parse(codeRaw);
        email = codeData.email;
      }
    } catch {}
  }

  if (!email) return json({ error: 'Email or access code required' }, 400);

  try {
    const regRaw = await KV.get(`autopilot:${email.toLowerCase().trim()}`);
    if (!regRaw) {
      return json({ registered: false, error: 'Not registered for Autopilot' }, 404);
    }

    const reg = JSON.parse(regRaw);

    // Read latest P/L data if available
    let pnlData = {};
    try {
      const pnlRaw = await KV.get(`autopilot_pnl:${email.toLowerCase().trim()}`);
      if (pnlRaw) pnlData = JSON.parse(pnlRaw);
    } catch {}

    return json({
      registered: true,
      email: reg.email,
      status: reg.status || 'active',
      paused: reg.paused || false,
      registeredAt: reg.registeredAt,
      pnl: pnlData.total_pnl || 0,
      trades: pnlData.total_trades || 0,
      position: pnlData.position || null,
      lastUpdate: pnlData.updatedAt || null,
    });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS_HEADERS });
}
