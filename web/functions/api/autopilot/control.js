// ═══════════════════════════════════════════════════════════════
// BIBSUS Alpha · autopilot/control.js · POST /api/autopilot/control
// Pause, resume, or disconnect autopilot
// Body: { code, action: "pause" | "resume" | "disconnect" }
// ═══════════════════════════════════════════════════════════════

const CORS_HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: CORS_HEADERS });

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  try {
    const body = await context.request.json();
    const { code, action } = body;

    if (!code) return json({ error: 'Access code required' }, 400);
    if (!['pause', 'resume', 'disconnect'].includes(action)) {
      return json({ error: 'Action must be: pause, resume, or disconnect' }, 400);
    }

    // Resolve email from code
    const normalized = code.trim().toUpperCase();
    const codeRaw = await KV.get(`code:${normalized}`);
    if (!codeRaw) return json({ error: 'Invalid access code' }, 403);

    const codeData = JSON.parse(codeRaw);
    const email = codeData.email;
    if (!email) return json({ error: 'Invalid code data' }, 400);

    const regKey = `autopilot:${email}`;
    const regRaw = await KV.get(regKey);
    if (!regRaw) return json({ error: 'Not registered for Autopilot' }, 404);

    const reg = JSON.parse(regRaw);

    if (action === 'pause') {
      reg.paused = true;
      reg.pausedAt = new Date().toISOString();
    } else if (action === 'resume') {
      reg.paused = false;
      reg.resumedAt = new Date().toISOString();
    } else if (action === 'disconnect') {
      reg.status = 'disconnected';
      reg.disconnectedAt = new Date().toISOString();
      // Remove encrypted keys
      delete reg.cb_api_key_enc;
      delete reg.cb_api_secret_enc;
    }

    await KV.put(regKey, JSON.stringify(reg));

    return json({
      success: true,
      action,
      email,
      status: reg.status,
      paused: reg.paused || false,
    });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS_HEADERS });
}
