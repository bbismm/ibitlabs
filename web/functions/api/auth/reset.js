// POST /api/auth/reset — Reset password with token
import { hashPassword, normalizeEmail, json, CORS } from './_crypto.js';

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  try {
    const body = await context.request.json();
    const { token, new_password } = body;

    if (!token) return json({ error: 'Reset token required' }, 400);
    if (!new_password || new_password.length < 8) return json({ error: 'Password must be at least 8 characters' }, 400);

    // Validate reset token
    const resetRaw = await KV.get(`reset:${token}`);
    if (!resetRaw) return json({ error: 'Invalid or expired reset link. Request a new one.' }, 400);

    const { email } = JSON.parse(resetRaw);
    const normalEmail = normalizeEmail(email);

    // Get user
    const userRaw = await KV.get(`user:${normalEmail}`);
    if (!userRaw) return json({ error: 'Account not found' }, 404);

    const user = JSON.parse(userRaw);

    // Update password
    user.password_hash = await hashPassword(new_password);
    user.updated_at = new Date().toISOString();
    await KV.put(`user:${normalEmail}`, JSON.stringify(user));

    // Delete reset token (one-time use)
    await KV.delete(`reset:${token}`);

    return json({ success: true, message: 'Password updated. You can now log in.' });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS });
}
