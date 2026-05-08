// BIBSUS Alpha · get-access-code.js
// Returns the access code for an active subscriber (by email)

export async function onRequestGet(context) {
  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

  const url = new URL(context.request.url);
  const email = url.searchParams.get('email');

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return json({ error: 'Valid email required' }, 400);
  }

  const normalEmail = email.toLowerCase().trim();
  const KV = context.env.REPLOT_REPORTS;

  if (!KV) {
    return json({ error: 'Service unavailable' }, 503);
  }

  try {
    const accessRaw = await KV.get(`access:${normalEmail}`);
    if (!accessRaw) {
      return json({ error: 'No access code found. Complete payment first.' }, 404);
    }

    const accessData = JSON.parse(accessRaw);
    return json({
      code: accessData.code,
      plan: accessData.plan,
      email: normalEmail,
      createdAt: accessData.createdAt,
    });
  } catch (e) {
    return json({ error: e.message }, 500);
  }
}
