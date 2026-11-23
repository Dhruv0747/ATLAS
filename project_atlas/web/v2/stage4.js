/* ATLAS Stage-4 part A page (2026-11-23): parked IMU/EKF/TF check. Read-only test; no PIN. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const NAMES = { parked: 'ATLAS stayed parked', imu_rate: 'Gyro data rate', imu_covariance: 'Gyro has covariance',
    imu_bias: 'Gyro bias', imu_drift: 'Gyro drift', ekf_rate: 'EKF rate', ekf_drift: 'EKF drift',
    tf_odom_base: 'TF odom → base_link', tf_map_odom: 'TF map → odom' };

  function render(d, plan) {
    const s4 = ((plan || {}).later || []).find(l => l.n === 4);
    const locked = !s4 || s4.status === 'LOCKED', running = !!d.running, installed = d.tool_installed !== false;
    $('go').disabled = locked || running || !installed;
    $('go').textContent = running ? 'CHECKING… do not touch ATLAS' : locked ? '🔒 LOCKED — pass stages 1, 2 and 3 first' : 'START PARKED CHECK (60 s)';
    $('msg').textContent = !installed ? 'The IMU check tool is not installed on ATLAS yet.'
      : running ? 'Recording for 60 s… do not touch ATLAS or the remote.'
      : locked ? 'Stage 4 unlocks after the entry gate (stages 1, 2 and 3) has passed.'
      : (s4 && s4.evidence) || 'Ready. Press START.';
    const last = (d.results || []).slice(-1)[0];
    if (last) {
      const ok = last.verdict === 'PASS';
      const rows = Object.entries(last.checks || {}).map(([k, v]) => `<tr><td>${esc(NAMES[k] || k)}</td><td class="${v ? 'ok' : 'bad'}">${v ? 'PASS' : 'FAIL'}</td></tr>`).join('');
      $('result').innerHTML = `<div class="big ${ok ? 'ok' : 'bad'}" style="background:${ok ? '#124d2f' : '#5c1420'}">STAGE 4 PART A: ${esc(last.verdict)}</div>` +
        `<table>${rows}</table><small>${esc(last.when || '')} · ${esc(last.detail || '')}</small>`;
    } else { $('result').innerHTML = ''; }
    $('log').textContent = d.log || '';
  }

  let busy = false;
  async function poll() {
    if (busy) return; busy = true;
    try {
      const [d, plan] = await Promise.all([
        fetch('/api/readiness/imucheck', { cache: 'no-store', signal: AbortSignal.timeout(3000) }).then(r => r.json()),
        fetch('/api/master_plan', { cache: 'no-store', signal: AbortSignal.timeout(3000) }).then(r => r.json()).catch(() => null)]);
      render(d, plan);
    } catch (e) { $('msg').textContent = 'Lost contact with ATLAS: ' + e.message; }
    finally { busy = false; }
  }
  $('go').onclick = async () => {
    if (!confirm('Start the 60 s parked check?\n\nATLAS will NOT move. Do not touch ATLAS or the remote until it finishes.')) return;
    try {
      const r = await fetch('/api/readiness/imucheck', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: '{}' });
      const d = await r.json().catch(() => ({})); alert(d.message || ('HTTP ' + r.status));
    } catch (e) { alert('Could not reach ATLAS: ' + e.message); }
    setTimeout(poll, 800);
  };
  setInterval(poll, 2000); poll();
})();
