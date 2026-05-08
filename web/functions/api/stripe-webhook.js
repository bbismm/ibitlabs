// ═══════════════════════════════════════════════════════════════
// iBitLabs · stripe-webhook.js · POST /api/stripe-webhook
// Handles Stripe events: checkout.session.completed, customer.subscription.deleted
// Auto-generates access codes and sends confirmation
//
// Setup in Stripe Dashboard → Developers → Webhooks:
//   URL: https://ibitlabs.com/api/stripe-webhook
//   Events: checkout.session.completed, customer.subscription.deleted
//   Set STRIPE_WEBHOOK_SECRET env var to the webhook signing secret
// ═══════════════════════════════════════════════════════════════

function generateAccessCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code = 'BA-';
  for (let i = 0; i < 8; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return code;
}

function detectPlan(session) {
  // Check price IDs or metadata to determine which plan
  const lineItems = session.line_items?.data || [];
  const metadata = session.metadata || {};

  if (metadata.plan) return metadata.plan;

  // Fallback: check by mode
  if (session.mode === 'payment') return 'academy';
  return session.mode === 'subscription' ? 'signals' : 'unknown';
}

async function ensureAccessCode(KV, email, plan) {
  if (!KV || !email) return null;
  const normalEmail = email.toLowerCase().trim();
  const key = `access:${normalEmail}`;

  try {
    const existing = await KV.get(key);
    if (existing) {
      const parsed = JSON.parse(existing);
      // Update plan if upgrading
      if (parsed.code) {
        if (plan && parsed.plan !== plan) {
          parsed.plan = plan;
          await KV.put(key, JSON.stringify(parsed));
          await KV.put(`code:${parsed.code}`, JSON.stringify({
            email: normalEmail, plan, createdAt: parsed.createdAt
          }));
        }
        return parsed.code;
      }
    }
  } catch {}

  const code = generateAccessCode();
  const record = { code, email: normalEmail, plan, createdAt: new Date().toISOString() };

  await KV.put(key, JSON.stringify(record));
  await KV.put(`code:${code}`, JSON.stringify({ email: normalEmail, plan, createdAt: record.createdAt }));

  return code;
}

// ── Stripe HMAC-SHA256 webhook signature verification ──
async function verifyStripeSignature(rawBody, sigHeader, secret) {
  // Parse Stripe signature header: t=timestamp,v1=signature
  const parts = {};
  for (const item of sigHeader.split(',')) {
    const [key, val] = item.split('=');
    parts[key] = val;
  }
  const timestamp = parts['t'];
  const signature = parts['v1'];
  if (!timestamp || !signature) return false;

  // Reject if timestamp too old (5 min tolerance)
  const age = Math.floor(Date.now() / 1000) - parseInt(timestamp);
  if (isNaN(age) || age > 300 || age < -60) return false;

  // Compute expected signature: HMAC-SHA256(secret, timestamp + '.' + payload)
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const signed = await crypto.subtle.sign('HMAC', key, encoder.encode(`${timestamp}.${rawBody}`));
  const expected = Array.from(new Uint8Array(signed)).map(b => b.toString(16).padStart(2, '0')).join('');

  // Timing-safe comparison
  if (expected.length !== signature.length) return false;
  let mismatch = 0;
  for (let i = 0; i < expected.length; i++) {
    mismatch |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  }
  return mismatch === 0;
}

export async function onRequestPost(context) {
  const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
  const WEBHOOK_SECRET = context.env.STRIPE_WEBHOOK_SECRET;
  const KV = context.env.REPLOT_REPORTS;

  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  if (!STRIPE_SK) return json({ error: 'Stripe not configured' }, 500);

  try {
    const rawBody = await context.request.text();
    let event;

    // Verify webhook signature (REQUIRED in production)
    if (WEBHOOK_SECRET) {
      const sig = context.request.headers.get('stripe-signature');
      if (!sig) return json({ error: 'No signature' }, 400);

      const valid = await verifyStripeSignature(rawBody, sig, WEBHOOK_SECRET);
      if (!valid) return json({ error: 'Invalid signature' }, 401);

      event = JSON.parse(rawBody);
    } else {
      // WEBHOOK_SECRET not set — reject in production
      return json({ error: 'Webhook secret not configured' }, 500);
    }

    const type = event.type;

    // ── checkout.session.completed ──
    if (type === 'checkout.session.completed') {
      const session = event.data.object;
      const email = session.customer_details?.email || session.customer_email || '';

      if (!email) return json({ received: true, skipped: 'no_email' });

      const plan = detectPlan(session);

      if (KV) {
        const code = await ensureAccessCode(KV, email, plan);

        // Update user account if exists (link plan to account)
        try {
          const normalEmail = email.toLowerCase().trim();
          const userRaw = await KV.get(`user:${normalEmail}`);
          if (userRaw) {
            const user = JSON.parse(userRaw);
            user.plan = plan;
            user.access_code = code;
            user.updated_at = new Date().toISOString();
            await KV.put(`user:${normalEmail}`, JSON.stringify(user));
          }
        } catch {}

        // Add to active subscribers list for notifications
        try {
          const normalEmail = email.toLowerCase().trim();
          let subs = [];
          const subsRaw = await KV.get('subscribers:active');
          if (subsRaw) subs = JSON.parse(subsRaw);
          if (!subs.includes(normalEmail)) {
            subs.push(normalEmail);
            await KV.put('subscribers:active', JSON.stringify(subs));
          }
        } catch {}

        // Store webhook event for audit
        await KV.put(`webhook:${event.id}`, JSON.stringify({
          type, email, plan, code,
          amount: session.amount_total,
          processedAt: new Date().toISOString(),
        }), { expirationTtl: 90 * 86400 }); // keep 90 days

        // Send access code via SendGrid if configured
        const SENDGRID_KEY = context.env.SENDGRID_API_KEY;
        if (SENDGRID_KEY && code) {
          const planName = plan === 'signals' ? 'Alpha Signals' :
                          plan === 'autopilot' ? 'Alpha Autopilot' :
                          plan === 'academy' ? 'Alpha Academy' : 'iBitLabs';

          await fetch('https://api.sendgrid.com/v3/mail/send', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${SENDGRID_KEY}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              personalizations: [{ to: [{ email }] }],
              from: { email: 'alpha@ibitlabs.com', name: 'iBitLabs' },
              subject: `Your ${planName} Access Code`,
              content: [{
                type: 'text/plain',
                value: `Welcome to ${planName}!\n\nYour access code: ${code}\n\nGo to www.ibitlabs.com to get started.\n\nKeep this code safe — you'll need it to access your ${planName} features.\n\n— iBitLabs Team`,
              }],
            }),
          });
        }

        return json({ received: true, email, plan, code });
      }

      return json({ received: true, email, plan });
    }

    // ── customer.subscription.deleted ──
    if (type === 'customer.subscription.deleted') {
      const sub = event.data.object;
      const customerId = sub.customer;

      // Look up customer email
      if (STRIPE_SK && customerId) {
        const custRes = await fetch(`https://api.stripe.com/v1/customers/${customerId}`, {
          headers: { 'Authorization': `Bearer ${STRIPE_SK}` },
        });
        const customer = await custRes.json();
        const email = customer.email;

        if (email && KV) {
          // Mark autopilot as disconnected if registered
          const regRaw = await KV.get(`autopilot:${email.toLowerCase().trim()}`);
          if (regRaw) {
            const reg = JSON.parse(regRaw);
            reg.status = 'canceled';
            reg.canceledAt = new Date().toISOString();
            delete reg.cb_api_key_enc;
            delete reg.cb_api_secret_enc;
            await KV.put(`autopilot:${email.toLowerCase().trim()}`, JSON.stringify(reg));
          }
        }
      }

      return json({ received: true, type: 'subscription_deleted' });
    }

    // Unhandled event type
    return json({ received: true, type, unhandled: true });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
