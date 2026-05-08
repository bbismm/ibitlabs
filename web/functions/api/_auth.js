// ═══════════════════════════════════════════════════════════════
// Replot AI · _auth.js · Shared auth & rate limiting utilities
// Used by auto-analyze.js and run-analysis.js
// ═══════════════════════════════════════════════════════════════

// Simple IP-based rate limiter using Cloudflare KV
// Allows `maxRequests` per `windowSeconds` per IP
export async function checkRateLimit(context, { maxRequests = 5, windowSeconds = 3600, prefix = 'rl' } = {}) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return { allowed: true }; // Skip if no KV

  const ip = context.request.headers.get('CF-Connecting-IP') || 'unknown';
  const key = `${prefix}:${ip}`;

  try {
    const raw = await KV.get(key);
    const count = raw ? parseInt(raw, 10) : 0;

    if (count >= maxRequests) {
      return { allowed: false, remaining: 0 };
    }

    await KV.put(key, String(count + 1), { expirationTtl: windowSeconds });
    return { allowed: true, remaining: maxRequests - count - 1 };
  } catch {
    return { allowed: true }; // Fail open if KV errors
  }
}

// Verify payment via Stripe (server-side check)
// Returns { paid: true, plan } or { paid: false }
export async function verifyPayment(context, email) {
  if (!email) return { paid: false };

  const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
  if (!STRIPE_SK) return { paid: false };

  try {
    const custRes = await fetch(`https://api.stripe.com/v1/customers?email=${encodeURIComponent(email)}&limit=1`, {
      headers: { 'Authorization': `Bearer ${STRIPE_SK}` },
    });
    const customers = await custRes.json();
    if (!customers.data?.length) return { paid: false };

    const customerId = customers.data[0].id;

    // Check active subscriptions
    const subRes = await fetch(`https://api.stripe.com/v1/subscriptions?customer=${customerId}&status=active&limit=1`, {
      headers: { 'Authorization': `Bearer ${STRIPE_SK}` },
    });
    const subs = await subRes.json();
    if (subs.data?.length) return { paid: true, plan: 'pro' };

    // Check lifetime payments
    const chargeRes = await fetch(`https://api.stripe.com/v1/charges?customer=${customerId}&limit=10`, {
      headers: { 'Authorization': `Bearer ${STRIPE_SK}` },
    });
    const charges = await chargeRes.json();
    const hasLifetime = charges.data?.some(c => c.paid && !c.refunded && c.amount >= 14900);
    if (hasLifetime) return { paid: true, plan: 'lifetime' };

    // Check manual KV grant
    const KV = context.env.REPLOT_REPORTS;
    if (KV) {
      const grantRaw = await KV.get('grant:' + email.toLowerCase().trim());
      if (grantRaw) {
        const grant = JSON.parse(grantRaw);
        if (!grant.revoked) return { paid: true, plan: 'granted' };
      }
    }

    return { paid: false };
  } catch {
    return { paid: false };
  }
}

// Verify admin session token from KV
export async function verifyAdminToken(context, token) {
  if (!token) return false;
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return false;
  try {
    const session = await KV.get('admin_session:' + token);
    return !!session;
  } catch {
    return false;
  }
}

// Sanitize address input — strip anything that looks like prompt injection
export function sanitizeAddress(address) {
  if (typeof address !== 'string') return '';
  // Remove control characters
  let clean = address.replace(/[\x00-\x1F\x7F]/g, '');
  // Limit length to 200 chars (no real address is longer)
  clean = clean.slice(0, 200);
  // Strip common injection patterns
  clean = clean.replace(/ignore\s+(all\s+)?previous\s+instructions?/gi, '');
  clean = clean.replace(/system\s*prompt/gi, '');
  clean = clean.replace(/you\s+are\s+now/gi, '');
  clean = clean.replace(/forget\s+(all\s+)?(your\s+)?instructions?/gi, '');
  clean = clean.replace(/override/gi, '');
  return clean.trim();
}
