// ═══════════════════════════════════════════════════════════════
// Replot AI · save-email.js · Email Collection Endpoint
// Stores emails in Cloudflare KV for later marketing use
// ═══════════════════════════════════════════════════════════════

export async function onRequestPost(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });

  try {
    const { email, source } = await context.request.json();

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return json({ error: 'Invalid email' }, 400);
    }

    const KV = context.env.REPLOT_INDEX;
    if (!KV) {
      // Gracefully handle missing KV — still return success to user
      console.log(`EMAIL_CAPTURE: ${email} from ${source || 'unknown'} (KV not configured)`);
      return json({ success: true });
    }

    // Store email with metadata
    const key = `email:${email.toLowerCase().trim()}`;
    const existing = await KV.get(key);

    if (existing) {
      // Already captured — update last seen
      const data = JSON.parse(existing);
      data.last_seen = new Date().toISOString();
      data.visits = (data.visits || 1) + 1;
      if (source && !data.sources.includes(source)) data.sources.push(source);
      await KV.put(key, JSON.stringify(data));
    } else {
      // New email
      await KV.put(key, JSON.stringify({
        email: email.toLowerCase().trim(),
        sources: [source || 'unknown'],
        captured_at: new Date().toISOString(),
        last_seen: new Date().toISOString(),
        visits: 1,
      }));

      // Update email count
      const countStr = await KV.get('email_count') || '0';
      await KV.put('email_count', String(parseInt(countStr) + 1));
    }

    return json({ success: true });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
