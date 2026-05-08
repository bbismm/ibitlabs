// POST /api/auth/telegram-disconnect — Unlink Telegram from account
import { getTokenFromRequest, getSession, json, CORS } from './_crypto.js';

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  const token = getTokenFromRequest(context.request);
  if (!token) return json({ error: 'Not logged in' }, 401);

  const session = await getSession(KV, token);
  if (!session) return json({ error: 'Session expired' }, 401);

  const email = session.email;

  try {
    // Get existing Telegram connection
    const tgRaw = await KV.get(`telegram:${email}`);
    if (tgRaw) {
      const tg = JSON.parse(tgRaw);
      // Remove both directions
      if (tg.chat_id) await KV.delete(`telegram_chat:${tg.chat_id}`);
      await KV.delete(`telegram:${email}`);
    }

    return json({ success: true });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS });
}
