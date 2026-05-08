// ═══════════════════════════════════════════════════════════════
// iBitLabs · rss.js · GET /api/rss
// Generates an RSS 2.0 feed from the essays API.
// Fetches /api/essays internally and converts to XML.
// ═══════════════════════════════════════════════════════════════

const CACHE_SECONDS = 600;

function escXml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function stripHtml(html) {
  return String(html ?? '').replace(/<[^>]*>/g, '').trim().slice(0, 300);
}

export async function onRequestGet(context) {
  try {
    // Fetch essays from our own API
    const origin = new URL(context.request.url).origin;
    const res = await fetch(`${origin}/api/essays`);
    if (!res.ok) throw new Error('Essays API returned ' + res.status);
    const essays = await res.json();

    const items = essays.map(e => {
      const link = `https://www.ibitlabs.com/essays#${e.slug}`;
      const pubDate = new Date(e.date + 'T12:00:00Z').toUTCString();
      const desc = stripHtml(e.body);
      return `    <item>
      <title>${escXml(e.title)}</title>
      <link>${link}</link>
      <guid isPermaLink="true">${link}</guid>
      <pubDate>${pubDate}</pubDate>
      <description>${escXml(desc)}</description>
      <author>bonny@ibitlabs.com (Bonnybb)</author>
    </item>`;
    }).join('\n');

    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>iBitLabs Essays</title>
    <link>https://www.ibitlabs.com/essays</link>
    <description>Long-form writing from the iBitLabs experiment — AI-built trading, strategy breakdowns, and lessons from shipping a live trading bot as a non-coder.</description>
    <language>en-us</language>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
    <atom:link href="https://www.ibitlabs.com/api/rss" rel="self" type="application/rss+xml"/>
${items}
  </channel>
</rss>`;

    return new Response(xml, {
      status: 200,
      headers: {
        'Content-Type': 'application/rss+xml; charset=utf-8',
        'Cache-Control': `public, max-age=${CACHE_SECONDS}, s-maxage=${CACHE_SECONDS}`,
      },
    });
  } catch (e) {
    return new Response(`<!-- RSS error: ${e.message} -->`, {
      status: 503,
      headers: { 'Content-Type': 'application/xml' },
    });
  }
}
