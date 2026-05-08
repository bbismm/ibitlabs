// POST /api/auth/forgot — Send password reset email
import { generateToken, normalizeEmail, validateEmail, json, CORS } from './_crypto.js';
import { checkRateLimit } from '../_auth.js';

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  // Rate limit: 3 reset requests per hour per IP
  const rl = await checkRateLimit(context, { maxRequests: 3, windowSeconds: 3600, prefix: 'rl:forgot' });
  if (!rl.allowed) return json({ error: 'Too many attempts. Try again later.' }, 429);

  try {
    const body = await context.request.json();
    const email = normalizeEmail(body.email);

    if (!validateEmail(email)) return json({ error: 'Valid email required' }, 400);

    // Always return success (prevent email enumeration)
    const userRaw = await KV.get(`user:${email}`);
    if (!userRaw) return json({ success: true, message: 'If an account exists, a reset link has been sent.' });

    // Generate reset token
    const resetToken = generateToken();
    await KV.put(`reset:${resetToken}`, JSON.stringify({ email }), { expirationTtl: 3600 }); // 1 hour

    // Send email
    const SENDGRID_KEY = context.env.SENDGRID_API_KEY;
    if (SENDGRID_KEY) {
      const origin = context.request.headers.get('origin') || 'https://www.ibitlabs.com';
      const resetUrl = `${origin}/login?reset=${resetToken}`;

      await fetch('https://api.sendgrid.com/v3/mail/send', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${SENDGRID_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          personalizations: [{ to: [{ email }] }],
          from: { email: 'noreply@ibitlabs.com', name: 'iBitLabs' },
          subject: 'Reset your iBitLabs password',
          content: [{
            type: 'text/plain',
            value: `You requested a password reset for your iBitLabs account.\n\nClick here to reset:\n${resetUrl}\n\nThis link expires in 1 hour.\n\nIf you didn't request this, ignore this email.\n\n— iBitLabs`,
          }],
        }),
      });
    }

    return json({ success: true, message: 'If an account exists, a reset link has been sent.' });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS });
}
