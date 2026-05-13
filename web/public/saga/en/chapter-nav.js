// chapter-nav.js — injects a top site-bar on every page, plus chapter
// prev/next/TOC navigation on chapter-NN.html and prologue.html.
// Loaded via a single <script src="chapter-nav.js" defer> tag near </body>.
(function () {
  'use strict';

  // ── 1. Site-bar (always shown) ──────────────────────────────────────
  const siteBar = document.createElement('nav');
  siteBar.className = 'site-bar';
  siteBar.innerHTML = `
    <a href="/" class="site-bar-brand"><b>iBitLabs</b></a>
    <div class="site-bar-links">
      <a href="/signals">Signals</a>
      <a href="/lab">Lab</a>
      <a href="/office">Office</a>
      <a href="/writing" class="active">Writing</a>
      <a href="/contributors">Contributors</a>
    </div>
  `;
  document.body.insertBefore(siteBar, document.body.firstChild);

  // ── 2. Chapter nav (chapter / prologue only) ────────────────────────
  const TOTAL = 19;
  const path = location.pathname.split('/').pop() || '';
  const m = path.match(/chapter-(\d{2})(?:\.html)?$/);
  const isProlog = /^prologue(?:\.html)?$/.test(path);
  const n = m ? parseInt(m[1], 10) : null;

  let prev = null, next = null, label = '';
  if (isProlog) {
    label = 'Prologue';
    next = 'chapter-01.html';
  } else if (n !== null) {
    label = `Chapter ${n} / ${TOTAL}`;
    prev = (n === 1) ? 'prologue.html' : `chapter-${String(n - 1).padStart(2, '0')}.html`;
    next = (n < TOTAL) ? `chapter-${String(n + 1).padStart(2, '0')}.html` : null;
  } else {
    return; // not a chapter page — site-bar is enough
  }

  const top = document.createElement('div');
  top.className = 'chap-nav';
  top.innerHTML = `
    ${prev ? `<a href="${prev}" rel="prev">← Prev</a>` : `<span class="chap-disabled">← Prev</span>`}
    <a class="chap-toc" href="./">${label}</a>
    ${next ? `<a href="${next}" rel="next">Next →</a>` : `<span class="chap-disabled">Next →</span>`}
  `;
  // Site-bar is firstChild now; insert top chap-nav right after it.
  siteBar.insertAdjacentElement('afterend', top);

  const bot = document.createElement('div');
  bot.className = 'chap-foot';
  bot.innerHTML = `
    ${prev ? `<a href="${prev}">← ${isProlog ? '' : (n === 1 ? 'Prologue' : 'Previous chapter')}</a>` : `<span class="chap-foot-spacer"></span>`}
    <a href="./">All chapters</a>
    ${next ? `<a href="${next}">${isProlog ? 'Chapter 1 →' : (n < TOTAL ? 'Next chapter →' : '')}</a>` : `<span class="chap-foot-spacer"></span>`}
  `;
  document.body.appendChild(bot);
})();
