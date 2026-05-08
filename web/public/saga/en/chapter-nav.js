// chapter-nav.js — injects a top + bottom nav into each chapter page so the
// reading experience stays inside iBitLabs (TOC, prev/next, progress).
// Loaded on every chapter-NN.html and prologue.html via a single <script>
// tag at the bottom of the file.
(function () {
  'use strict';

  const TOTAL = 19;
  const path = location.pathname.split('/').pop() || '';
  const m = path.match(/chapter-(\d{2})\.html/);
  const isProlog = /prologue/.test(path);
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
    return; // not a chapter page
  }

  const top = document.createElement('div');
  top.className = 'chap-nav';
  top.innerHTML = `
    ${prev ? `<a href="${prev}" rel="prev">← Prev</a>` : `<span class="chap-disabled">← Prev</span>`}
    <a class="chap-toc" href="./">${label}</a>
    ${next ? `<a href="${next}" rel="next">Next →</a>` : `<span class="chap-disabled">Next →</span>`}
  `;
  document.body.insertBefore(top, document.body.firstChild);

  const bot = document.createElement('div');
  bot.className = 'chap-foot';
  bot.innerHTML = `
    ${prev ? `<a href="${prev}">← ${isProlog ? '' : (n === 1 ? 'Prologue' : 'Previous chapter')}</a>` : `<span class="chap-foot-spacer"></span>`}
    <a href="./">All chapters</a>
    ${next ? `<a href="${next}">${isProlog ? 'Chapter 1 →' : (n < TOTAL ? 'Next chapter →' : '')}</a>` : `<span class="chap-foot-spacer"></span>`}
  `;
  // append at end of body so it sits under the prose
  document.body.appendChild(bot);
})();
