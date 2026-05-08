// POST /api/auth/login — Authenticate user
import { verifyPassword, normalizeEmail, validateEmail, createSession, json, CORS } from './_crypto.js';
import { checkRateLimit } from '../_auth.js';

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  // Rate limit: 10 login attempts per 15 minutes per IP
  const rl = await checkRateLimit(context, { maxRequests: 10, windowSeconds: 900, prefix: 'rl:login' });
  if (!rl.allowed) return json({ error: 'Too many attempts. Try again in 15 minutes.' }, 429);

  try {
    const body = await context.request.json();
    const email = normalizeEmail(body.email);
    const password = body.password || '';

    if (!validateEmail(email)) return json({ error: 'Valid email required' }, 400);
    if (!password) return json({ error: 'Password required' }, 400);

    // Lookup user
    const userRaw = await KV.get(`user:${email}`);
    if (!userRaw) return json({ error: 'Invalid email or password' }, 401);

    const user = JSON.parse(userRaw);

    // Verify password
    const valid = await verifyPassword(password, user.password_hash);
    if (!valid) return json({ error: 'Invalid email or password' }, 401);

    if (user.status === 'suspended') return json({ error: 'Account suspended' }, 403);

    // Refresh plan from KV (in case they paid after registering)
    let plan = user.plan || 'free';
    try {
      const accessRaw = await KV.get(`access:${email}`);
      if (accessRaw) {
        const accessData = JSON.parse(accessRaw);
        if (accessData.plan && accessData.plan !== 'free') {
          plan = accessData.plan;
          user.plan = plan;
          user.access_code = accessData.code;
        }
      }
    } catch {}

    // Update last login
    user.last_login = new Date().toISOString();
    await KV.put(`user:${email}`, JSON.stringify(user));

    // Create session
    const token = await createSession(KV, email, plan);

    return json({
      success: true,
      token,
      email,
      plan,
      access_code: user.access_code || null,
    });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS });
}
