// GET /api/auth/google/callback — Handle Google OAuth callback
import { normalizeEmail, createSession } from '../_crypto.js';

export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');

  const clientId = context.env.GOOGLE_CLIENT_ID;
  const clientSecret = context.env.GOOGLE_CLIENT_SECRET;
  const KV = context.env.REPLOT_REPORTS;
  const redirectUri = `${url.origin}/api/auth/google/callback`;

  // Error or user denied
  if (error || !code) {
    return Response.redirect(`${url.origin}/login?error=oauth_denied`, 302);
  }

  if (!clientId || !clientSecret || !KV) {
    return Response.redirect(`${url.origin}/login?error=oauth_config`, 302);
  }

  // Verify CSRF state
  let savedState = null;
  if (state) {
    try {
      const raw = await KV.get(`oauth_state:${state}`);
      if (raw) {
        savedState = JSON.parse(raw);
        await KV.delete(`oauth_state:${state}`);
      }
    } catch {}
  }
  if (!savedState) {
    return Response.redirect(`${url.origin}/login?error=invalid_state`, 302);
  }

  try {
    // Exchange code for tokens
    const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri,
        grant_type: 'authorization_code',
      }),
    });
    const tokens = await tokenRes.json();

    if (!tokens.access_token) {
      return Response.redirect(`${url.origin}/login?error=token_exchange`, 302);
    }

    // Get user info from Google
    const userRes = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    const googleUser = await userRes.json();

    if (!googleUser.email) {
      return Response.redirect(`${url.origin}/login?error=no_email`, 302);
    }

    const email = normalizeEmail(googleUser.email);

    // Find or create user
    let user = null;
    const userRaw = await KV.get(`user:${email}`);

    if (userRaw) {
      // Existing user — update last login
      user = JSON.parse(userRaw);
      user.last_login = new Date().toISOString();
      if (googleUser.name && !user.name) user.name = googleUser.name;
      if (googleUser.picture && !user.picture) user.picture = googleUser.picture;
      await KV.put(`user:${email}`, JSON.stringify(user));
    } else {
      // New user — create account
      let plan = 'free';
      let accessCode = null;

      // Check if they already paid via Stripe before registering
      try {
        const accessRaw = await KV.get(`access:${email}`);
        if (accessRaw) {
          const accessData = JSON.parse(accessRaw);
          plan = accessData.plan || 'free';
          accessCode = accessData.code;
        }
      } catch {}

      user = {
        email,
        name: googleUser.name || '',
        picture: googleUser.picture || '',
        auth_provider: 'google',
        plan,
        status: 'active',
        access_code: accessCode,
        created_at: new Date().toISOString(),
        last_login: new Date().toISOString(),
      };
      await KV.put(`user:${email}`, JSON.stringify(user));
    }

    // Create session
    const token = await createSession(KV, email, user.plan || 'free');

    // Redirect to frontend with token (frontend saves it to localStorage)
    let redirectPath = savedState.redirect || '';
    if (!redirectPath || !redirectPath.startsWith('/') || redirectPath.startsWith('//')) {
      redirectPath = user.plan !== 'free' ? '/signals' : '/account';
    }

    // Pass token via URL fragment (not query param — fragments aren't sent to server)
    return Response.redirect(`${url.origin}${redirectPath}#token=${token}`, 302);
  } catch (e) {
    return Response.redirect(`${url.origin}/login?error=oauth_failed`, 302);
  }
}
