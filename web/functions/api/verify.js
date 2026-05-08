// ═══════════════════════════════════════════════════════════════
// BIBSUS Alpha · verify.js · POST /api/verify
// Validates access codes from frontend (signals page, autopilot page)
// Accepts: POST { code } or GET ?code=XX
// Returns: { valid, plan, email }
// ═══════════════════════════════════════════════════════════════

const CORS_HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Access-Code',
};

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: CORS_HEADERS });

async function validateCode(code, context) {
  if (!code) return { valid: false };

  const normalized = code.trim().toUpperCase();
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return { valid: false, error: 'Service unavailable' };

  try {
    const codeRaw = await KV.get(`code:${normalized}`);
    if (!codeRaw) return { valid: false };

    const codeData = JSON.parse(codeRaw);

    // Verify subscription is still active via Stripe
    const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
    if (STRIPE_SK && codeData.email) {
      const custRes = await fetch(
        `https://api.stripe.com/v1/customers?email=${encodeURIComponent(codeData.email)}&limit=1`,
        { headers: { 'Authorization': `Bearer ${STRIPE_SK}` } }
      );
      const customers = await custRes.json();

      if (customers.data?.length) {
        const customerId = customers.data[0].id;
        const subRes = await fetch(
          `https://api.stripe.com/v1/subscriptions?customer=${customerId}&status=active&limit=1`,
          { headers: { 'Authorization': `Bearer ${STRIPE_SK}` } }
        );
        const subs = await subRes.json();

        if (!subs.data?.length) {
          // No active subscription — check for one-time payments (academy)
          const chargeRes = await fetch(
            `https://api.stripe.com/v1/charges?customer=${customerId}&limit=10`,
            { headers: { 'Authorization': `Bearer ${STRIPE_SK}` } }
          );
          const charges = await chargeRes.json();
          const hasPaid = charges.data?.some(c => c.paid && !c.refunded && c.amount >= 9900);

          if (!hasPaid) {
            // Check KV manual grant
            const grantRaw = await KV.get(`grant:${codeData.email}`);
            if (!grantRaw) {
              return { valid: false, reason: 'subscription_expired' };
            }
          }
        }
      }
    }

    return { valid: true, plan: codeData.plan || 'pro', email: codeData.email };
  } catch (e) {
    return { valid: false, error: e.message };
  }
}

// POST /api/verify — { code: "BA-XXXXXXXX" }
export async function onRequestPost(context) {
  try {
    const length = parseInt(context.request.headers.get('Content-Length') || '0');
    if (length === 0) return json({ valid: false, error: 'Body required' }, 400);

    const body = await context.request.json();
    const code = body.code || '';
    const result = await validateCode(code, context);
    return json(result);
  } catch (e) {
    return json({ valid: false, error: e.message }, 500);
  }
}

// GET /api/verify?code=BA-XXXXXXXX — convenience alias
export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const code = url.searchParams.get('code') || '';
  const result = await validateCode(code, context);
  return json(result);
}

// OPTIONS — CORS preflight
export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS_HEADERS });
}
