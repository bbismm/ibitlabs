// POST /api/auth/logout — End session
import { getTokenFromRequest, deleteSession, json, CORS } from './_crypto.js';

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  const token = getTokenFromRequest(context.request);
  if (token) await deleteSession(KV, token);

  return json({ success: true });
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS });
}
