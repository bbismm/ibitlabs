// User status — comprehensive check combining Stripe + KV grants + access codes

export async function onRequestGet(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  const url = new URL(context.request.url);
  const email = url.searchParams.get('email');

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return json({ error: 'Valid email required' }, 400);
  }

  const normalEmail = email.toLowerCase().trim();
  const result = { active: false, source: null, plan: null, email: normalEmail, accessCode: null };

  try {
    const KV = context.env.REPLOT_REPORTS;

    // Check KV grant
    if (KV) {
      const grantRaw = await KV.get('grant:' + normalEmail);
      if (grantRaw) {
        const grant = JSON.parse(grantRaw);
        if (!grant.revoked) {
          result.active = true;
          result.source = 'grant';
          result.plan = 'granted';
          result.grantedAt = grant.grantedAt;
        }
      }
    }

    // Check Stripe
    const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
    if (STRIPE_SK) {
      const custRes = await fetch(`https://api.stripe.com/v1/customers?email=${encodeURIComponent(normalEmail)}&limit=1`, {
        headers: { 'Authorization': `Bearer ${STRIPE_SK}` }
      });
      const customers = await custRes.json();

      if (customers.data?.length) {
        const customerId = customers.data[0].id;
        result.customerId = customerId;

        // Check active subscriptions
        const subRes = await fetch(`https://api.stripe.com/v1/subscriptions?customer=${customerId}&status=active&limit=1`, {
          headers: { 'Authorization': `Bearer ${STRIPE_SK}` }
        });
        const subs = await subRes.json();
        if (subs.data?.length) {
          result.active = true;
          result.source = 'stripe';
          result.plan = 'pro';
          result.subscriptionStatus = subs.data[0].status;
          result.currentPeriodEnd = new Date(subs.data[0].current_period_end * 1000).toISOString();
        }

        // Check lifetime payments
        if (!result.active || result.source === 'grant') {
          const chargeRes = await fetch(`https://api.stripe.com/v1/charges?customer=${customerId}&limit=10`, {
            headers: { 'Authorization': `Bearer ${STRIPE_SK}` }
          });
          const charges = await chargeRes.json();
          const lifetime = charges.data?.find(c => c.paid && !c.refunded && c.amount >= 14900);
          if (lifetime) {
            result.active = true;
            result.source = 'stripe';
            result.plan = 'lifetime';
            result.paidAt = new Date(lifetime.created * 1000).toISOString();
          }
        }
      }
    }

    // Fetch access code from KV if user is active
    if (result.active && KV) {
      try {
        const accessRaw = await KV.get(`access:${normalEmail}`);
        if (accessRaw) {
          const accessData = JSON.parse(accessRaw);
          result.accessCode = accessData.code || null;
        }
      } catch {}
    }

    return json(result);
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
