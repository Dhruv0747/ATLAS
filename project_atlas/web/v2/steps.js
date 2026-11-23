/* ATLAS master-plan later-step page (2026-11-23): /v2/steps?n=5|6. Read-only owner checks; ATLAS does not move. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const n = parseInt(new URLSearchParams(location.search).get('n') || '0', 10);
  const INFO = {
    5: { title: 'Step 5 · Nav2 recovery budget audit',
      how: ['ATLAS does not move. Nothing needs to be cleared.', 'Press START. ATLAS reads the navigation settings it is running right now and checks them (a few seconds).'],
      foot: 'Checks that every recovery retry is limited (no endless loops), the in-place Spin is off, back-up moves are short, a stuck robot is detected, a silent command is cut within 0.5 s instead of being replayed, and the Stage-3 runner has a Go retry budget.',
      names: { bt_files_found: 'Behaviour trees found', bt_retries_bounded: 'Retries limited', bt_no_spin: 'No in-place spin',
        backup_bounded: 'Back-up is short', stuck_detection: 'Stuck robot detected', stale_twist_cut: 'Old commands cut (≤ 0.5 s)',
        mission_home_retries: 'Return-home retries limited', runner_retry_budget: 'Stage-3 runner retry budget' } },
    6: { title: 'Step 6 · wheel PID evaluation',
      how: ['ATLAS does not move.', 'Press START. ATLAS reads its live encoder and steering feedback and decides whether a per-wheel PID controller is advisable.'],
      foot: 'The plan says: evaluate wheel PID only if feedback quality permits. "NOT ADVISED" completes this step honestly and names what blocks it (for example the excluded M3 encoder). The validated 3-encoder speed loop keeps controlling speed.',
      names: { live_data: 'Live encoder data', four_encoders_trusted: 'All 4 encoders trusted', steering_angle_measured: 'Steering angle measured',
        speed_loop_validated: 'Speed loop validated', per_wheel_pid_safe_off: 'Per-wheel PID safely off' } },
  };
  const info = INFO[n] || { title: 'Unknown step', how: [], foot: '', names: {} };
  $('title').textContent = info.title; document.title = 'ATLAS · ' + info.title;
  $('how').innerHTML = info.how.map(h => `<li>${esc(h)}</li>`).join('');
  $('foot').textContent = info.foot;

  function render(d, plan) {
    const st = ((plan || {}).later || []).find(l => l.n === n);
    const locked = !st || st.status === 'LOCKED';
    $('what').textContent = st ? `Board: ${st.status}` + (st.evidence ? ' · ' + st.evidence : '') : '';
    $('go').disabled = locked || d.busy || !d.tool_installed;
    $('go').textContent = d.running ? 'CHECKING…' : locked ? `🔒 LOCKED — finish ${st ? st.unlock_after : 'the step before'} first` : 'START CHECK';
    $('msg').textContent = !d.tool_installed ? 'This check is not installed on ATLAS yet.' : d.running ? 'Checking… (ATLAS does not move)'
      : d.busy ? 'Another check is running.' : locked ? 'This step unlocks after the step before it is done.' : 'Ready.';
    const last = (d.results || []).slice(-1)[0];
    if (!last) { $('result').innerHTML = ''; } else {
      const good = /^(PASS|ADVISED|NOT ADVISED)$/.test(last.verdict);
      const rows = Object.entries(last.checks || {}).map(([k, v]) => `<tr><td>${esc(info.names[k] || k)}</td><td class="${v ? 'ok' : 'bad'}">${v ? 'YES' : 'NO'}</td></tr>`).join('');
      $('result').innerHTML = `<div class="big ${good ? 'ok' : 'bad'}" style="background:${good ? '#124d2f' : '#5c1420'}">STEP ${n}: ${esc(last.verdict)}</div>` +
        `<table>${rows}</table><small>${esc(last.when || '')} · ${esc(last.detail || '')}</small>` +
        ((last.notes || []).length ? `<small>${esc(last.notes.join(' · '))}</small>` : '');
    }
    $('log').textContent = d.log || '';
  }
  let busy = false;
  async function poll() {
    if (busy) return; busy = true;
    try {
      const get = u => fetch(u, { cache: 'no-store', signal: AbortSignal.timeout(3000) }).then(r => r.json());
      const [d, plan] = await Promise.all([get('/api/readiness/stepcheck?n=' + n), get('/api/master_plan').catch(() => null)]);
      render(d, plan);
    } catch (e) { $('msg').textContent = 'Lost contact with ATLAS: ' + e.message; }
    finally { busy = false; }
  }
  $('go').onclick = async () => {
    try {
      const r = await fetch('/api/readiness/stepcheck', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: JSON.stringify({ n }) });
      const d = await r.json().catch(() => ({})); alert(d.message || ('HTTP ' + r.status));
    } catch (e) { alert('Could not reach ATLAS: ' + e.message); }
    setTimeout(poll, 800);
  };
  setInterval(poll, 2000); poll();
})();
