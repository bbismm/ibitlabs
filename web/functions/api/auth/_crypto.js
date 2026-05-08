// ═══════════════════════════════════════════════════════════════
// iBitLabs · _crypto.js · Password hashing & session tokens
// Uses Web Crypto API (native to Cloudflare Workers, zero deps)
// ═══════════════════════════════════════════════════════════════

export async function hashPassword(password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits']
  );
  const hash = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' }, key, 256
  );
  const saltB64 = btoa(String.fromCharCode(...salt));
  const hashB64 = btoa(String.fromCharCode(...new Uint8Array(hash)));
  return `${saltB64}:${hashB64}`;
}

export async function verifyPassword(password, stored) {
  const [saltB64, hashB64] = stored.split(':');
  if (!saltB64 || !hashB64) return false;
  const salt = Uint8Array.from(atob(saltB64), c => c.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits']
  );
  const hash = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' }, key, 256
  );
  // Timing-safe comparison to prevent timing attacks
  const computed = btoa(String.fromCharCode(...new Uint8Array(hash)));
  if (computed.length !== hashB64.length) return false;
  let mismatch = 0;
  for (let i = 0; i < computed.length; i++) {
    mismatch |= computed.charCodeAt(i) ^ hashB64.charCodeAt(i);
  }
  return mismatch === 0;
}

export function generateToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

export function normalizeEmail(email) {
  return (email || '').toLowerCase().trim();
}

export function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

const SESSION_TTL = 7 * 24 * 3600; // 7 days

export async function createSession(KV, email, plan) {
  const token = generateToken();
  await KV.put(`session:${token}`, JSON.stringify({
    email: normalizeEmail(email),
    plan: plan || 'free',
    created_at: new Date().toISOString(),
  }), { expirationTtl: SESSION_TTL });
  return token;
}

export async function getSession(KV, token) {
  if (!token) return null;
  try {
    const raw = await KV.get(`session:${token}`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export async function deleteSession(KV, token) {
  if (token) await KV.delete(`session:${token}`);
}

export function getTokenFromRequest(request) {
  const auth = request.headers.get('Authorization') || '';
  if (auth.startsWith('Bearer ')) return auth.slice(7);
  // Also check cookie
  const cookies = request.headers.get('Cookie') || '';
  const match = cookies.match(/ibl_token=([a-f0-9]+)/);
  return match ? match[1] : null;
}

export const CORS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

export const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: CORS });
