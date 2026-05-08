// Admin users — list Stripe customers and KV-granted users

import { verifyAdminToken } from './_auth.js';

export async function onRequestGet(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  const url = new URL(context.request.url);
  const token = url.searchParams.get('token');
  const action = url.searchParams.get('action');

  if (!await verifyAdminToken(context, token)) {
    return json({ error: 'Unauthorized' }, 401);
  }

  try {
    if (action === 'granted_users') {
      const KV = context.env.REPLOT_REPORTS;
      if (!KV) return json({ grants: [] });

      const list = await KV.list({ prefix: 'grant:' });
      const grants = [];
      for (const key of list.keys) {
        const raw = await KV.get(key.name);
        if (raw) {
          grants.push(JSON.parse(raw));
        }
      }
      return json({ grants });
    }

    if (action === 'stripe_customers') {
      const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
      if (!STRIPE_SK) return json({ customers: [] });

      const res = await fetch('https://api.stripe.com/v1/customers?limit=30', {
        headers: { 'Authorization': `Bearer ${STRIPE_SK}` }
      });
      const data = await res.json();
      const customers = (data.data || []).map(c => ({
        id: c.id,
        email: c.email,
        name: c.name,
        created: new Date(c.created * 1000).toISOString()
      }));
      return json({ customers });
    }

    return json({ error: 'action must be granted_users or stripe_customers' }, 400);
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
