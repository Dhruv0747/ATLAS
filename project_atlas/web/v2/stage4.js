/* ATLAS Stage-4 page (2026-11-23): part A parked IMU/EKF/TF check (no PIN, no motion) and part B gentle turns under
   full workload (PIN, moves; same tool as Stage 2 with --workload). */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const NAMES = { parked: 'ATLAS stayed parked', imu_rate: 'Gyro data rate', imu_covariance: 'Gyro has covariance',
    imu_bias: 'Gyro bias', imu_drift: 'Gyro drift', ekf_rate: 'EKF rate', ekf_drift: 'EKF drift',
    tf_odom_base: 'TF odom → base_link', tf_map_odom: 'TF map → odom' };
  const banner = (title, verdict) => {
    const ok = verdict === 'PASS';
    return `<div class="big ${ok ? 'ok' : 'bad'}" style="background:${ok ? '#124d2f' : '#5c1420'}">${esc(title)}: ${esc(verdict)}</div>`;
  };

  function renderA(d, locked) {
    const running = !!d.running, installed = d.tool_installed !== false;
    $('go').disabled = locked || running || !installed;
    $('go').textContent = running ? 'CHECKING… do not touch ATLAS' : locked ? '🔒 LOCKED — pass stages 1, 2 and 3 first' : 'START PARKED CHECK (60 s)';
    const last = (d.results || []).slice(-1)[0];
    $('msg').textContent = !installed ? 'The IMU check tool is not installed on ATLAS yet.'
      : running ? 'Recording for 60 s… do not touch ATLAS or the remote.'
      : locked ? 'Stage 4 unlocks after the entry gate (stages 1, 2 and 3) has passed.' : 'Ready.';
    $('result').innerHTML = !last ? '' : banner('PART A', last.verdict) + `<table>${Object.entries(last.checks || {}).map(([k, v]) =>
      `<tr><td>${esc(NAMES[k] || k)}</td><td class="${v ? 'ok' : 'bad'}">${v ? 'PASS' : 'FAIL'}</td></tr>`).join('')}</table>` +
      `<small>${esc(last.when || '')} · ${esc(last.detail || '')}</small>`;
    return running ? d.log : '';
  }

  function renderB(d, locked) {
    const running = !!d.running && !!d.workload, other = !!d.running && !d.workload;
    $('goB').disabled = locked || !!d.running || d.tool_installed === false;
    $('goB').textContent = running ? 'TURNING… (B stops)' : locked ? '🔒 LOCKED — pass stages 1, 2 and 3 first' : 'START PART B TURNS';
    $('msgB').textContent = running ? 'Part B running… keep the remote ready (B = stop).' : other ? 'A Stage 2 turn check is running.' : '';
    const last = (d.workload_results || []).slice(-1)[0];
    if (!last) { $('resultB').innerHTML = ''; return running ? d.log : ''; }
    const w = last.workload || {};
    const row = (label, x) => x ? `<tr><td>${label}</td><td>${esc(x.hz)} Hz · gap ${esc(x.max_gap_s)} s · age p95 ${esc(x.age_p95_s)} s</td></tr>` : '';
    $('resultB').innerHTML = banner('PART B', last.verdict) + '<table>' +
      (last.arcs || []).map(a => `<tr><td>${esc(a.direction)} turn</td><td class="${a.verdict === 'PASS' ? 'ok' : 'bad'}">${esc(a.verdict)} · gyro ${esc(a.imu_yaw_deg)}° · LiDAR ${a.icp_yaw_deg == null ? '-' : esc(a.icp_yaw_deg) + '°'} · ${esc(a.end_reason)}</td></tr>`).join('') +
      row('Gyro (IM10A)', w.imu) + row('EKF /odom', w.ekf) + row('TF odom → base_link', w.tf_odom_base) + row('TF map → odom', w.tf_map_odom) +
      (w.ekf_turns ? `<tr><td>EKF vs LiDAR turn</td><td>${esc(JSON.stringify(w.ekf_turns))}</td></tr>` : '') +
      (w.load_avg_1m != null ? `<tr><td>CPU load (1 min)</td><td>${esc(w.load_avg_1m)}</td></tr>` : '') + '</table>' +
      `<small>${esc(last.when || '')}${(last.failed || []).length ? ' · failed: ' + esc(last.failed.join(', ')) : ''}</small>`;
    return running ? d.log : '';
  }

  let busy = false;
  async function poll() {
    if (busy) return; busy = true;
    try {
      const get = u => fetch(u, { cache: 'no-store', signal: AbortSignal.timeout(3000) }).then(r => r.json());
      const [a, b, plan] = await Promise.all([get('/api/readiness/imucheck'), get('/api/readiness/turncheck'), get('/api/master_plan').catch(() => null)]);
      const s4 = ((plan || {}).later || []).find(l => l.n === 4);
      const locked = !s4 || s4.status === 'LOCKED';
      const logA = renderA(a, locked), logB = renderB(b, locked);
      $('log').textContent = logB || logA || b.log || a.log || '';
    } catch (e) { $('msg').textContent = 'Lost contact with ATLAS: ' + e.message; }
    finally { busy = false; }
  }
  async function post(url, body) {
    try {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({})); alert(d.message || ('HTTP ' + r.status));
    } catch (e) { alert('Could not reach ATLAS: ' + e.message); }
    setTimeout(poll, 800);
  }
  $('go').onclick = () => {
    if (!confirm('Start the 60 s parked check?\n\nATLAS will NOT move. Do not touch ATLAS or the remote until it finishes.')) return;
    post('/api/readiness/imucheck', {});
  };
  $('goB').onclick = () => {
    if (!confirm('Start Stage 4 part B?\n\nATLAS will curve gently LEFT, stop, then RIGHT and stop (about 30 cm each) with everything running.\nIs 1.5 m ahead and 0.6 m on both sides clear? Is the remote in your hand?')) return;
    const pin = $('pin').value; $('pin').value = '';
    post('/api/readiness/turncheck', { pin, workload: true });
  };
  setInterval(poll, 2000); poll();
})();
