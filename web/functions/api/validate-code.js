// BIBSUS Alpha · validate-code.js
// Validates an access code against KV store
// Called by the Python signals harness to verify subscriber codes

export async function onRequestGet(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  const url = new URL(context.request.url);
  const code = url.searchParams.get('code');

  if (!code) {
    return json({ valid: false, error: 'Code required' }, 400);
  }

  const KV = context.env.REPLOT_REPORTS;
  if (!KV) {
    return json({ valid: false, error: 'Service unavailable' }, 503);
  }

  try {
    const codeRaw = await KV.get(`code:${code.trim().toUpperCase()}`);
    if (!codeRaw) {
      return json({ valid: false });
    }

    const codeData = JSON.parse(codeRaw);

    // Verify the subscriber still has an active plan
    const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
    if (STRIPE_SK && codeData.email) {
      const custRes = await fetch(`https://api.stripe.com/v1/customers?email=${encodeURIComponent(codeData.email)}&limit=1`, {
        headers: { 'Authorization': `Bearer ${STRIPE_SK}` }
      });
      const customers = await custRes.json();

      if (customers.data?.length) {
        const customerId = customers.data[0].id;
        const subRes = await fetch(`https://api.stripe.com/v1/subscriptions?customer=${customerId}&status=active&limit=1`, {
          headers: { 'Authorization': `Bearer ${STRIPE_SK}` }
        });
        const subs = await subRes.json();

        if (!subs.data?.length) {
          // Check lifetime payments
          const chargeRes = await fetch(`https://api.stripe.com/v1/charges?customer=${customerId}&limit=10`, {
            headers: { 'Authorization': `Bearer ${STRIPE_SK}` }
          });
          const charges = await chargeRes.json();
          const hasLifetime = charges.data?.some(c => c.paid && !c.refunded && c.amount >= 14900);

          if (!hasLifetime) {
            // Check KV grant
            const grantRaw = await KV.get(`grant:${codeData.email}`);
            if (!grantRaw) {
              return json({ valid: false, reason: 'subscription_expired' });
            }
          }
        }
      }
    }

    return json({ valid: true, plan: codeData.plan, email: codeData.email });
  } catch (e) {
    return json({ valid: false, error: e.message }, 500);
  }
}
