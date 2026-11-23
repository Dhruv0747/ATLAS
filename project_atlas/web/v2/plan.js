/* ATLAS master-plan progress board (2026-11-23). Read-only: GET /api/master_plan every 5 s. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cls = s => String(s || '').startsWith('PASS') ? 'PASS' : String(s || '').replace(/ /g, '_');

  function render(d) {
    const n = d.next_step || {};
    $('next').innerHTML = `<b>Next step</b><br>${esc(n.text)}` + (n.href ? `<br><a href="${esc(n.href)}">${esc(n.label || 'Open')}</a>` : '');
    $('gcount').textContent = `· ${d.gate_done}/${d.gate_total} done`;
    $('gbar').style.width = (100 * d.gate_done / Math.max(1, d.gate_total)) + '%';
    $('gate').innerHTML = (d.gate || []).map(g => {
      const hist = g.history && g.history.length ? `<table>${g.history.slice().reverse().map(h =>
        `<tr><td>${esc(h.when)}</td><td>${esc(h.verdict)} ${esc(h.score || '')}</td><td>${esc(h.note || (h.failed && h.failed.length ? 'failed: ' + h.failed.join(', ') : ''))}</td></tr>`).join('')}</table>` : '';
      const passed = String(g.status).startsWith('PASS');
      const btn = !g.tool ? '' : g.locked ? `<button class="tool" disabled>🔒 ${esc(g.tool.label)} · after stage ${esc(g.unlock_after)} passes</button>`
        : `<a class="tool" href="${esc(g.tool.href)}">${passed ? 'Run again: ' : ''}${esc(g.tool.label)}</a>`;
      const how = (passed || g.locked ? '' : `<ol>${(g.how || []).map(s => `<li>${esc(s)}</li>`).join('')}</ol>`) + btn;
      return `<div class="card"><span class="st ${cls(g.status)}">${esc(g.status)}</span><b>Stage ${g.n} · ${esc(g.title)}</b>` +
        `<div class="goal">${esc(g.goal)}</div><div class="ev">Evidence: ${esc(g.evidence)}</div>${how}${hist}</div>`;
    }).join('');
    $('later').innerHTML = (d.later || []).map(l => `<div class="later"><span class="st ${cls(l.status)}">${esc(l.status)}</span>` +
      `<b>${l.n}. ${esc(l.title)}</b><div class="ev">${esc(l.what)}</div>` +
      (l.status === 'LOCKED' ? `<button class="tool" disabled>🔒 Unlocks after ${esc(l.unlock_after)}</button>`
        : `<button class="tool" disabled>Needs a developer session — no owner test yet</button>`) + `</div>`).join('');
    $('note').textContent = (d.note || '') + ' Plan: ' + (d.source || '');
  }

  async function poll() {
    try { const r = await fetch('/api/master_plan', { cache: 'no-store', signal: AbortSignal.timeout(4000) }); render(await r.json()); }
    catch (e) { $('next').textContent = 'Lost contact with ATLAS: ' + e.message; }
  }
  setInterval(poll, 5000); poll();
})();
