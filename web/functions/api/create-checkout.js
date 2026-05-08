// ═══════════════════════════════════════════════════════════════
// iBitLabs · create-checkout.js · Cloudflare Pages Function
// Plans:
//   dashboard      — $19/mo subscription (real-time signals, manual copy-trade)
//   dashboard_yearly — $199/year (save $29)
//   autopilot      — $49/mo subscription (automated trading, $5K+ recommended)
//   autopilot_yearly — $499/year (save $89)
// ═══════════════════════════════════════════════════════════════

export async function onRequestPost(context) {
  const STRIPE_SK = context.env.STRIPE_SECRET_KEY;

  // Price IDs from Stripe Dashboard
  const PRICE_DASHBOARD       = context.env.STRIPE_PRICE_DASHBOARD;        // $19/mo
  const PRICE_DASHBOARD_YEARLY = context.env.STRIPE_PRICE_DASHBOARD_YEARLY; // $199/year
  const PRICE_AUTOPILOT       = context.env.STRIPE_PRICE_AUTOPILOT;        // $49/mo
  const PRICE_AUTOPILOT_YEARLY = context.env.STRIPE_PRICE_AUTOPILOT_YEARLY; // $499/year

  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });

  if (!STRIPE_SK) {
    return json({ error: 'Stripe not configured' }, 500);
  }

  try {
    const { plan, email } = await context.request.json();

    const plans = {
      dashboard:        { priceId: PRICE_DASHBOARD,        mode: 'subscription' },
      dashboard_yearly: { priceId: PRICE_DASHBOARD_YEARLY, mode: 'subscription' },
      autopilot:        { priceId: PRICE_AUTOPILOT,        mode: 'subscription' },
      autopilot_yearly: { priceId: PRICE_AUTOPILOT_YEARLY, mode: 'subscription' },
    };

    if (!plan || !plans[plan]) {
      return json({ error: `Unknown plan: "${plan}". Valid: ${Object.keys(plans).join(', ')}` }, 400);
    }

    const { priceId, mode } = plans[plan];

    if (!priceId) {
      return json({ error: `Price not configured for plan "${plan}". Set STRIPE_PRICE_${plan.toUpperCase()} in Cloudflare.` }, 400);
    }

    const origin = context.request.headers.get('origin')
      || context.request.headers.get('referer')?.replace(/\/[^/]*$/, '')
      || 'https://www.ibitlabs.com';

    // Get logged-in user's email from session token
    let customerEmail = email || '';
    if (!customerEmail) {
      const auth = context.request.headers.get('Authorization') || '';
      if (auth.startsWith('Bearer ')) {
        const KV = context.env.REPLOT_REPORTS;
        if (KV) {
          try {
            const sessionRaw = await KV.get(`session:${auth.slice(7)}`);
            if (sessionRaw) customerEmail = JSON.parse(sessionRaw).email || '';
          } catch {}
        }
      }
    }

    const body = new URLSearchParams({
      'line_items[0][price]': priceId,
      'line_items[0][quantity]': '1',
      mode,
      'success_url': `${origin}/account?payment=success&session_id={CHECKOUT_SESSION_ID}`,
      'cancel_url': `${origin}/?payment=cancelled`,
      'allow_promotion_codes': 'true',
      'metadata[plan]': plan,
    });

    // Pre-fill email so webhook can match to user account
    if (customerEmail) body.set('customer_email', customerEmail);

    const res = await fetch('https://api.stripe.com/v1/checkout/sessions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${STRIPE_SK}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: body.toString(),
    });

    const session = await res.json();

    if (session.error) {
      return json({ error: session.error.message }, 400);
    }

    return json({ url: session.url, sessionId: session.id });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
