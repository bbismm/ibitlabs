// ═══════════════════════════════════════════════════════════════
// Replot AI · env-test.js · Cloudflare Pages Function
// ═══════════════════════════════════════════════════════════════

export async function onRequestGet(context) {
  // Only allow in development (localhost / preview deploys)
  const url = new URL(context.request.url);
  const host = url.hostname;
  if (host !== 'localhost' && host !== '127.0.0.1' && !host.endsWith('.pages.dev')) {
    return new Response(JSON.stringify({ error: 'Not available in production' }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const env = context.env;
  const data = {
    hasHudToken: !!env.HUD_API_TOKEN,
    hasRapidKey: !!env.RAPIDAPI_KEY,
    hasAnthropicKey: !!env.ANTHROPIC_API_KEY,
    hasStripeKey: !!env.STRIPE_SECRET_KEY,
    runtime: 'cloudflare-pages',
  };

  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
