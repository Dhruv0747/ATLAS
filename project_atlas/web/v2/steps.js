/* ATLAS master-plan later-step page (2026-11-23): /v2/steps?n=5|6|7|8|9. Read-only owner checks; ATLAS does not move. */
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
    7: { title: 'Step 7 · camera visual odometry (shadow mode)',
      how: ['ATLAS does not move. Park it facing a corner, furniture or boxes (not one plain wall), 0.5–3 m away.',
        'Press START and keep ATLAS still for 20 s. ATLAS checks its depth-camera odometry: speed, freshness, GOOD / DEGRADED / LOST state, CPU use, and that it feeds nothing.',
        'The moving part comes from the Stage-2 turn check: every turn check now also records the camera estimate against the LiDAR. If this page says NEEDS MOTION, run the Stage-2 turn check once (operator PIN, remote in hand), then press START here again.'],
      foot: 'Shadow mode: the camera estimate is only watched and compared. It never goes into the EKF, Nav2 or the motors. "NOT USABLE" completes this step honestly: the camera estimate disagreed with the LiDAR while turning and stays shadow-only.',
      names: { vo_running: 'Camera odometry running', shadow_only: 'Shadow only (feeds nothing)', atlas_parked: 'ATLAS stood still',
        rate_ok: 'Rate ≥ 4 Hz', age_ok: 'Fresh (p95 age ≤ 0.5 s)', mostly_good_parked: 'GOOD ≥ 80 % when parked',
        parked_drift_ok: 'No drift when parked', cpu_within_budget: 'CPU ≤ 25 % of one core',
        motion_heading_agrees: 'Turn angle agrees with LiDAR', motion_distance_agrees: 'Distance agrees with LiDAR',
        motion_tracking_kept: 'Not LOST while turning' },
      motion: { href: '/v2/stage2', label: 'Open Stage 2 · turn check',
        text: 'Next: run the Stage-2 turn check once (operator PIN, remote in hand). It records the camera estimate against the LiDAR. Then come back and press START here once more.' } },
    8: { title: 'Step 8 · TensorRT YOLO benchmark',
      how: ['ATLAS does not move. Keep it parked with the normal navigation stack running (about 30 s).',
        'Press START. ATLAS first measures itself for 5 s without YOLO, then runs its existing YOLO object detector on live camera frames (at most 10 per second) for 20 s.',
        'It stops YOLO at once if CPU stays at 75 % or more, RAM reaches 80 % or any temperature reaches 70 °C.'],
      foot: 'Nothing is rebuilt: this measures the YOLO that ATLAS already has. "NOT ADVISED" completes this step honestly: YOLO works but is too slow or too heavy next to navigation, so it stays off by default (Eco mode) and runs only on demand.',
      names: { parked: 'ATLAS parked', engine_loaded: 'YOLO engine loaded', inference_ran: 'YOLO ran', latency_p95_ok: 'Fast (p95 ≤ 100 ms)',
        rate_ok: '≥ 9 detections per second', cpu_limit_held: 'CPU below 75 %', ram_limit_held: 'RAM below 80 %',
        temp_limit_held: 'Temperature below 70 °C', under_nav_stack: 'Measured with navigation running' } },
    9: { title: 'Step 9 · semantic perception → semantic goals',
      how: ['ATLAS does not move and no goal is sent. Park it facing a chair, table, bottle, bag or similar, 0.5–3 m away.',
        'Centre the camera (straight ahead) and make sure ATLAS is localised on the map.',
        'Press START (about 15 s). ATLAS names the objects it sees, confirms each one with the LiDAR, places it on the map and works out where it would stop in front of it, but only writes that down.'],
      foot: 'Part A is advisory only: object names and positions are suggestions and nothing is sent. Part B below then sends ATLAS once to the stop point in front of the object, through Nav2 and every safety check.',
      names: { parked: 'ATLAS parked', camera_forward: 'Camera centred forward', localised: 'Localised on the map', lidar_live: 'LiDAR live',
        yolo_ran: 'Object detector ran', limits_held: 'CPU / RAM / temperature limits held', objects_found: 'Object found',
        positions_stable: 'Object position steady (≤ 25 cm)', goals_resolved_not_sent: 'Stop point worked out (not sent)' },
      // 2026-11-26 part B: semantic goal through Nav2 (owner-triggered, bounded; ATLAS moves)
      partB: {
        how: ['First pass Part A above (START CHECK) with ATLAS 1–2.5 m from the object. Do not move ATLAS after it (Part B refuses a result older than 30 min or if ATLAS moved).',
          'Clear the path between ATLAS and the object. Keep the remote in hand: B stops ATLAS at once.',
          'On the home page switch to Autonomous mode (operator PIN) and release the E-STOP.',
          'Press GO TO OBJECT. ATLAS drives through Nav2 to the stop point 0.70 m in front of the object (at most 2.5 m, 60 s), stops, looks at the object again, and switches back to Manual.'],
        names: { dispatched: 'Goal sent through mission control', nav2_succeeded: 'Nav2 reached the goal', no_owner_stop: 'No E-STOP / Manual during the drive',
          within_time: 'Within 60 s', stayed_on_course: 'Stayed on course (≤ 1 m off)', limits_held: 'CPU / RAM / temperature limits held',
          arrived_at_stop_point: 'Stopped at the stop point (≤ 25 cm)', facing_object: 'Facing the object (≤ 25°)',
          object_confirmed: 'Same object seen again (3 of 5)' } } },
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
      const good = /^(PASS|ADVISED|NOT ADVISED|NOT USABLE)$/.test(last.verdict);
      const wait = /^NEEDS/.test(last.verdict);
      const rows = Object.entries(last.checks || {}).map(([k, v]) => `<tr><td>${esc(info.names[k] || k)}</td><td class="${v ? 'ok' : 'bad'}">${v ? 'YES' : 'NO'}</td></tr>`).join('');
      $('result').innerHTML = `<div class="big ${good ? 'ok' : wait ? '' : 'bad'}" style="background:${good ? '#124d2f' : wait ? '#5a4a12' : '#5c1420'}">STEP ${n}: ${esc(last.verdict)}</div>` +
        `<table>${rows}</table><small>${esc(last.when || '')} · ${esc(last.detail || '')}</small>` +
        ((last.notes || []).length ? `<small>${esc(last.notes.join(' · '))}</small>` : '') +
        (wait && info.motion ? `<p style="margin:14px 0 6px">${esc(info.motion.text)}</p><a href="${info.motion.href}" style="display:block;text-align:center;padding:16px;border-radius:10px;background:#1f5fae;color:#fff;font-size:1.2em;font-weight:700;text-decoration:none">${esc(info.motion.label)} →</a>` : '');
    }
    $('log').textContent = d.log || '';
  }
  const pb = info.partB;
  if (pb) { $('partB').hidden = false; $('howB').innerHTML = pb.how.map(h => `<li>${esc(h)}</li>`).join(''); }
  function renderB(b, plan, stepBusy) {
    const st = ((plan || {}).later || []).find(l => l.n === n) || {};
    const locked = !st.part_a_done;
    $('goB').disabled = locked || b.running || stepBusy || !b.tool_installed;
    $('goB').textContent = b.running ? 'DRIVING TO THE OBJECT…' : locked ? '🔒 LOCKED — pass Part A first' : 'GO TO OBJECT';
    $('msgB').textContent = !b.tool_installed ? 'Part B is not installed on ATLAS yet.' : b.running ? 'ATLAS is moving. Remote in hand: B stops it.'
      : stepBusy ? 'Another check is running.' : locked ? 'Part B unlocks after Part A has passed.' : 'Ready. Autonomous mode ON and E-STOP released are needed.';
    const last = (b.results || []).slice(-1)[0];
    if (!last) { $('resultB').innerHTML = ''; } else {
      const ok = last.verdict === 'PASS', ref = last.verdict === 'REFUSED';
      const rows = Object.entries(last.checks || {}).map(([k, v]) => `<tr><td>${esc(pb.names[k] || k)}</td><td class="${v ? 'ok' : 'bad'}">${v ? 'YES' : 'NO'}</td></tr>`).join('');
      const ms = last.measured || {};
      // 2026-11-26 owner "show reason": why ATLAS did not get there (safety mux veto or mission-control refusal)
      const why = ms.blocked_by ? `<div style="margin:12px 0;padding:14px;border-radius:12px;background:#3a2a08;border:1px solid #d9a520;color:#fff;font-size:18px;line-height:1.4">` +
        `<b>Why ATLAS stopped:</b> ${esc(ms.blocked_by)}${(ms.mux_stops || [])[0] ? ' (' + esc(ms.mux_stops[0].count) + '×)' : ''}` +
        (ms.hint ? `<br><b>What to do:</b> ${esc(ms.hint)}` : '') + `</div>` : '';
      const refusedWhy = ref && (last.notes || []).length ? `<div style="margin:12px 0;padding:14px;border-radius:12px;background:#3a2a08;border:1px solid #d9a520;color:#fff;font-size:18px">` +
        `<b>Not started:</b> ${esc(last.notes.join(' · '))}</div>` : '';
      $('resultB').innerHTML = `<div class="big ${ok ? 'ok' : ref ? '' : 'bad'}" style="background:${ok ? '#124d2f' : ref ? '#5a4a12' : '#5c1420'}">PART B: ${esc(last.verdict)}</div>` +
        why + refusedWhy + `<table>${rows}</table><small>${esc(last.when || '')} · ${esc(last.detail || '')}</small>`;
    }
    $('logB').textContent = b.log || '';
  }
  let busy = false;
  async function poll() {
    if (busy) return; busy = true;
    try {
      const get = u => fetch(u, { cache: 'no-store', signal: AbortSignal.timeout(3000) }).then(r => r.json());
      const [d, plan, b] = await Promise.all([get('/api/readiness/stepcheck?n=' + n), get('/api/master_plan').catch(() => null),
        pb ? get('/api/readiness/semanticgo').catch(() => null) : null]);
      render(d, plan);
      if (pb && b) renderB(b, plan, d.busy);
    } catch (e) { $('msg').textContent = 'Lost contact with ATLAS: ' + e.message; }
    finally { busy = false; }
  }
  if (pb) $('goB').onclick = async () => {
    if (!confirm('ATLAS will DRIVE to the object now. Path clear and remote in hand?')) return;
    try {
      const r = await fetch('/api/readiness/semanticgo', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: '{}' });
      const d = await r.json().catch(() => ({})); alert(d.message || ('HTTP ' + r.status));
    } catch (e) { alert('Could not reach ATLAS: ' + e.message); }
    setTimeout(poll, 800);
  };
  $('go').onclick = async () => {
    try {
      const r = await fetch('/api/readiness/stepcheck', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: JSON.stringify({ n }) });
      const d = await r.json().catch(() => ({})); alert(d.message || ('HTTP ' + r.status));
    } catch (e) { alert('Could not reach ATLAS: ' + e.message); }
    setTimeout(poll, 800);
  };
  setInterval(poll, 2000); poll();
})();
