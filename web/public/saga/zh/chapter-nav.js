// chapter-nav.js (zh) — Chinese-locale chapter navigation.
// Same shape as /saga/en/chapter-nav.js but localized labels.
(function () {
  'use strict';

  const TOTAL = 19;
  const path = location.pathname.split('/').pop() || '';
  const m = path.match(/chapter-(\d{2})\.html/);
  const isProlog = /prologue/.test(path);
  const n = m ? parseInt(m[1], 10) : null;

  let prev = null, next = null, label = '';
  if (isProlog) {
    label = '序章';
    next = 'chapter-01.html';
  } else if (n !== null) {
    label = `第 ${n} 章 / 共 ${TOTAL}`;
    prev = (n === 1) ? 'prologue.html' : `chapter-${String(n - 1).padStart(2, '0')}.html`;
    next = (n < TOTAL) ? `chapter-${String(n + 1).padStart(2, '0')}.html` : null;
  } else {
    return;
  }

  const top = document.createElement('div');
  top.className = 'chap-nav';
  top.innerHTML = `
    ${prev ? `<a href="${prev}" rel="prev">← 上一章</a>` : `<span class="chap-disabled">← 上一章</span>`}
    <a class="chap-toc" href="./">${label}</a>
    ${next ? `<a href="${next}" rel="next">下一章 →</a>` : `<span class="chap-disabled">下一章 →</span>`}
  `;
  document.body.insertBefore(top, document.body.firstChild);

  const bot = document.createElement('div');
  bot.className = 'chap-foot';
  bot.innerHTML = `
    ${prev ? `<a href="${prev}">← ${isProlog ? '' : (n === 1 ? '序章' : '上一章')}</a>` : `<span class="chap-foot-spacer"></span>`}
    <a href="./">全部章节</a>
    ${next ? `<a href="${next}">${isProlog ? '第 1 章 →' : (n < TOTAL ? '下一章 →' : '')}</a>` : `<span class="chap-foot-spacer"></span>`}
  `;
  document.body.appendChild(bot);
})();
