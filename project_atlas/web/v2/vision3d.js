/* ATLAS 3D Vision Lab (Stage 31/32 UI). Same-origin requests only: GET /api/vision3d/{status,frame,pixel,cloud,raw}
 * and POST /api/vision3d/viewer {start|stop}. Stage 32: infrared is fetched as the camera's native bytes and only
 * contrast-stretched in this browser for display; raw values are shown on click. No ROS control, driver parameter change or recording.
 * The status poll keeps the existing 4-second viewer lease alive only while this page is visible. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), api = '/api/vision3d/';
  let paused = false, busy = false, timer = null, controller = null, status = null, urls = {}, imageStamps = {}, cloud = null, projected = [];
  // Stage 31b: after Start, the previous session's state (same worker_pid, or a reply already in flight) must not be
  // shown as if it were the new session. Until the new worker reports, the banner says "Checking before start".
  let starting = null;   // {fromPid, at} while waiting for the new worker's first state
  const irEvidence = { received: 0, rendered: 0, failures: 0, last_stamp: null, scope: 'this page lifetime; no image history' };
  function currentRuntime(rt) {
    if (!starting) return rt;
    const fresh = rt && rt.worker_pid && rt.worker_pid !== starting.fromPid;
    const ended = rt && !rt.worker_pid && rt.state === 'OFF' && rt.reason;     // new worker died before writing state
    if (fresh || ended || Date.now() - starting.at > 20000) { starting = null; return rt; }
    return { state: 'CHECKING', limits: rt && rt.limits, reason: '' };
  }
  let yaw = 0, pitch = 0, zoom = 110, pan = [0, 0], panning = false, drag = null;
  const canvas = $('cloudCanvas'), ctx = canvas.getContext('2d');
  const isNum = v => typeof v === 'number' && Number.isFinite(v);
  const fmt = (n, d = 3) => isNum(n) ? n.toFixed(d) : 'unknown';
  const mode = () => (document.querySelector('input[name="vlMode"]:checked') || {}).value || 'depth';
  const MODE_NAMES = { depth: 'depth only', concurrent: 'depth + RGB', ir: 'infrared only', ir_depth: 'infrared + depth', rgb_ir: 'infrared + RGB', depth_cloud: 'depth + 3D cloud' };
  let frozen = false, ir = null;   // ir: last native IR frame {w,h,bits,values}

  // ---------- supported-mode selection ----------
  function applyModes(support) {
    for (const label of document.querySelectorAll('#vlModes label[data-mode]')) {
      const m = label.dataset.mode, info = (support || {})[m], input = label.querySelector('input'), note = label.querySelector('[data-note]');
      const st = info ? info.state : (m === 'depth' ? 'verified' : 'untested');
      label.className = st; label.title = info ? info.note : '';
      note.textContent = st === 'verified' ? 'Tested' : st === 'unsupported' ? (m === 'depth_cloud' ? 'Needs calibration' : 'Not supported') : 'Not yet tested';
      input.disabled = st === 'unsupported';
      if (input.disabled && input.checked) document.querySelector('input[name="vlMode"][value="depth"]').checked = true;
    }
    const info = (support || {})[mode()];
    $('vlModeNote').textContent = info ? info.note : '';
  }
  document.querySelectorAll('input[name="vlMode"]').forEach(i => i.addEventListener('change', () => applyModes(status && status.mode_support)));

  // ---------- native infrared display ----------
  function clearIr() { const c = $('irCanvas'); c.classList.add('off'); delete c.dataset.sourceStamp; c.dataset.rendered = 'false'; ir = null; $('irEmpty').hidden = false; $('irProbe').textContent = ''; }
  function drawIr(buf, h) {
    const w = +h.get('X-Width'), ht = +h.get('X-Height'), enc = h.get('X-Encoding'), step = +h.get('X-Step'), be = h.get('X-Bigendian') === '1';
    if (!['mono8', 'mono16', '16UC1'].includes(enc)) throw Error('Unsupported native IR encoding');
    const bits = enc === 'mono8' ? 8 : 16, dv = new DataView(buf), n = w * ht;
    if (!(w > 0 && ht > 0) || step < w * bits / 8 || buf.byteLength !== step * ht) throw Error('IR frame size mismatch');
    const values = bits === 8 ? new Uint8Array(n) : new Uint16Array(n);
    for (let y = 0; y < ht; y++) for (let x = 0; x < w; x++) values[y * w + x] = bits === 8 ? dv.getUint8(y * step + x) : dv.getUint16(y * step + x * 2, !be);
    // Display-only contrast stretch between the 2nd and 98th percentiles of THIS frame; raw values are untouched.
    const sorted = values.slice().sort(), lo = sorted[Math.floor(n * 0.02)], hi = Math.max(lo + 1, sorted[Math.floor(n * 0.98)]);
    const c = $('irCanvas'), g = c.getContext('2d'); c.width = w; c.height = ht;
    const img = g.createImageData(w, ht);
    for (let i = 0; i < n; i++) { const v = Math.max(0, Math.min(255, Math.round((values[i] - lo) * 255 / (hi - lo)))); img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v; img.data[i * 4 + 3] = 255; }
    g.putImageData(img, 0, 0); c.classList.remove('off'); $('irEmpty').hidden = true;
    ir = { w, h: ht, bits, values, stamp: h.get('X-Source-Stamp') };
    c.dataset.sourceStamp = ir.stamp; c.dataset.rendered = 'true';
    $('irScale').textContent = `Native ${bits}-bit infrared (${enc}), ${w} × ${ht}. Display stretched from raw ${lo} (black) to ${hi} (white); the camera's values are not changed.`;
  }
  $('irCanvas').onclick = e => {
    if (!ir) return;
    const r = e.target.getBoundingClientRect(), u = Math.min(ir.w - 1, Math.floor((e.clientX - r.left) / r.width * ir.w)), v = Math.min(ir.h - 1, Math.floor((e.clientY - r.top) / r.height * ir.h));
    $('irProbe').textContent = `Raw infrared intensity ${ir.values[v * ir.w + u]} (of ${ir.bits === 8 ? 255 : 65535}) at pixel ${u}, ${v}`;
  };

  function clearImage(k) { if (k === 'ir') return clearIr(); $(k + 'Image').removeAttribute('src'); if (urls[k]) URL.revokeObjectURL(urls[k]); delete urls[k]; const e = $(k + 'Empty'); if (e) e.hidden = false; }
  async function get(route) { const r = await fetch(api + route, { cache: 'no-store', signal: controller.signal }); if (!r.ok) { let e = {}; try { e = await r.json(); } catch (x) { /* empty */ } throw Error(e.error || r.status); } return r; }
  async function viewer(payload) {
    const r = await fetch(api + 'viewer', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Vision3D': '1' }, body: JSON.stringify(payload), keepalive: true });
    const data = await r.json(); if (!r.ok) throw Error(data.error || r.status); return data;
  }

  // ---------- readable state ----------
  function bar(id, value, limit) {
    const i = $(id); if (!i) return;
    i.style.width = (isNum(value) ? Math.max(0, Math.min(100, value)) : 0) + '%';
    i.className = isNum(value) && value > limit ? 'over' : '';
  }
  function explain(rt) {
    const st = rt ? String(rt.state || 'OFF') : 'NONE', reason = rt ? String(rt.reason || '') : '';
    const failed = (rt && rt.failed_resources) || {}, res = (rt && rt.resources) || {};
    const lim = (rt && rt.limits) || { cpu_percent: 75, ram_percent: 80, temperature_c: 70 };
    let tone = 'idle', title = 'Camera off', text = 'Choose a mode and press Start. A session runs for up to 60 seconds.';
    if (!rt) { tone = 'fail'; title = 'Viewer not installed'; text = 'The Vision Lab runtime is not available on this Jetson.'; }
    else if (st === 'CHECKING') { tone = 'busy'; title = 'Checking before start'; text = 'ATLAS is confirming it is stopped and has enough CPU, memory and thermal headroom before turning the camera on.'; }
    else if (st === 'ACTIVE') {
      tone = 'ok'; title = 'Camera streaming'; text = `Live view for ${isNum(rt.remaining_s) ? Math.ceil(rt.remaining_s) : '—'} more seconds. Distances are uncalibrated sensor readings.`;
      if (['ir', 'ir_depth', 'rgb_ir'].includes(rt.mode)) {
        const s = status && status.streams && status.streams.ir;
        if (!s || s.state !== 'ACTIVE') {
          tone = 'warn'; title = s && s.state === 'STALE' ? 'IR STREAM STALE' : 'IR NO FRAMES RECEIVED';
          text = 'The driver is running, but fresh infrared images have not reached the viewer. This is not a successful IR view.';
        } else { title = 'IR frames received'; text = 'Receiver has fresh infrared frames. Browser rendering is reported below.'; }
      }
    }
    else if (st === 'RESOURCE BLOCKED') {
      tone = 'warn'; title = 'Stopped to protect ATLAS';
      const cpu = isNum(failed.cpu) ? failed.cpu : null;
      const what = cpu !== null ? `CPU reached ${cpu.toFixed(1)}%, above the ${lim.cpu_percent}% limit` :
        /RAM/.test(reason) ? `memory went above the ${lim.ram_percent}% limit` : /temperature|thermal/i.test(reason) ? `temperature went above ${lim.temperature_c} °C` : 'a resource limit was exceeded';
      text = `${what}, so the camera was turned off${rt.driver_stopped ? ' and the driver was stopped' : ''}. Nothing else on ATLAS was changed. You can try again later when the Jetson is less busy.`;
    } else if (reason) {
      const done = /session complete/i.test(reason);
      tone = done ? 'idle' : 'warn'; title = done ? 'Session finished' : 'Camera off';
      text = done ? 'The 60-second session ended. Press Start for another one.' :
        /paused|closed|lease/i.test(reason) ? 'The camera was stopped because the page was paused, hidden or closed.' :
        /domain .* in use/i.test(reason) ? 'Another program is already using the private Vision Lab ROS domain, so the camera was not started.' :
        /existing Astra/i.test(reason) ? 'Another Astra camera process is already running, so a second one was not started.' :
        /policy|stationary|nonzero|stale/i.test(reason) ? 'ATLAS was not confirmed stopped and E-STOP latched, so the camera was not started.' : reason;
    }
    const finalIr = status && status.last_session && status.last_session.streams && status.last_session.streams.ir;
    if (st === 'OFF' && rt && rt.driver_pid && ['ir', 'ir_depth', 'rgb_ir'].includes(rt.mode) && finalIr && !finalIr.received) {
      tone = 'warn'; title = 'IR NO FRAMES RECEIVED';
      text = 'The driver stopped. No infrared frame reached the receiver in the last session; see Developer Diagnostics.';
    }
    $('vlState').className = 'vl-state ' + tone; $('vlTitle').textContent = title; $('vlText').textContent = text;
    const cpu = isNum(failed.cpu) ? failed.cpu : res.cpu_percent, ram = res.ram_percent;
    const temps = res.thermal_c && typeof res.thermal_c === 'object' ? Object.values(res.thermal_c).filter(isNum) : [];
    const temp = temps.length ? Math.max(...temps) : null;
    $('vlCpu').textContent = isNum(cpu) ? cpu.toFixed(1) + '%' : '—'; bar('vlCpuBar', cpu, lim.cpu_percent);
    $('vlRam').textContent = isNum(ram) ? ram.toFixed(0) + '%' : '—'; bar('vlRamBar', ram, lim.ram_percent);
    $('vlTemp').textContent = isNum(temp) ? temp.toFixed(1) + ' °C' : '—'; bar('vlTempBar', temp, lim.temperature_c);
    $('vlRes').title = isNum(failed.cpu) ? 'CPU value is the sample that stopped the camera; RAM and temperature are from the last passing check.' : 'Last safety check sample';
    $('vlDriver').textContent = !rt ? '—' : st === 'ACTIVE' ? 'Running' : rt.driver_pid ? (rt.driver_stopped ? 'Stopped safely' : 'Stopping…') : st === 'CHECKING' ? 'Not started yet' : 'Off';
    const running = st === 'ACTIVE' || st === 'CHECKING';
    $('runtimeState').textContent = running ? (st === 'ACTIVE' ? `Driver running · ${MODE_NAMES[String(rt.mode || mode())] || 'depth only'}${frozen ? ' · preview paused' : ''}` : 'Starting…') : 'Camera off · press Start';
    $('startViewer').disabled = running;
    $('freeze').disabled = st !== 'ACTIVE';
    if (st !== 'ACTIVE' && frozen) { frozen = false; $('freeze').textContent = 'Pause preview'; $('freeze').setAttribute('aria-pressed', 'false'); }
  }
  function streamView(k, s) {
    const chip = $(k + 'State'), active = s.state === 'ACTIVE';
    chip.textContent = active ? 'Live' : s.state === 'STALE' ? 'Stale' : s.state === 'SENSOR ERROR' ? 'Sensor error' : 'Off';
    chip.className = 'vl-chip ' + (active ? 'ok' : s.state === 'STALE' || s.state === 'SENSOR ERROR' ? 'warn' : '');
    const fps = $(k + 'Fps'); if (fps) fps.textContent = active && isNum(s.fps_observed) ? `${s.fps_observed.toFixed(1)} fps · ${isNum(s.source_age_s) ? s.source_age_s.toFixed(2) + ' s old' : ''}` : '';
    if (k !== 'cloud') $(k + 'Meta').textContent = s.width ? `${s.width} × ${s.height} ${s.encoding || ''} · ${s.received || 0} frames received · largest gap ${fmt(s.max_gap_s, 2)} s` : (s.state === 'ACTIVE' ? '' : '');
  }

  // ---------- 3D (stays disabled until calibration) ----------
  function project(p) { const a = p[0] * Math.cos(yaw) + p[2] * Math.sin(yaw), b = -p[0] * Math.sin(yaw) + p[2] * Math.cos(yaw), c = p[1] * Math.cos(pitch) - b * Math.sin(pitch), d = p[1] * Math.sin(pitch) + b * Math.cos(pitch); return [canvas.width / 2 + a * zoom + pan[0], canvas.height / 2 + c * zoom + pan[1], d]; }
  function draw() {
    canvas.width = Math.max(1, Math.floor(canvas.clientWidth)); canvas.height = Math.max(1, Math.floor(canvas.clientHeight)); ctx.clearRect(0, 0, canvas.width, canvas.height); projected = [];
    ctx.fillStyle = '#8DA3B8'; ctx.font = '12px system-ui';
    if (!cloud) { ctx.fillText('3D view disabled until calibration is valid', 16, 26); return; }
    for (const p of cloud.points) { const q = project(p); if (q[0] < 0 || q[1] < 0 || q[0] > canvas.width || q[1] > canvas.height) continue; ctx.fillStyle = `hsl(${Math.min(240, p[2] * 48)},85%,65%)`; ctx.fillRect(q[0], q[1], 2, 2); projected.push({ q, p }); }
    const origin = project([0, 0, 0]); for (const [label, p, color] of [['X', [.4, 0, 0], '#ff8f94'], ['Y', [0, .4, 0], '#87f8b3'], ['Z', [0, 0, .4], '#85beff']]) { const q = project(p); ctx.strokeStyle = color; ctx.beginPath(); ctx.moveTo(origin[0], origin[1]); ctx.lineTo(q[0], q[1]); ctx.stroke(); ctx.fillStyle = color; ctx.fillText(label, q[0] + 4, q[1]); }
  }
  const xyzText = p => `X ${fmt(p[0])} m · Y ${fmt(p[1])} m · Z ${fmt(p[2])} m · range ${fmt(Math.hypot(...p))} m`;

  async function refresh() {
    if (busy || paused || document.hidden) return; busy = true; controller = new AbortController();
    try {
      status = await (await get('status')).json();
      status.runtime = currentRuntime(status.runtime);
      explain(status.runtime);
      $('sourceNotice').textContent = (status.simulated ? 'SIMULATED UI TEST — NOT JETSON DATA · ' : '') + status.configuration + (status.error ? ' · ' + status.error : '');
      $('mode').replaceChildren(...(status.modes.length ? status.modes : ['Not yet verified']).map(m => { const o = document.createElement('option'); o.textContent = typeof m === 'string' ? m : JSON.stringify(m); return o; }));
      applyModes(status.mode_support);
      const cal = status.calibration_state || { state: 'NOT VALIDATED', reason: 'Calibration status unavailable.' };
      $('cloudCal').textContent = cal.state === 'VALIDATED' ? 'Calibration validated. Points are metric (X right, Y down, Z forward).' : 'Calibration not validated: ' + cal.reason;
      $('cloudCal').className = 'vl-cal ' + (cal.state === 'VALIDATED' ? 'ok' : 'blocked');
      const cs = status.streams.cloud;
      $('showCloud').disabled = !(cal.state === 'VALIDATED' && cs && cs.state === 'ACTIVE');
      if ($('showCloud').disabled) $('showCloud').checked = false;
      for (const k of ['rgb', 'depth', 'ir', 'cloud']) {
        const s = status.streams[k]; streamView(k, s);
        if (k === 'cloud') { if (cal.state !== 'VALIDATED') { $('cloudState').textContent = 'Blocked'; $('cloudState').className = 'vl-chip warn'; $('cloudFps').textContent = ''; } continue; }
        if (s.state !== 'ACTIVE') { clearImage(k); continue; }
        if (frozen) continue;                         // Pause preview: keep the last picture, camera keeps running
        if (k === 'ir') {
          try { const response = await get('raw?kind=ir'); const bytes = await response.arrayBuffer(); irEvidence.received = Math.min(Number.MAX_SAFE_INTEGER, irEvidence.received + 1); drawIr(bytes, response.headers); irEvidence.rendered = Math.min(Number.MAX_SAFE_INTEGER, irEvidence.rendered + 1); irEvidence.last_stamp = ir.stamp; $('irState').textContent = 'Rendered'; }
          catch (e) { irEvidence.failures = Math.min(Number.MAX_SAFE_INTEGER, irEvidence.failures + 1); clearIr(); $('irState').textContent = e.message; }
          continue;
        }
        try {
          const response = await get('frame?kind=' + k), blob = await response.blob(); clearImage(k);
          imageStamps[k] = response.headers.get('X-Source-Stamp'); urls[k] = URL.createObjectURL(blob); $(k + 'Image').src = urls[k];
          const e = $(k + 'Empty'); if (e) e.hidden = true;
        } catch (e) { clearImage(k); $(k + 'State').textContent = e.message; }
      }
      if ($('showCloud').checked && status.streams.cloud.state === 'ACTIVE') {
        if (!frozen) {
          try { cloud = await (await get('cloud')).json(); $('obstacles').textContent = JSON.stringify(cloud.shadow_obstacles, null, 2);
            $('cloudMeta').textContent = `${cloud.points.length} points drawn of ${cloud.source_points} in the cloud · every ${cloud.sample_stride} point · frame ${cloud.frame}`; }
          catch (e) { cloud = null; $('cloudMeta').textContent = e.message; }
        }
      } else cloud = null;
      draw();
      $('diagnostics').textContent = JSON.stringify({ runtime: status.runtime, ir_delivery: status.ir_delivery, ir_boundaries: status.ir_boundaries,
        transport: status.transport, last_session: status.last_session, ir_api: status.ir_api, browser_ir_counters: irEvidence,
        browser_ir: { rendered: !!ir, source_stamp: ir && ir.stamp, preview_paused: frozen },
        calibration: status.calibration, camera_info: status.camera_info, usb_inventory: status.usb_verified, usb_note: status.usb_note, depth_validity_sample: status.depth_stats, streams: status.streams, drops: status.dropped_messages, tf: status.tf, detections: status.detections }, null, 2);
    } catch (e) {
      if (e.name !== 'AbortError') { $('vlState').className = 'vl-state fail'; $('vlTitle').textContent = 'No reply from the Vision Lab'; $('vlText').textContent = e.message; }
      cloud = null; for (const k of ['rgb', 'depth', 'ir']) clearImage(k); draw();
    } finally { busy = false; if (!paused && !document.hidden) timer = setTimeout(refresh, 500); }
  }
  function suspend() { clearTimeout(timer); if (controller) controller.abort(); cloud = null; for (const k of ['rgb', 'depth', 'ir']) clearImage(k); draw(); }
  $('freeze').onclick = () => {
    frozen = !frozen; $('freeze').textContent = frozen ? 'Resume preview' : 'Pause preview'; $('freeze').setAttribute('aria-pressed', String(frozen));
  };
  $('startViewer').onclick = async () => {
    frozen = false; $('freeze').textContent = 'Pause preview';
    starting = { fromPid: (status && status.runtime && status.runtime.worker_pid) || null, at: Date.now() };
    explain({ state: 'CHECKING', limits: status && status.runtime && status.runtime.limits });
    try { $('startViewer').disabled = true; await viewer({ action: 'start', mode: mode() }); paused = false; clearTimeout(timer); refresh(); }
    catch (e) { starting = null; $('startViewer').disabled = false; $('runtimeState').textContent = e.message; }
  };
  $('pause').onclick = async () => {
    paused = true; suspend();
    try { await viewer({ action: 'stop' }); $('runtimeState').textContent = 'Camera off · stopped by you'; } catch (e) { $('runtimeState').textContent = e.message; }
    finally { $('startViewer').disabled = false; paused = false; setTimeout(refresh, 800); }
  };
  document.addEventListener('visibilitychange', () => { if (document.hidden) { suspend(); viewer({ action: 'stop' }).catch(() => {}); } else if (!paused) refresh(); });
  window.addEventListener('pagehide', () => { suspend(); viewer({ action: 'stop' }).catch(() => {}); });
  $('depthImage').onclick = async e => {
    if (!status || paused) return;
    const r = e.target.getBoundingClientRect(), s = status.streams.depth, u = Math.floor((e.clientX - r.left) / r.width * s.width), v = Math.floor((e.clientY - r.top) / r.height * s.height);
    try {
      const m = await (await get(`pixel?u=${u}&v=${v}&stamp=${encodeURIComponent(imageStamps.depth)}`)).json();
      $('measurement').textContent = !m.valid ? `No reading at pixel ${u}, ${v} (too near, too far or absorbed)` :
        `${fmt(m.depth_z_m, 3)} m at pixel ${u}, ${v} · uncalibrated${m.xyz_m ? '\n' + xyzText(m.xyz_m) : ''}`;
    } catch (err) { $('measurement').textContent = err.message; }
  };
  canvas.onpointerdown = e => { drag = { x: e.clientX, y: e.clientY, startX: e.clientX, startY: e.clientY, pan: e.shiftKey || panning }; canvas.setPointerCapture(e.pointerId); };
  canvas.onpointermove = e => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (drag.pan) { pan[0] += dx; pan[1] += dy; } else { yaw += dx * .008; pitch = Math.max(-1.5, Math.min(1.5, pitch + dy * .008)); } drag.x = e.clientX; drag.y = e.clientY; draw(); };
  canvas.onpointerup = e => { if (drag && Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 5 && cloud) { const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top; let best = null, d = 12; for (const v of projected) { const n = Math.hypot(v.q[0] - x, v.q[1] - y); if (n < d) { best = v; d = n; } } if (best) $('measurement').textContent = xyzText(best.p); } drag = null; };
  canvas.onpointercancel = () => drag = null;
  function scale(f) { zoom = Math.max(10, Math.min(1000, zoom * f)); draw(); }
  canvas.addEventListener('wheel', e => { e.preventDefault(); scale(e.deltaY < 0 ? 1.1 : .9); }, { passive: false });
  $('zoomIn').onclick = () => scale(1.2); $('zoomOut').onclick = () => scale(1 / 1.2); $('resetView').onclick = () => { yaw = 0; pitch = 0; zoom = 110; pan = [0, 0]; draw(); };
  $('panMode').onclick = () => { panning = !panning; $('panMode').setAttribute('aria-pressed', String(panning)); };
  $('showCloud').onchange = () => { if (!$('showCloud').checked) { cloud = null; draw(); } };
  new ResizeObserver(draw).observe(canvas); refresh();
})();
