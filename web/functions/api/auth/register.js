// POST /api/auth/register — Create new account
import { hashPassword, generateToken, normalizeEmail, validateEmail, createSession, json, CORS } from './_crypto.js';
import { checkRateLimit } from '../_auth.js';

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  // Rate limit: 5 registrations per hour per IP
  const rl = await checkRateLimit(context, { maxRequests: 5, windowSeconds: 3600, prefix: 'rl:reg' });
  if (!rl.allowed) return json({ error: 'Too many attempts. Try again later.' }, 429);

  try {
    const body = await context.request.json();
    const email = normalizeEmail(body.email);
    const password = body.password || '';

    if (!validateEmail(email)) return json({ error: 'Valid email required' }, 400);
    if (password.length < 8) return json({ error: 'Password must be at least 8 characters' }, 400);

    // Check if user already exists
    const existing = await KV.get(`user:${email}`);
    if (existing) return json({ error: 'Account already exists. Please log in.' }, 409);

    // Hash password
    const password_hash = await hashPassword(password);

    // Check if this email already has a paid plan (from Stripe)
    let plan = 'free';
    let accessCode = null;
    try {
      const accessRaw = await KV.get(`access:${email}`);
      if (accessRaw) {
        const accessData = JSON.parse(accessRaw);
        plan = accessData.plan || 'free';
        accessCode = accessData.code;
      }
    } catch {}

    // Create user
    const user = {
      email,
      password_hash,
      plan,
      status: 'active',
      access_code: accessCode,
      created_at: new Date().toISOString(),
      last_login: new Date().toISOString(),
    };
    await KV.put(`user:${email}`, JSON.stringify(user));

    // Create session
    const token = await createSession(KV, email, plan);

    return json({
      success: true,
      token,
      email,
      plan,
      access_code: accessCode,
    });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS });
}
