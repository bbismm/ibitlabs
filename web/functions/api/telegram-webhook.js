// ═══════════════════════════════════════════════════════════════
// iBitLabs · telegram-webhook.js · POST /api/telegram-webhook
// Receives Telegram Bot updates (webhook mode).
// Commands: /start, /status, access-code linking
// ═══════════════════════════════════════════════════════════════

const CORS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: CORS });

async function sendTelegram(token, chatId, text) {
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: 'Markdown',
    }),
  });
}

export async function onRequestPost(context) {
  const KV = context.env.REPLOT_REPORTS;
  const BOT_TOKEN = context.env.TELEGRAM_BOT_TOKEN;

  if (!KV || !BOT_TOKEN) return json({ error: 'Service unavailable' }, 503);

  try {
    const update = await context.request.json();
    const message = update.message;
    if (!message || !message.text) return json({ ok: true });

    const chatId = message.chat.id;
    const username = message.from?.username || '';
    const text = message.text.trim();

    // /start — Welcome message
    if (text === '/start') {
      await sendTelegram(BOT_TOKEN, chatId,
        `Welcome to *iBitLabs Sniper*! 🎯\n\n` +
        `To connect your account, send your access code.\n` +
        `It looks like: \`BA-XXXXXXXX\`\n\n` +
        `You can find it on your [Account page](https://ibitlabs.com/account).\n\n` +
        `Commands:\n` +
        `/start — This message\n` +
        `/status — Current signal status`
      );
      return json({ ok: true });
    }

    // /status — Current signal status
    if (text === '/status') {
      let statusMsg = 'No active signal status available.';
      try {
        const raw = await KV.get('sniper:paid_status');
        if (raw) {
          const s = JSON.parse(raw);
          statusMsg = `*Sniper Status*\n\n` +
            `Direction: ${s.direction || 'N/A'}\n` +
            `Price: $${s.price || 'N/A'}\n` +
            `StochRSI: ${s.stoch_rsi || 'N/A'}\n` +
            `Updated: ${s.time || s.updated_at || 'N/A'}`;
        }
      } catch {}
      await sendTelegram(BOT_TOKEN, chatId, statusMsg);
      return json({ ok: true });
    }

    // Access code pattern: BA-XXXXXXXX
    if (/^BA-[A-Z0-9]{6,12}$/i.test(text.toUpperCase())) {
      const code = text.toUpperCase();
      const codeRaw = await KV.get(`code:${code}`);

      if (!codeRaw) {
        await sendTelegram(BOT_TOKEN, chatId,
          `Invalid access code. Please check and try again.\n\nYour code is on your [Account page](https://ibitlabs.com/account).`
        );
        return json({ ok: true });
      }

      const codeData = JSON.parse(codeRaw);
      const email = codeData.email;

      if (!email) {
        await sendTelegram(BOT_TOKEN, chatId, `Error: No email linked to this code.`);
        return json({ ok: true });
      }

      // Check if this account already has a Telegram connected
      const existingTg = await KV.get(`telegram:${email}`);
      if (existingTg) {
        const existing = JSON.parse(existingTg);
        if (existing.chat_id && existing.chat_id !== chatId) {
          await sendTelegram(BOT_TOKEN, chatId,
            `This access code is already linked to another Telegram account.\n\n` +
            `Each code can only be connected to one Telegram. ` +
            `If you need to reconnect, go to your [Account page](https://www.ibitlabs.com/account) and disconnect first.`
          );
          return json({ ok: true });
        }
      }

      // Store telegram connection (both directions)
      await KV.put(`telegram:${email}`, JSON.stringify({
        chat_id: chatId,
        username,
        connected_at: new Date().toISOString(),
      }));
      await KV.put(`telegram_chat:${chatId}`, JSON.stringify({ email }));

      await sendTelegram(BOT_TOKEN, chatId,
        `Connected! ✅\n\n` +
        `Your Telegram is now linked to *${email}*.\n` +
        `You will receive trading signals here automatically.\n\n` +
        `Use /status to check the latest signal.`
      );
      return json({ ok: true });
    }

    // Unknown message — help text
    await sendTelegram(BOT_TOKEN, chatId,
      `I didn't understand that.\n\n` +
      `Send your *access code* (e.g. \`BA-XXXXXXXX\`) to connect your account,\n` +
      `or use /start or /status.`
    );
    return json({ ok: true });

  } catch (e) {
    return json({ error: e.message }, 500);
  }
}

export async function onRequestOptions() {
  return new Response(null, { status: 200, headers: CORS });
}
