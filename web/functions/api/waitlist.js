// Autopilot waitlist — stores email + plan in KV

export async function onRequestPost(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  try {
    const { email, plan } = await context.request.json();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return json({ error: 'Invalid email' }, 400);
    }

    const KV = context.env.REPLOT_REPORTS || context.env.REPLOT_INDEX;
    if (KV) {
      const key = `waitlist:${email.toLowerCase().trim()}`;
      await KV.put(key, JSON.stringify({
        email: email.toLowerCase().trim(),
        plan: plan || 'autopilot',
        joined_at: new Date().toISOString(),
      }));
    }

    return json({ success: true });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
