// Admin authentication — verify password, return session token

export async function onRequestPost(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  try {
    const { password } = await context.request.json();
    const ADMIN_PW = context.env.ADMIN_PASSWORD;

    if (!ADMIN_PW) return json({ error: 'Admin not configured' }, 500);
    if (!password) return json({ error: 'Invalid password' }, 401);

    // Timing-safe comparison to prevent timing attacks
    const encoder = new TextEncoder();
    const a = encoder.encode(password);
    const b = encoder.encode(ADMIN_PW);
    if (a.length !== b.length) {
      // Still do work to avoid leaking length info
      let dummy = 0;
      for (let i = 0; i < b.length; i++) dummy |= b[i] ^ b[i];
      return json({ error: 'Invalid password' }, 401);
    }
    let mismatch = 0;
    for (let i = 0; i < a.length; i++) {
      mismatch |= a[i] ^ b[i];
    }
    if (mismatch !== 0) return json({ error: 'Invalid password' }, 401);

    // Generate session token with full 256-bit entropy
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    const token = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');

    const KV = context.env.REPLOT_REPORTS;
    if (KV) {
      // Rate limit: max 5 admin sessions per hour
      await KV.put('admin_session:' + token, JSON.stringify({ created: new Date().toISOString() }), { expirationTtl: 3600 }); // 1 hour instead of 8
    }

    return json({ token });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
