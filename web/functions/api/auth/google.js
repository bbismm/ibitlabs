// GET /api/auth/google — Redirect to Google OAuth consent screen
export async function onRequestGet(context) {
  const clientId = context.env.GOOGLE_CLIENT_ID;
  if (!clientId) {
    return new Response(JSON.stringify({ error: 'Google OAuth not configured' }), {
      status: 500, headers: { 'Content-Type': 'application/json' },
    });
  }

  const url = new URL(context.request.url);
  const redirectUri = `${url.origin}/api/auth/google/callback`;

  // Save redirect destination if provided
  const redirect = url.searchParams.get('redirect') || '';

  // Generate state token to prevent CSRF
  const stateBytes = crypto.getRandomValues(new Uint8Array(16));
  const state = Array.from(stateBytes, b => b.toString(16).padStart(2, '0')).join('');

  // Store state in KV with short TTL (10 min)
  const KV = context.env.REPLOT_REPORTS;
  if (KV) {
    await KV.put(`oauth_state:${state}`, JSON.stringify({ redirect }), { expirationTtl: 600 });
  }

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: 'openid email profile',
    state,
    access_type: 'online',
    prompt: 'select_account',
  });

  return Response.redirect(`https://accounts.google.com/o/oauth2/v2/auth?${params}`, 302);
}
