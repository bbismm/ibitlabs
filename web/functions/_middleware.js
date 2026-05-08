// iBitLabs middleware — hostname routing + CORS + security headers
const ALLOWED_ORIGINS = [
  'https://ibitlabs.com',
  'https://www.ibitlabs.com',
];

function getAllowedOrigin(request) {
  const origin = request.headers.get('Origin') || '';
  if (ALLOWED_ORIGINS.includes(origin)) {
    return origin;
  }
  if (!origin) return null;
  return null;
}

// Security headers applied to ALL responses
const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-XSS-Protection': '1; mode=block',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'Content-Security-Policy': [
    "default-src 'self'",
    // script-src: self + inline + Stripe + Google Analytics (GA4) + Google Tag Manager
    "script-src 'self' 'unsafe-inline' https://js.stripe.com https://www.googletagmanager.com https://www.google-analytics.com https://ssl.google-analytics.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    // img-src already 'https:' so GA beacon pixels work
    "img-src 'self' data: https:",
    // connect-src: self + Stripe + GA4 collection endpoints
    "connect-src 'self' https://api.stripe.com https://www.google-analytics.com https://analytics.google.com https://stats.g.doubleclick.net https://region1.google-analytics.com",
    "frame-src https://js.stripe.com",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; '),
};

export async function onRequest(context) {
  const url = new URL(context.request.url);
  const hostname = url.hostname;
  const allowedOrigin = getAllowedOrigin(context.request);

  // CORS preflight
  if (context.request.method === 'OPTIONS') {
    const headers = {
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Max-Age': '86400',
      ...SECURITY_HEADERS,
    };
    if (allowedOrigin) headers['Access-Control-Allow-Origin'] = allowedOrigin;
    return new Response(null, { status: 200, headers });
  }

  // Redirect bare domain to www
  if (hostname === 'ibitlabs.com') {
    const wwwUrl = new URL(url.toString());
    wwwUrl.hostname = 'www.ibitlabs.com';
    return Response.redirect(wwwUrl.toString(), 301);
  }

  // Process request
  const response = await context.next();

  // Add CORS + security headers
  const newResponse = new Response(response.body, response);

  // Security headers on all responses
  for (const [key, value] of Object.entries(SECURITY_HEADERS)) {
    newResponse.headers.set(key, value);
  }

  // CORS: only allow specific origins (not *)
  if (allowedOrigin) {
    newResponse.headers.set('Access-Control-Allow-Origin', allowedOrigin);
    newResponse.headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    newResponse.headers.set('Vary', 'Origin');
  }
  // Remove any wildcard CORS set by individual endpoints
  if (newResponse.headers.get('Access-Control-Allow-Origin') === '*') {
    if (allowedOrigin) {
      newResponse.headers.set('Access-Control-Allow-Origin', allowedOrigin);
    } else {
      newResponse.headers.delete('Access-Control-Allow-Origin');
    }
  }

  return newResponse;
}
