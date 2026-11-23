/* ATLAS Stage-2 gentle turn check page (2026-11-23). GET /api/readiness/turncheck + /api/master_plan; START via POST. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let locked = true, running = false, installed = true;

  function setButton() {
    $('go').disabled = locked || running || !installed;
    $('go').textContent = running ? 'RUNNING… (B stops)' : locked ? 'LOCKED — pass Stage 1 first' : 'START STAGE 2 TURNS';
  }

  function render(d, plan) {
    running = !!d.running; installed = d.tool_installed !== false;
    const g2 = ((plan || {}).gate || []).find(g => g.id === 'stage2');
    if (g2) locked = !!g2.locked;
    setButton();
    const last = (d.results || []).slice(-1)[0];
    $('msg').textContent = !installed ? 'The turn check tool is not installed on ATLAS yet.'
      : running ? 'Turn check running… keep the remote ready (B = stop).'
      : locked ? 'Stage 2 is locked until Stage 1 (straight run) has passed.'
      : g2 && String(g2.status).startsWith('PASS') ? 'Stage 2 already PASSED: ' + (g2.evidence || '') + ' You may run it again.'
      : 'Ready. Follow the steps above, then press START.';
    if (last) {
      const rows = (last.arcs || []).map(a => `<tr><td>${esc(a.direction)}</td><td class="${a.verdict === 'PASS' ? 'ok' : 'bad'}">${esc(a.verdict)}</td>` +
        `<td>gyro ${esc(a.imu_yaw_deg)}° · LiDAR ${a.icp_yaw_deg == null ? '-' : esc(a.icp_yaw_deg) + '°'} · ${esc(a.wheel_distance_m)} m · ${esc(a.end_reason)}` +
        `${Object.entries(a.checks || {}).filter(([, v]) => !v).map(([k]) => ' · ✗ ' + esc(k)).join('')}</td></tr>`).join('');
      const ok = last.verdict === 'PASS';
      $('result').innerHTML = `<div class="big ${ok ? 'ok' : 'bad'}" style="background:${ok ? '#124d2f' : '#5c1420'}">STAGE 2: ${esc(last.verdict)}</div>` +
        `<table>${rows}</table><small>${esc(last.when || '')} · ${esc(last.detail || '')}${(last.failed || []).length ? ' · failed: ' + esc(last.failed.join(', ')) : ''}</small>`;
    } else { $('result').innerHTML = ''; }
    $('log').textContent = d.log || '';
  }

  let busy = false;
  async function poll() {
    if (busy) return; busy = true;
    try {
      const [d, plan] = await Promise.all([
        fetch('/api/readiness/turncheck', { cache: 'no-store', signal: AbortSignal.timeout(3000) }).then(r => r.json()),
        fetch('/api/master_plan', { cache: 'no-store', signal: AbortSignal.timeout(3000) }).then(r => r.json()).catch(() => null)]);
      render(d, plan);
    } catch (e) { $('msg').textContent = 'Lost contact with ATLAS: ' + e.message; }
    finally { busy = false; }
  }

  $('go').onclick = async () => {
    if (!confirm('Start Stage 2 turns?\n\nATLAS will curve gently LEFT, stop, then curve gently RIGHT and stop (about 30 cm each).\nIs 1.5 m ahead and 0.6 m on both sides clear? Is the remote in your hand?')) return;
    try {
      const r = await fetch('/api/readiness/turncheck', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' },
        body: JSON.stringify({ pin: $('pin').value }) });
      const d = await r.json().catch(() => ({})); alert(d.message || ('HTTP ' + r.status));
    } catch (e) { alert('Could not reach ATLAS: ' + e.message); }
    $('pin').value = ''; setTimeout(poll, 800);
  };
  setInterval(poll, 1500); poll();
})();
