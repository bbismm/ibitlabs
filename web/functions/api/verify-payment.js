// ═══════════════════════════════════════════════════════════════
// BIBSUS Alpha · verify-payment.js · Cloudflare Pages Function
// Verifies a Stripe Checkout Session, generates access codes,
// and returns subscription status
// ═══════════════════════════════════════════════════════════════

async function stripeGet(path, STRIPE_SK) {
  const res = await fetch(`https://api.stripe.com/v1${path}`, {
    headers: { 'Authorization': `Bearer ${STRIPE_SK}` },
  });
  const data = await res.json();
  if (!res.ok) {
    return { error: data.error || { message: `Stripe API error: ${res.status}` } };
  }
  return data;
}

function generateAccessCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code = 'BA-';
  for (let i = 0; i < 8; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return code;
}

async function ensureAccessCode(KV, email, plan) {
  if (!KV || !email) return null;
  const normalEmail = email.toLowerCase().trim();
  const key = `access:${normalEmail}`;

  try {
    const existing = await KV.get(key);
    if (existing) {
      const parsed = JSON.parse(existing);
      if (parsed.code) return parsed.code;
    }
  } catch {}

  const code = generateAccessCode();
  const record = {
    code,
    email: normalEmail,
    plan,
    createdAt: new Date().toISOString(),
  };

  try {
    await KV.put(key, JSON.stringify(record));
    await KV.put(`code:${code}`, JSON.stringify({ email: normalEmail, plan, createdAt: record.createdAt }));
  } catch {}

  return code;
}

export async function onRequestGet(context) {
  const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
  const KV = context.env.REPLOT_REPORTS;

  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });

  if (!STRIPE_SK) {
    return json({ error: 'Stripe not configured' }, 500);
  }

  const url = new URL(context.request.url);
  const params = url.searchParams;

  try {
    // Mode 1: Verify a checkout session (after redirect from Stripe)
    if (params.get('session_id')) {
      const session = await stripeGet(`/checkout/sessions/${params.get('session_id')}`, STRIPE_SK);

      if (session.error) {
        return json({ error: session.error.message }, 400);
      }

      if (session.payment_status !== 'paid') {
        return json({ active: false, reason: 'not_paid' });
      }

      const email = session.customer_details?.email || session.customer_email || '';
      // Use metadata.plan if available (set by create-checkout), fallback to mode-based detection
      const plan = session.metadata?.plan || (session.mode === 'payment' ? 'academy' : 'signals');

      const accessCode = await ensureAccessCode(KV, email, plan);

      return json({
        active: true,
        plan,
        email,
        customerId: session.customer,
        accessCode,
      });
    }

    // Mode 2: Check subscription status by email
    if (params.get('email')) {
      const email = params.get('email');

      // Check manual KV grant first
      if (KV) {
        try {
          const grantRaw = await KV.get('grant:' + email.toLowerCase().trim());
          if (grantRaw) {
            const grant = JSON.parse(grantRaw);
            if (!grant.revoked) {
              const accessCode = await ensureAccessCode(KV, email, 'granted');
              return json({ active: true, plan: 'granted', email, source: 'grant', accessCode });
            }
          }
        } catch {}
      }

      // Search for customers with this email
      const customers = await stripeGet(`/customers?email=${encodeURIComponent(email)}&limit=1`, STRIPE_SK);
      if (!customers.data?.length) {
        return json({ active: false, reason: 'no_customer' });
      }

      const customerId = customers.data[0].id;

      // Check for active subscriptions
      const subs = await stripeGet(`/subscriptions?customer=${customerId}&status=active&limit=1`, STRIPE_SK);
      if (subs.data?.length) {
        const accessCode = await ensureAccessCode(KV, email, 'pro');
        return json({ active: true, plan: 'pro', email, accessCode });
      }

      // Check for one-time payments (lifetime)
      const charges = await stripeGet(`/charges?customer=${customerId}&limit=10`, STRIPE_SK);
      const hasPaid = charges.data?.some(c => c.paid && !c.refunded && c.amount >= 14900);
      if (hasPaid) {
        const accessCode = await ensureAccessCode(KV, email, 'lifetime');
        return json({ active: true, plan: 'lifetime', email, accessCode });
      }

      return json({ active: false, reason: 'no_active_plan' });
    }

    return json({ error: 'Provide session_id or email' }, 400);
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
