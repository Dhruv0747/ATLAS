/* ATLAS Home (2026-11-28): "Next step" banner + "Why isn't ATLAS moving?" card.
 * Read-only: GET /api/why every 1.5 s while the page is visible. It sends nothing and adds no control action;
 * the only links open existing pages. */
(function () {
  'use strict';
  const box = document.getElementById('hmGuide');
  if (!box) return;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const LABEL = { ok: 'OK', wait: 'YOUR TURN', stop: 'STOPPED', unknown: 'NO DATA' };
  box.innerHTML =
    '<div class="hg-next" id="hgNext" hidden><span class="hg-k">Next step</span><span class="hg-t" id="hgNextText"></span>' +
    '<a class="hg-btn" id="hgNextBtn" hidden></a></div>' +
    '<div class="hg-why" id="hgWhy" data-level="unknown" role="status" aria-live="polite">' +
    '<span class="hg-badge" id="hgBadge">…</span><div class="hg-body"><div class="hg-title" id="hgTitle">Checking ATLAS…</div>' +
    '<div class="hg-fix" id="hgFix"></div><details class="hg-more" id="hgMore" hidden><summary>Details</summary>' +
    '<div id="hgDetail"></div></details></div></div>';
  const $ = id => document.getElementById(id);
  let last = '';

  function render(d) {
    const w = d.why || { level: 'unknown', title: 'No live safety data from ATLAS.' };
    const key = JSON.stringify(d);
    if (key === last) return;
    last = key;
    $('hgWhy').dataset.level = w.level;
    $('hgBadge').textContent = LABEL[w.level] || '…';
    $('hgTitle').textContent = w.title || '';
    $('hgFix').textContent = w.fix ? 'What to do: ' + w.fix : '';
    const det = [w.detail, w.source ? 'Source: ' + w.source : ''].filter(Boolean).join(' · ');
    $('hgMore').hidden = !w.detail;
    $('hgDetail').textContent = det;
    const n = d.next;
    $('hgNext').hidden = !(n && n.text);
    if (n && n.text) {
      $('hgNextText').textContent = n.text;
      const b = $('hgNextBtn');
      b.hidden = !n.href;
      if (n.href) { b.href = n.href; b.textContent = (n.label || 'Open') + ' →'; }
    }
  }

  let busy = false;
  async function poll() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const r = await fetch('/api/why', { cache: 'no-store', signal: AbortSignal.timeout(3000) });
      render(await r.json());
    } catch (e) {
      render({ why: { level: 'unknown', title: 'Lost contact with ATLAS.', fix: 'Check Wi-Fi and that ATLAS is on.' } });
    } finally { busy = false; }
  }
  setInterval(poll, 1500);
  document.addEventListener('visibilitychange', poll);
  poll();
})();
