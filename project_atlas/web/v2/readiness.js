/* 2026-11-15 ATLAS Autonomy Readiness page: every blocker, why, Hindi fix steps, a button to the test, and the
   dashboard-run Speed check. The server decides everything; a PASS clears the blocker by itself. */
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
    if (d.mode === 'AUTONOMOUS') { s.textContent = d.ready_to_drive ? 'AUTONOMOUS mode चालू — rover चल सकता है' : 'AUTONOMOUS mode चालू — पर नीचे की लाल चीज़ें goal रोकेंगी'; s.className = 'summary ' + (d.ready_to_drive ? 'ok' : 'warn'); }
    else if (d.ready_to_switch_on) { s.textContent = '✅ Autonomous mode चालू कर सकते हैं: Command center में PIN डालकर "Autonomous mode" दबाएँ'; s.className = 'summary ok'; }
    else { s.textContent = `❌ Autonomous mode अभी नहीं खुलेगा — ${bad.length} चीज़ ठीक करनी है`; s.className = 'summary bad'; }
    $('items').innerHTML = d.items.map(i => {
      const a = i.action;
      const btn = !a ? '' : a.href ? `<a class="btn" href="${esc(a.href)}">${esc(a.label)}</a>` : `<button type="button" data-api="${esc(a.api)}">${esc(a.label)}</button>`;
      return `<div class="item ${i.ok ? 'ok' : 'bad'}"><h2>${i.ok ? '✅' : '❌'} ${esc(i.title)}</h2>
        <div class="why">${esc(i.why)}</div>${i.steps.length ? '<b>कैसे ठीक करें:</b><ol>' + i.steps.map(x => `<li>${esc(x)}</li>`).join('') + '</ol>' : ''}
        ${btn}<div class="unlock">${i.ok ? '' : 'खुलेगा: ' + esc(i.unlocks_by)}</div></div>`;
    }).join('');
    const sp = d.speed || {};
    const running = d.speed_check_running;
    $('s010').disabled = $('s015').disabled = running || !sp.enabled || !sp.tool_installed;
    $('speedState').textContent = !sp.enabled ? 'Speed control (closed loop) अभी बंद है।' : !sp.tool_installed ? 'Speed check tool अभी rover पर install नहीं है।'
      : running ? 'Speed check चल रहा है… remote तैयार रखें (B = रुको)।'
      : 'PASS: ' + ((sp.passed || []).map(x => x.toFixed(2)).join(', ') || 'कोई नहीं') + ' • बाकी: ' + ((sp.missing || []).map(x => x.toFixed(2)).join(', ') || 'कोई नहीं');
    $('results').innerHTML = (sp.results || []).slice().reverse().map(r => `<div class="${r.verdict === 'PASS' ? 'pass' : 'fail'}">
      ${esc(Number(r.target_mps).toFixed(2))} m/s → ${esc(r.verdict)} • औसत ${r.steady_mean_mps == null ? '—' : Number(r.steady_mean_mps).toFixed(3)} • peak ${r.peak_mps == null ? '—' : Number(r.peak_mps).toFixed(3)} • ${esc(r.end_reason)}${r.failed_checks && r.failed_checks.length ? ' • fail: ' + esc(r.failed_checks.join(', ')) : ''}</div>`).join('');
  }
  async function poll() {
    if (document.hidden) return;
    try { render(await fetch('/api/readiness', { cache: 'no-store' }).then(r => r.json())); } catch (e) { $('summary').textContent = 'Rover से जुड़ नहीं पा रहे'; $('summary').className = 'summary bad'; }
    try {
      const s = await fetch('/api/readiness/speedcheck', { cache: 'no-store' }).then(r => r.json());
      $('log').hidden = !s.log; $('log').textContent = s.log || '';
    } catch (e) { /* keep last */ }
  }
  $('items').onclick = async e => { const b = e.target.closest('[data-api]'); if (b) { await post(b.dataset.api, {}); setTimeout(poll, 1500); } };
  for (const [id, v] of [['s010', 0.10], ['s015', 0.15]]) {
    $(id).onclick = async () => {
      if (!confirm(`Speed check ${v.toFixed(2)} m/s शुरू करें?\n\nRover ~0.6 m आगे अपने आप चलेगा। आगे 1.5 m खाली है? Remote हाथ में है?`)) return;
      await post('/api/readiness/speedcheck', { speed: v, pin: $('pin').value }); $('pin').value = ''; setTimeout(poll, 800);
    };
  }
  setInterval(poll, 1500); poll();
})();
