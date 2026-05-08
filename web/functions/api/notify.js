// ═══════════════════════════════════════════════════════════════
// iBitLabs · notify.js · POST /api/notify
// Sends signal notifications to all active subscribers.
// Called by the Python Sniper when a new signal fires.
// Channels: Email (SendGrid) + Telegram (optional)
//
// Body: { secret, signal: { direction, price, stoch_rsi, time } }
// secret = NOTIFY_SECRET env var (prevents unauthorized calls)
// ═══════════════════════════════════════════════════════════════

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  const NOTIFY_SECRET = context.env.NOTIFY_SECRET;
  const SENDGRID_KEY = context.env.SENDGRID_API_KEY;
  const TELEGRAM_BOT = context.env.TELEGRAM_BOT_TOKEN;
  const TELEGRAM_CHAT = context.env.TELEGRAM_CHAT_ID;

  if (!KV) return json({ error: 'Service unavailable' }, 503);

  try {
    const body = await context.request.json();

    // Auth check
    if (NOTIFY_SECRET && body.secret !== NOTIFY_SECRET) {
      return json({ error: 'Unauthorized' }, 403);
    }

    const signal = body.signal;
    if (!signal || !signal.direction) {
      return json({ error: 'Signal data required' }, 400);
    }

    const results = { email: 0, telegram: false };

    // Build notification message
    const dir = signal.direction.toUpperCase();
    const emoji = dir === 'LONG' ? '🟢' : '🔴';
    const subject = `${emoji} iBitLabs: ${dir} Signal @ $${signal.price}`;
    const textBody = (
      `${emoji} ${dir} SIGNAL — SOL/USD\n\n` +
      `Price: $${signal.price}\n` +
      `StochRSI: ${signal.stoch_rsi}\n` +
      `Time: ${signal.time}\n\n` +
      `TP: $${dir === 'LONG' ? (signal.price * 1.015).toFixed(2) : (signal.price * 0.985).toFixed(2)}\n` +
      `SL: $${dir === 'LONG' ? (signal.price * 0.95).toFixed(2) : (signal.price * 1.05).toFixed(2)}\n\n` +
      `— iBitLabs Sniper\n` +
      `www.ibitlabs.com`
    );

    // 1. Email all active dashboard/autopilot subscribers
    if (SENDGRID_KEY) {
      // Get all subscribers from KV
      const emails = await _getActiveSubscribers(KV, context.env.STRIPE_SECRET_KEY);

      for (const email of emails) {
        try {
          await fetch('https://api.sendgrid.com/v3/mail/send', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${SENDGRID_KEY}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              personalizations: [{ to: [{ email }] }],
              from: { email: 'signals@ibitlabs.com', name: 'iBitLabs Signals' },
              subject,
              content: [{ type: 'text/plain', value: textBody }],
            }),
          });
          results.email++;
        } catch {}
      }
    }

    // 2. Telegram notification
    if (TELEGRAM_BOT && TELEGRAM_CHAT) {
      try {
        await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT}/sendMessage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: TELEGRAM_CHAT,
            text: textBody,
            parse_mode: 'HTML',
          }),
        });
        results.telegram = true;
      } catch {}
    }

    // 3. Store signal in KV for browser notification polling
    await KV.put('sniper:latest_signal', JSON.stringify({
      ...signal,
      notified_at: new Date().toISOString(),
      emails_sent: results.email,
    }), { expirationTtl: 3600 }); // expire after 1h

    return json({ success: true, results });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

async function _getActiveSubscribers(KV, STRIPE_SK) {
  // Method 1: Read from KV subscriber list
  const emails = new Set();

  try {
    const listRaw = await KV.get('subscribers:active');
    if (listRaw) {
      const list = JSON.parse(listRaw);
      list.forEach(e => emails.add(e));
    }
  } catch {}

  // Method 2: Check autopilot customers
  try {
    const apListRaw = await KV.get('autopilot:customers');
    if (apListRaw) {
      const apList = JSON.parse(apListRaw);
      apList.forEach(e => emails.add(e));
    }
  } catch {}

  return Array.from(emails);
}
