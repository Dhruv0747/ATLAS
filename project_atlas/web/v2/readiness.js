/* 2026-11-15 ATLAS Autonomy Readiness page: every blocker, why, fix steps, a button to the test, and the
   dashboard-run Speed check. The server decides everything; a PASS clears the blocker by itself.
   2026-11-16 owner: dashboard text in English only. */
(function () {
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  async function post(path, body) {
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: JSON.stringify(body || {}) });
      const d = await r.json().catch(() => ({})); alert(d.message || ('request ' + r.status)); return d;
    } catch (e) { alert('CONTROL LINK LOST'); return {}; }
  }
  function render(d) {
    const bad = d.items.filter(i => !i.ok);
    const s = $('summary');
    if (d.mode === 'AUTONOMOUS') { s.textContent = d.ready_to_drive ? 'AUTONOMOUS mode ON — the rover can drive' : 'AUTONOMOUS mode ON — but the red items below will stop goals'; s.className = 'summary ' + (d.ready_to_drive ? 'ok' : 'warn'); }
    else if (d.ready_to_switch_on) { s.textContent = '✅ Autonomous mode can be switched on: enter the PIN in the Command center and press "Autonomous mode"'; s.className = 'summary ok'; }
    else { s.textContent = `❌ Autonomous mode cannot be switched on yet — ${bad.length} item${bad.length === 1 ? '' : 's'} to fix`; s.className = 'summary bad'; }
    $('items').innerHTML = d.items.map(i => {
      const a = i.action;
      const btn = !a ? '' : a.href ? `<a class="btn" href="${esc(a.href)}">${esc(a.label)}</a>` : `<button type="button" data-api="${esc(a.api)}">${esc(a.label)}</button>`;
      return `<div class="item ${i.ok ? 'ok' : 'bad'}"><h2>${i.ok ? '✅' : '❌'} ${esc(i.title)}</h2>
        <div class="why">${esc(i.why)}</div>${i.steps.length ? '<b>How to fix:</b><ol>' + i.steps.map(x => `<li>${esc(x)}</li>`).join('') + '</ol>' : ''}
        ${btn}<div class="unlock">${i.ok ? '' : 'Clears: ' + esc(i.unlocks_by)}</div></div>`;
    }).join('');
    const sp = d.speed || {};
    const running = d.speed_check_running;
    $('s015').disabled = running || !sp.enabled || !sp.tool_installed;
    $('speedState').textContent = !sp.enabled ? 'Closed-loop speed control is currently off.' : !sp.tool_installed ? 'The Speed check tool is not installed on the rover yet.'
      : running ? 'Speed check running… keep the remote ready (B = stop).'
      : `PASS: ${(sp.passed || []).filter(x => Math.abs(x - 0.15) < 0.005).length}/${sp.passes_needed || 2}` + ((sp.missing || []).length ? '' : ' ✅ unlocked');
    $('results').innerHTML = (sp.results || []).slice().reverse().map(r => `<div class="${r.verdict === 'PASS' ? 'pass' : 'fail'}">
      ${esc(Number(r.requested_mps || r.target_mps).toFixed(2))} m/s (rover target ${esc(Number(r.target_mps).toFixed(3))}) → ${esc(r.verdict)} • mean ${r.steady_mean_mps == null ? '—' : Number(r.steady_mean_mps).toFixed(3)} • peak ${r.peak_mps == null ? '—' : Number(r.peak_mps).toFixed(3)} • ${esc(r.end_reason)}${r.failed_checks && r.failed_checks.length ? ' • fail: ' + esc(r.failed_checks.join(', ')) : ''}</div>`).join('');
  }
  async function poll() {
    if (document.hidden) return;
    try { render(await fetch('/api/readiness', { cache: 'no-store' }).then(r => r.json())); } catch (e) { $('summary').textContent = 'Cannot reach the rover'; $('summary').className = 'summary bad'; }
    try {
      const s = await fetch('/api/readiness/speedcheck', { cache: 'no-store' }).then(r => r.json());
      $('log').hidden = !s.log; $('log').textContent = s.log || '';
    } catch (e) { /* keep last */ }
  }
  $('items').onclick = async e => { const b = e.target.closest('[data-api]'); if (b) { await post(b.dataset.api, {}); setTimeout(poll, 1500); } };
  for (const [id, v] of [['s015', 0.15]]) {
    $(id).onclick = async () => {
      if (!confirm(`Start Speed check at ${v.toFixed(2)} m/s?\n\nThe rover will drive ~0.6 m forward by itself. Is 1.5 m ahead clear? Is the remote in your hand?`)) return;
      await post('/api/readiness/speedcheck', { speed: v, pin: $('pin').value }); $('pin').value = ''; setTimeout(poll, 800);
    };
  }
  setInterval(poll, 1500); poll();
})();
