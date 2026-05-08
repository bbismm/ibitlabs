// Create Stripe Customer Portal session for subscription management

export async function onRequestPost(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
  if (!STRIPE_SK) return json({ error: 'Stripe not configured' }, 500);

  try {
    const { email } = await context.request.json();
    if (!email) return json({ error: 'Email required' }, 400);

    // Find customer
    const custRes = await fetch(`https://api.stripe.com/v1/customers?email=${encodeURIComponent(email)}&limit=1`, {
      headers: { 'Authorization': `Bearer ${STRIPE_SK}` }
    });
    const customers = await custRes.json();
    if (!customers.data?.length) {
      return json({ error: 'No Stripe account found for this email' }, 404);
    }

    const origin = new URL(context.request.url).origin;

    // Create portal session
    const portalRes = await fetch('https://api.stripe.com/v1/billing_portal/sessions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${STRIPE_SK}`,
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: new URLSearchParams({
        customer: customers.data[0].id,
        return_url: `${origin}/account`
      })
    });
    const portal = await portalRes.json();

    if (portal.error) return json({ error: portal.error.message }, 400);
    return json({ url: portal.url });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
