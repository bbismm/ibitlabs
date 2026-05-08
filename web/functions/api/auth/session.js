// GET /api/auth/session — Check current session
import { getTokenFromRequest, getSession, json, CORS } from './_crypto.js';

export async function onRequestGet(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  const token = getTokenFromRequest(context.request);
  if (!token) return json({ error: 'No session' }, 401);

  const session = await getSession(KV, token);
  if (!session) return json({ error: 'Session expired' }, 401);

  // Get latest user data
  let user = {};
  try {
    const userRaw = await KV.get(`user:${session.email}`);
    if (userRaw) user = JSON.parse(userRaw);
  } catch {}

  // Get access code
  let accessCode = user.access_code || null;
  if (!accessCode) {
    try {
      const accessRaw = await KV.get(`access:${session.email}`);
      if (accessRaw) accessCode = JSON.parse(accessRaw).code;
    } catch {}
  }

  // Check Telegram connection
  let telegramConnected = false;
  try {
    const tgRaw = await KV.get(`telegram:${session.email}`);
    if (tgRaw) telegramConnected = true;
  } catch {}

  return json({
    email: session.email,
    plan: user.plan || session.plan || 'free',
    access_code: accessCode,
    created_at: user.created_at,
    telegram_connected: telegramConnected,
    active: true,
  });
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS });
}
