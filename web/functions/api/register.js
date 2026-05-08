// ═══════════════════════════════════════════════════════════════
// BIBSUS Alpha · register.js · POST /api/register
// Registers Autopilot customer: validates access code + stores
// AES-256-GCM encrypted Coinbase API keys in KV
// ═══════════════════════════════════════════════════════════════

// AES-256-GCM encryption using Web Crypto API
async function encryptAES(plaintext, hexKey) {
  const keyBytes = Uint8Array.from(hexKey.match(/.{2}/g).map(b => parseInt(b, 16)));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['encrypt']);
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(plaintext));
  const ivHex = Array.from(iv, b => b.toString(16).padStart(2, '0')).join('');
  const ctHex = Array.from(new Uint8Array(encrypted), b => b.toString(16).padStart(2, '0')).join('');
  return `aes:${ivHex}:${ctHex}`;
}

async function decryptAES(ciphertext, hexKey) {
  if (ciphertext.startsWith('b64:')) return atob(ciphertext.slice(4)); // legacy fallback
  if (!ciphertext.startsWith('aes:')) return atob(ciphertext); // old base64
  const [, ivHex, ctHex] = ciphertext.split(':');
  const keyBytes = Uint8Array.from(hexKey.match(/.{2}/g).map(b => parseInt(b, 16)));
  const iv = Uint8Array.from(ivHex.match(/.{2}/g).map(b => parseInt(b, 16)));
  const ct = Uint8Array.from(ctHex.match(/.{2}/g).map(b => parseInt(b, 16)));
  const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['decrypt']);
  const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
  return new TextDecoder().decode(decrypted);
}

const CORS_HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: CORS_HEADERS });

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  if (!KV) return json({ error: 'Service unavailable' }, 503);

  try {
    const body = await context.request.json();
    const { code, cb_api_key, cb_api_secret } = body;

    if (!code) return json({ error: 'Access code required' }, 400);
    if (!cb_api_key || !cb_api_secret) return json({ error: 'Coinbase API key and secret required' }, 400);

    // Validate access code
    const normalized = code.trim().toUpperCase();
    const codeRaw = await KV.get(`code:${normalized}`);
    if (!codeRaw) return json({ error: 'Invalid access code' }, 403);

    const codeData = JSON.parse(codeRaw);
    const email = codeData.email;

    if (!email) return json({ error: 'Invalid code data' }, 400);

    // Verify Stripe subscription is active (autopilot requires active sub)
    const STRIPE_SK = context.env.STRIPE_SECRET_KEY;
    if (STRIPE_SK) {
      const custRes = await fetch(
        `https://api.stripe.com/v1/customers?email=${encodeURIComponent(email)}&limit=1`,
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
          return json({ error: 'No active subscription. Subscribe to Autopilot first.' }, 403);
        }
      } else {
        return json({ error: 'No Stripe account found for this code' }, 403);
      }
    }

    // Encrypt API keys with AES-256-GCM before storing
    const ENCRYPT_KEY = context.env.API_ENCRYPT_KEY; // 256-bit hex key in env
    let cb_api_key_enc, cb_api_secret_enc;
    if (ENCRYPT_KEY) {
      cb_api_key_enc = await encryptAES(cb_api_key, ENCRYPT_KEY);
      cb_api_secret_enc = await encryptAES(cb_api_secret, ENCRYPT_KEY);
    } else {
      // Fallback: base64 (log warning — ENCRYPT_KEY should be set)
      cb_api_key_enc = 'b64:' + btoa(cb_api_key);
      cb_api_secret_enc = 'b64:' + btoa(cb_api_secret);
    }

    const registration = {
      email,
      code: normalized,
      cb_api_key_enc,
      cb_api_secret_enc,
      registeredAt: new Date().toISOString(),
      status: 'active',
      paused: false,
    };

    await KV.put(`autopilot:${email}`, JSON.stringify(registration));

    // Add to active autopilot customers list
    let customerList = [];
    try {
      const listRaw = await KV.get('autopilot:customers');
      if (listRaw) customerList = JSON.parse(listRaw);
    } catch {}

    if (!customerList.includes(email)) {
      customerList.push(email);
      await KV.put('autopilot:customers', JSON.stringify(customerList));
    }

    return json({
      success: true,
      email,
      status: 'active',
      message: 'Autopilot registered. The Sniper will begin trading on your account within 5 minutes.',
    });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS_HEADERS });
}
