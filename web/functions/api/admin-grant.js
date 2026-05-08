// Admin grant/revoke access for a user email

import { verifyAdminToken } from './_auth.js';

export async function onRequestPost(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  try {
    const { token, email, action } = await context.request.json();

    if (!await verifyAdminToken(context, token)) {
      return json({ error: 'Unauthorized' }, 401);
    }

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return json({ error: 'Invalid email' }, 400);
    }

    if (!['grant', 'revoke'].includes(action)) {
      return json({ error: 'Action must be grant or revoke' }, 400);
    }

    const KV = context.env.REPLOT_REPORTS;
    if (!KV) return json({ error: 'KV not available' }, 500);

    const key = 'grant:' + email.toLowerCase().trim();

    if (action === 'grant') {
      await KV.put(key, JSON.stringify({
        email: email.toLowerCase().trim(),
        grantedAt: new Date().toISOString(),
        grantedBy: 'admin',
        revoked: false
      }));
    } else {
      const existing = await KV.get(key);
      const data = existing ? JSON.parse(existing) : { email: email.toLowerCase().trim() };
      await KV.put(key, JSON.stringify({
        ...data,
        revoked: true,
        revokedAt: new Date().toISOString()
      }));
    }

    return json({ success: true, email: email.toLowerCase().trim(), action });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
