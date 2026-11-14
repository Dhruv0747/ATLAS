/* ATLAS Home (Stage 31): read-only status cards and layout helpers.
 * Reads the /api/status object command.js already fetches (latestStatus) and two read-only GETs:
 * /api/lidar-view (only while the LiDAR card is on screen) and /api/vision3d/summary (no viewer lease).
 * Sends no POST, no drive, camera, E-STOP, reset or navigation request. Unknown data is shown as unavailable. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const isNum = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
  const fx = (v, d = 1) => isNum(v) ? Number(v).toFixed(d) : '—';
  const parse = v => { if (v && typeof v === 'object') return v; try { return JSON.parse(v); } catch (e) { return null; } };
  const it = (r, k) => (r && r[k]) || null;
  const val = (r, k) => { const x = it(r, k); return x ? x.value : undefined; };
  const ageOf = (r, k) => { const x = it(r, k); return x && isNum(x.age) ? Number(x.age) : Infinity; };
  const agoText = a => !Number.isFinite(a) ? 'No update received' : a < 1 ? 'Updated just now' : a < 120 ? `Updated ${a.toFixed(a < 10 ? 1 : 0)} s ago` : `Updated ${Math.round(a / 60)} min ago`;
  const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* memory only */ } } };

  // Same rule as shell.js: a status object that has not changed for 5 s is not current.
  let seen = null, seenAt = 0;
  const fresh = () => {
    const d = typeof latestStatus !== 'undefined' ? latestStatus : null;
    if (d !== seen) { seen = d; seenAt = Date.now(); }
    return d && Date.now() - seenAt < 5000 ? d : null;
  };

  const PILL = { ok: 'Connected', stale: 'Stale', fault: 'Fault', off: 'Disconnected', unverified: 'Unverified', na: 'Unavailable', idle: 'Off', warn: 'Check' };
  const TONE = { ok: 'ok', stale: 'warn', fault: 'fail', off: 'fail', unverified: 'warn', na: '', idle: '', warn: 'warn' };
  function setCard(id, o) {
    const c = $(id); if (!c) return;
    const q = s => c.querySelector(s);
    const tone = TONE[o.state] || '';
    c.className = 'hm-card' + (tone ? ' s-' + tone : '');
    const pill = q('[data-pill]'); pill.textContent = o.pill || PILL[o.state] || o.state; pill.className = 'hm-pill ' + tone;
    if (q('[data-main]') && o.main !== undefined) q('[data-main]').textContent = o.main;
    if (q('[data-unit]') && o.unit !== undefined) q('[data-unit]').textContent = o.unit;
    if (q('[data-sub]') && o.sub !== undefined) q('[data-sub]').textContent = o.sub;
    if (q('[data-age]')) q('[data-age]').textContent = o.age === undefined ? '' : (typeof o.age === 'string' ? o.age : agoText(o.age));
  }
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

  // ---------- Jetson ----------
  function meter(label, value, limit, unit, warnAt, failAt) {
    const row = el('div', 'hm-meter'), bar = el('div', 'hm-bar'), fill = el('i');
    const v = isNum(value) ? Number(value) : null;
    const tone = v === null ? '' : v >= failAt ? 'fail' : v >= warnAt ? 'warn' : '';
    bar.className = 'hm-bar ' + tone; fill.style.width = (v === null ? 0 : Math.max(0, Math.min(100, v))) + '%'; bar.append(fill);
    if (limit !== null) { const m = el('em'); m.style.left = limit + '%'; m.title = 'Astra viewer admission limit ' + limit + unit; bar.append(m); }
    row.append(el('span', '', label), bar, el('b', '', v === null ? '—' : Math.round(v) + unit));
    return row;
  }
  function system(d) {
    if (!d) return setCard('cardSystem', { state: 'stale', pill: 'No reply', sub: 'Dashboard has no fresh reply from ATLAS', age: '' });
    const s = d.system || {}, cpu = Number(s.cpu_percent), ram = Number(s.ram_percent), temp = Number.parseFloat(String(s.temp || ''));
    const box = $('cardSystem').querySelector('[data-vis]');
    box.replaceChildren(meter('CPU', cpu, 75, '%', 75, 95), meter('RAM', ram, 80, '%', 80, 92), meter('Temp', temp, 70, '°', 70, 95));
    const over = [cpu > 75 && 'CPU', ram > 80 && 'RAM', temp > 70 && 'temperature'].filter(Boolean);
    const state = temp >= 95 ? 'fault' : over.length ? 'warn' : isNum(cpu) ? 'ok' : 'na';
    setCard('cardSystem', { state, pill: state === 'ok' ? 'Normal' : state === 'warn' ? 'Busy' : undefined,
      sub: over.length ? `${over.join(', ')} above the 3D camera admission limit` : 'Marks show the 3D camera admission limits', age: 0 });
  }

  // ---------- Battery ----------
  function battery(r) {
    const b = typeof bmsSnapshot === 'function' ? bmsSnapshot(r) : null;
    const bar = $('cardBattery').querySelector('[data-vis]');
    if (!b) {
      bar.className = 'hm-batt'; bar.firstElementChild.style.width = '0';
      return setCard('cardBattery', { state: 'na', main: '—', unit: '', sub: 'BMS reading invalid or older than 10 s. Last values are hidden.', age: ageOf(r, 'bms_status') });
    }
    const pct = Number(b.soc_percent), mode = typeof bmsMode === 'function' ? bmsMode(b) : '';
    const tone = pct <= 15 ? 'fail' : pct <= 30 ? 'warn' : '';
    bar.className = 'hm-batt ' + tone; bar.firstElementChild.style.width = Math.max(0, Math.min(100, pct)) + '%';
    const spread = Math.max(...b.cells_v) - Math.min(...b.cells_v);
    const src = typeof bmsSocSource === 'function' ? bmsSocSource(b) : '';
    const modeText = mode === 'IDLE / NEAR ZERO' ? 'Idle' : mode === 'CHARGING' ? 'Charging' : mode === 'DISCHARGING' ? 'Discharging' : mode;
    setCard('cardBattery', { state: tone === 'fail' ? 'fault' : tone ? 'warn' : 'ok', pill: tone === 'fail' ? 'Low' : tone ? 'Getting low' : modeText,
      main: Math.round(pct) + '%', unit: 'charge',
      sub: `${fx(b.voltage_v, 2)} V · ${fx(Math.abs(b.current_a), 2)} A · cells within ${fx(spread * 1000, 0)} mV${src ? ' · ' + src.replace('DALY', 'Daly').replace('COUNTER', 'counter').replace('VOLTAGE', 'voltage').replace('ESTIMATE', 'estimate') : ''}`, age: ageOf(r, 'bms_status') });
  }

  // ---------- LiDAR ----------
  let lidarView = null, lidarAt = 0, lidarBusy = false, lidarVisible = true;
  async function pollLidar() {
    if (document.hidden || lidarBusy || !lidarVisible) return;
    lidarBusy = true;
    try {
      const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 2500);
      const r = await fetch('/api/lidar-view', { cache: 'no-store', signal: ctl.signal }); clearTimeout(t);
      if (r.ok) { lidarView = await r.json(); lidarAt = Date.now(); }
    } catch (e) { /* card shows the telemetry age instead */ } finally { lidarBusy = false; }
  }
  function drawScan(cv, view) {
    const g = cv.getContext('2d'), w = cv.width, h = cv.height, cx = w / 2, cy = h / 2, R = 3.0, s = Math.min(w, h) / 2 / R;
    g.clearRect(0, 0, w, h);
    g.strokeStyle = 'rgba(128,190,236,.18)'; g.lineWidth = 1;
    for (const m of [1, 2, 3]) { g.beginPath(); g.arc(cx, cy, m * s, 0, Math.PI * 2); g.stroke(); }
    g.fillStyle = '#22B8F0';
    const pts = view && Array.isArray(view.points) ? view.points : [];
    for (const p of pts) {
      if (!Array.isArray(p) || !isNum(p[0]) || !isNum(p[1])) continue;
      const x = cx - Number(p[1]) * s, y = cy - Number(p[0]) * s;   // base_link: +X forward (up), +Y left
      if (x >= 0 && x <= w && y >= 0 && y <= h) g.fillRect(x - 1, y - 1, 2, 2);
    }
    g.fillStyle = '#E7F0F8'; g.beginPath(); g.moveTo(cx, cy - 7); g.lineTo(cx - 5, cy + 5); g.lineTo(cx + 5, cy + 5); g.closePath(); g.fill();
    g.fillStyle = '#8DA3B8'; g.font = '10px system-ui'; g.fillText('3 m', cx + 3 * s - 18 > w ? w - 22 : cx + 3 * s - 18, cy - 3);
  }
  function lidar(r) {
    const li = val(r, 'lidar') || {}, a = ageOf(r, 'lidar'), cv = $('cardLidar').querySelector('canvas');
    const viewFresh = lidarView && Date.now() - lidarAt < 5000 && lidarView.state === 'LIVE';
    drawScan(cv, viewFresh ? lidarView : null);
    const pts = Number(li.points) || 0;
    const state = a < 3 && pts > 0 ? 'ok' : a < 10 ? 'stale' : 'off';
    const c = viewFresh && lidarView.closest ? lidarView.closest : null;
    const nearest = c ? Object.entries(c).filter(([, v]) => isNum(v)).sort((x, y) => x[1] - y[1])[0] : null;
    const hz = viewFresh && isNum(lidarView.hz) ? `${fx(lidarView.hz, 1)} Hz · ` : '';
    setCard('cardLidar', { state, pill: state === 'ok' ? 'Scanning' : undefined,
      sub: state === 'off' ? 'No scan received. Check the RPLIDAR USB and service.' :
        `${hz}${pts} of ${li.total || '—'} points valid · nearest ${nearest ? fx(nearest[1], 2) + ' m ' + nearest[0] : fx(li.nearest_m, 2) + ' m'}`, age: a });
  }

  // ---------- Depth camera (Astra) ----------
  let depth = null, depthAt = 0, depthMissing = false, depthBusy = false;
  async function pollDepth() {
    if (document.hidden || depthBusy || depthMissing) return;
    depthBusy = true;
    try {
      const r = await fetch('/api/vision3d/summary', { cache: 'no-store' });
      if (r.status === 404) depthMissing = true; else if (r.ok) { depth = await r.json(); depthAt = Date.now(); }
    } catch (e) { /* shown as no reply */ } finally { depthBusy = false; renderDepth(); }
  }
  // ---------- Track A live depth picture (Astra obstacle pipeline, written about 1 Hz) ----------
  // Live only after the status file's sequence number is SEEN TO CHANGE (an old file left from a previous run never
  // counts), and only while it keeps changing (within 5 s). No clock comparison with the Jetson is needed.
  const ta = { seq: null, changedAt: 0, info: null };
  async function pollTrackA() {
    if (document.hidden) return;
    // The dashboard server occasionally resets a connection under load; one quick retry keeps the card steady.
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const r = await fetch('/v2/astra_depth_live.txt', { cache: 'no-store', signal: AbortSignal.timeout(2500) });
        if (r.ok) { const j = await r.json(); if (ta.seq !== null && j.seq !== ta.seq) { ta.changedAt = Date.now(); ta.info = j; } ta.seq = j.seq; }
        break;
      } catch (e) { if (attempt === 0) await new Promise(res => setTimeout(res, 300)); }
    }
    renderDepth();
  }
  const trackALive = () => !!ta.info && Date.now() - ta.changedAt < 8000;   // writer ~1 Hz, poll 2 s: 8 s tolerates resets
  // ---------- Full-screen viewer (3D map and depth picture). Close: x button, Esc, or click outside. ----------
  const fs = { el: null, onClose: null };
  function openFullscreen(title, body, onClose) {
    closeFullscreen();
    const ov = document.createElement('div');
    ov.setAttribute('role', 'dialog'); ov.setAttribute('aria-label', title);
    ov.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(5,10,18,.95);display:flex;flex-direction:column;padding:12px;box-sizing:border-box';
    const head = document.createElement('div');
    head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;color:#e8f1ff;font:600 16px system-ui;margin-bottom:8px';
    const h = document.createElement('span'); h.textContent = title;
    const x = document.createElement('button'); x.type = 'button'; x.textContent = '×'; x.setAttribute('aria-label', 'Close full screen');
    x.style.cssText = 'font:28px/1 system-ui;width:44px;height:44px;border-radius:10px;border:1px solid #ffffff40;background:#ffffff14;color:#fff;cursor:pointer';
    x.onclick = closeFullscreen; head.append(h, x);
    const wrap = document.createElement('div'); wrap.style.cssText = 'flex:1;min-height:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px';
    wrap.append(body); ov.append(head, wrap);
    ov.addEventListener('click', e => { if (e.target === ov) closeFullscreen(); });
    document.body.append(ov); fs.el = ov; fs.onClose = onClose || null;
  }
  function closeFullscreen() {
    if (!fs.el) return;
    fs.el.remove(); fs.el = null; if (fs.onClose) { const f = fs.onClose; fs.onClose = null; f(); }
  }
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeFullscreen(); });
  function fullscreenButton(onClick) {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = '⤢ Full screen';
    b.style.cssText = 'font:600 12px system-ui;padding:6px 10px;border-radius:8px;border:1px solid #0002;background:#ffffffcc;cursor:pointer;margin:2px 0 6px';
    b.addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); onClick(); });
    return b;
  }
  // Depth picture, full screen: large live image + the same colour scale + live text, refreshed with the card.
  const depthFs = { img: null, info: null };
  function openDepthFullscreen() {
    const box = document.createElement('div'); box.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:8px;width:100%;height:100%';
    const img = document.createElement('img'); img.alt = 'Live Astra depth view, full screen';
    img.style.cssText = 'flex:1;min-height:0;max-width:100%;object-fit:contain;image-rendering:pixelated;border-radius:12px;background:#000';
    img.src = '/v2/astra_depth_live.webp?seq=' + ta.seq;
    const lg = depthLegend(); lg.style.maxWidth = '640px'; lg.style.width = '100%'; lg.style.color = '#e8f1ff'; lg.style.fontSize = '13px';
    const info = document.createElement('div'); info.style.cssText = 'color:#b8c7da;font:13px system-ui';
    box.append(img, lg, info); depthFs.img = img; depthFs.info = info; updateDepthFullscreen();
    openFullscreen('Depth camera (Astra) — live', box, () => { depthFs.img = null; depthFs.info = null; });
  }
  function updateDepthFullscreen() {
    if (!depthFs.img) return;
    depthFs.img.src = '/v2/astra_depth_live.webp?seq=' + ta.seq;
    const i = ta.info;
    depthFs.info.textContent = trackALive() && i ? `${fx(i.valid_percent, 0)}% of the image has depth · nearest ${i.nearest_m != null ? fx(i.nearest_m, 2) + ' m' : '—'} · updates about once a second`
                                                 : 'Depth camera not running (no new picture).';
  }
  function depthImage(show) {
    const c = $('cardDepth'); if (!c) return;
    let img = c.querySelector('img[data-ta]');
    if (!show) { if (img) img.remove(); const lg = c.querySelector('[data-ta-legend]'); if (lg) lg.remove(); const fb = c.querySelector('[data-ta-fs]'); if (fb) fb.remove(); updateDepthFullscreen(); return; }
    if (!img) {
      img = document.createElement('img'); img.dataset.ta = '1'; img.alt = 'Live Astra depth view: red near, blue far';
      img.style.cssText = 'display:block;width:100%;max-width:320px;aspect-ratio:4/3;margin:6px 0;border-radius:10px;background:#000;image-rendering:pixelated';
      const sub = c.querySelector('[data-sub]'); (sub ? sub.parentNode : c).insertBefore(img, sub || null);
      img.after(depthLegend());
      img.title = 'Click for full screen'; img.style.cursor = 'zoom-in';
      img.addEventListener('click', e => { e.stopPropagation(); e.preventDefault(); openDepthFullscreen(); });
      const btn = fullscreenButton(openDepthFullscreen); btn.dataset.taFs = '1'; c.querySelector('[data-ta-legend]').after(btn);
    }
    img.src = '/v2/astra_depth_live.webp?seq=' + ta.seq;
    updateDepthFullscreen();
  }
  // Distance colour scale for the depth picture. Same colours as the picture: OpenCV COLORMAP_JET applied to
  // (1 - (d - 0.35) / 2.65) * 255 in atlas_astra_depth_preview.py, so 0.35 m = dark red ... 3.0 m = dark blue.
  function depthLegend() {
    const NEAR = 0.35, FAR = 3.0, pos = d => 100 * (d - NEAR) / (FAR - NEAR);
    const box = document.createElement('div'); box.dataset.taLegend = '1';
    box.style.cssText = 'max-width:320px;margin:2px 0 8px;font-size:11px;line-height:1.2';
    const bar = document.createElement('div');
    bar.style.cssText = 'height:12px;border-radius:6px;border:1px solid #0002;background:linear-gradient(to right,' +
      '#800000 0%,#ff0000 12.5%,#ffff00 37.5%,#00ffff 62.5%,#0000ff 87.5%,#000080 100%)';
    bar.title = 'Distance from the camera: 0.35 m (dark red) to 3 m (dark blue)';
    const ticks = document.createElement('div'); ticks.style.cssText = 'position:relative;height:14px;margin-top:2px';
    for (const d of [0.35, 1, 1.5, 2, 2.5, 3]) {
      const t = document.createElement('span'); t.textContent = (d === 0.35 ? '0.35' : String(d)) + ' m';
      const x = pos(d);
      t.style.cssText = 'position:absolute;top:0;white-space:nowrap;' +
        (x <= 0 ? 'left:0' : x >= 100 ? 'right:0' : `left:${x.toFixed(1)}%;transform:translateX(-50%)`);
      ticks.append(t);
    }
    const note = document.createElement('div'); note.style.cssText = 'opacity:.75;margin-top:1px';
    note.textContent = 'Red = near, blue = far. Black = no reading (too close, too far, shiny or dark surface).';
    box.append(bar, ticks, note);
    return box;
  }
  function renderDepth() {
    if (trackALive()) {
      depthImage(true);
      const i = ta.info, near = i.nearest_m != null ? ` · nearest ${fx(i.nearest_m, 2)} m` : '';
      // 2026-11-14: "Nav2" only when the obstacle scan really reaches Nav2 (domain 0, via the Astra bridge).
      const d = fresh(), r = d && d.ros, nav2Age = r ? ageOf(r, 'astra_nav2') : Infinity;
      if (!(nav2Age < 2)) return setCard('cardDepth', { state: 'warn', pill: 'Nav2 OFF', main: 'On', unit: '',
        sub: 'Camera works, but its obstacles are NOT reaching Nav2 (Astra bridge off). Autonomous driving is blocked until it is back.', age: '' });
      return setCard('cardDepth', { state: 'ok', pill: 'Live · Nav2', main: 'On', unit: '',
        sub: `Obstacle layer for Nav2 · red near, blue far (0.35-3 m), black = no reading · ${fx(i.valid_percent, 0)}% valid${near}`, age: '' });
    }
    depthImage(false);
    if (depthMissing) return setCard('cardDepth', { state: 'unverified', pill: 'Open lab', main: 'Vision Lab', unit: '', sub: 'Live depth status is shown in the 3D Vision Lab.', age: '' });
    if (!depth || Date.now() - depthAt > 15000) return setCard('cardDepth', { state: 'na', main: '—', unit: '', sub: 'No reply from the Vision Lab service', age: '' });
    const s = String(depth.state || 'OFF'), cpu = depth.blocked_cpu_percent, lim = depth.cpu_limit_percent;
    if (s === 'ACTIVE') return setCard('cardDepth', { state: 'ok', pill: 'Streaming', main: isNum(depth.depth_fps) ? fx(depth.depth_fps, 1) : 'Live', unit: isNum(depth.depth_fps) ? 'fps' : '', sub: 'Uncalibrated depth only · 3D geometry disabled', age: '' });
    if (s === 'RESOURCE BLOCKED') return setCard('cardDepth', { state: 'warn', pill: 'Blocked', main: 'Stopped', unit: '',
      sub: isNum(cpu) ? `Last start stopped safely at ${fx(cpu, 1)}% CPU (limit ${lim || 75}%)` : 'Last start stopped safely by the resource guard', age: '' });
    if (s === 'CHECKING') return setCard('cardDepth', { state: 'unverified', pill: 'Starting', main: 'Checking', unit: '', sub: 'Safety and resource admission running', age: '' });
    // 25 Oct 2026: live USB presence (read-only sysfs on the Jetson), shown like the other devices.
    const u = depth.usb || null, us = u ? String(u.state || 'UNKNOWN') : null, port = u && u.port ? ` (USB ${u.port})` : '';
    if (us === 'NOT_DETECTED') return setCard('cardDepth', { state: 'off', pill: u.enumeration_failure ? 'USB failed' : 'Disconnected', main: 'No camera', unit: '',
      sub: u.enumeration_failure ? String(u.detail) : 'Astra not detected on USB. Check its USB cable.', age: '' });   // 26 Oct: failed USB start explained
    if (us === 'NO_ACCESS') return setCard('cardDepth', { state: 'warn', pill: 'No access', main: 'Connected', unit: '', sub: `Astra connected${port}, but the access rule does not cover this port.`, age: '' });
    if (us === 'PARTIAL' || us === 'AMBIGUOUS' || us === 'MISMATCH') return setCard('cardDepth', { state: 'warn', pill: 'Check USB', main: 'Check', unit: '', sub: String(u.detail || 'Astra USB layout not recognised') + '. Reseat the camera cable.', age: '' });
    if (us === 'CONNECTED') return setCard('cardDepth', { state: 'ok', pill: 'Connected', main: 'Off', unit: '', sub: `Camera connected${port}. Off — start it in the 3D Vision Lab.`, age: '' });
    setCard('cardDepth', { state: 'idle', pill: 'Off', main: 'Off', unit: '', sub: 'Camera off. Start it in the 3D Vision Lab.', age: '' });
  }

  // ---------- Encoders ----------
  const lastCounts = {};
  function encoders(r) {
    const h = parse(val(r, 'encoder_health')) || {}, a = ageOf(r, 'encoder_health');
    const excluded = new Set((h.excluded_encoders || []).map(Number)), box = $('cardEncoders').querySelector('[data-vis]');
    const wheels = [[3, 'Front left'], [4, 'Front right'], [1, 'Rear left'], [2, 'Rear right']];
    box.replaceChildren(...wheels.map(([m, name]) => {
      const v = val(r, 'enc_m' + m), prev = lastCounts[m]; lastCounts[m] = v;
      const dir = isNum(v) && isNum(prev) ? (Number(v) > Number(prev) ? '▲' : Number(v) < Number(prev) ? '▼' : '·') : '·';
      const w = el('div', 'hm-wheel' + (excluded.has(m) ? ' excluded' : ''));
      w.title = `M${m} ${name}${excluded.has(m) ? ' — excluded by encoder consensus' : ''}`;
      w.append(el('b', '', isNum(v) ? String(v) : '—'), el('span', 'dir', dir), el('span', '', name));
      return w;
    }));
    const link = h.link_state, st = String(h.state || '');
    const state = a > 5 || link === 'STALE' ? 'stale' : excluded.size || /FAULT|CRITICAL|BLOCK/i.test(st) ? 'fault' : st === 'READY' ? 'ok' : st ? 'warn' : 'na';
    setCard('cardEncoders', { state, pill: state === 'ok' ? 'All 4 OK' : state === 'fault' ? `${excluded.size || ''} excluded`.trim() : undefined,
      sub: state === 'na' ? 'No encoder health report' : excluded.size ? `Consensus excluded ${[...excluded].map(m => 'M' + m).join(', ')}. Odometry may be unreliable.` :
        `Consensus ${String(h.consensus_state || '—').toLowerCase()} · link ${String(link || '—').toLowerCase()}`, age: a });
  }

  // ---------- IMU ----------
  function drawAttitude(cv, roll, pitch, yaw) {
    const g = cv.getContext('2d'), w = cv.width, h = cv.height, cx = w / 2, cy = h / 2, R = w / 2 - 4;
    g.clearRect(0, 0, w, h); g.save(); g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.clip();
    g.fillStyle = '#0B2236'; g.fillRect(0, 0, w, h);
    if (isNum(roll) && isNum(pitch)) {
      g.translate(cx, cy); g.rotate(-Number(roll) * Math.PI / 180);
      const off = Math.max(-R, Math.min(R, Number(pitch) * R / 45));
      g.fillStyle = '#3A2A12'; g.fillRect(-w, off, 2 * w, h);
      g.strokeStyle = '#E7F0F8'; g.lineWidth = 2; g.beginPath(); g.moveTo(-R, off); g.lineTo(R, off); g.stroke();
      g.setTransform(1, 0, 0, 1, 0, 0);
    }
    g.restore();
    g.strokeStyle = 'rgba(128,190,236,.5)'; g.lineWidth = 2; g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.stroke();
    g.strokeStyle = '#F2B33D'; g.lineWidth = 3; g.beginPath(); g.moveTo(cx - 14, cy); g.lineTo(cx - 5, cy); g.moveTo(cx + 5, cy); g.lineTo(cx + 14, cy); g.stroke();
    if (isNum(yaw)) {
      const t = -Number(yaw) * Math.PI / 180 - Math.PI / 2;   // heading needle on the rim
      g.fillStyle = '#22B8F0'; g.beginPath(); g.arc(cx + Math.cos(t) * (R - 5), cy + Math.sin(t) * (R - 5), 4, 0, Math.PI * 2); g.fill();
    }
  }
  function imu(r) {
    const full = val(r, 'imu_full') || {}, a = Math.min(ageOf(r, 'imu_full'), ageOf(r, 'imu_heading'), ageOf(r, 'imu_yaw'));
    const roll = val(r, 'imu_roll'), pitch = val(r, 'imu_pitch'), yaw = val(r, 'imu_yaw');
    drawAttitude($('cardImu').querySelector('canvas'), roll, pitch, yaw);
    const fused = String(full.navigation_fusion || '').startsWith('ENABLED');
    const state = a < 4 ? (fused ? 'ok' : 'unverified') : a < 15 ? 'stale' : 'off';
    setCard('cardImu', { state, pill: state === 'ok' ? 'Live' : state === 'unverified' ? 'Monitoring' : undefined,
      main: isNum(yaw) ? `${fx(yaw, 0)}°` : '—',
      sub: state === 'off' ? 'No IMU data. Check the IM10A USB and service.' :
        `Roll ${fx(roll, 1)}° · pitch ${fx(pitch, 1)}° · ${fused ? 'gyro used by EKF' : 'not used for navigation'}`, age: a });
  }

  // ---------- Network ----------
  function network(d) {
    const net = (d && d.network) || {}, fb = net.fallback || {}, checks = fb.checks || {}, box = $('cardNetwork').querySelector('[data-vis]');
    const mode = String(fb.mode || '').toUpperCase();
    const route = (name, key, active) => { const c = checks[key]; const e = el('span', 'hm-route' + (c ? (c.ok ? ' ok' : ' fail') : '') + (active ? ' active' : ''), name); e.title = c ? c.reason || '' : 'Not checked'; return e; };
    box.replaceChildren(route('Wi-Fi', 'wifi', mode === 'WIFI'), route('Cellular', 'cellular', mode === 'CELLULAR'), el('span', 'hm-route' + (net.tailscale_ip ? ' ok' : ''), 'Tailscale'));
    const anyOk = Object.values(checks).some(c => c && c.ok);
    const state = !d ? 'stale' : net.route ? (anyOk ? 'ok' : 'warn') : 'off';
    setCard('cardNetwork', { state, pill: state === 'ok' ? 'Online' : state === 'warn' ? 'No internet check' : undefined,
      main: String(net.route || 'No route').replace(/\s*\(.*\)$/, ''), sub: `${net.wifi_ip || '—'} · ${fb.hotspot_active ? 'rescue hotspot ON' : 'rescue hotspot off'}`,
      age: isNum(fb.time) ? Math.max(0, Date.now() / 1000 - Number(fb.time)) : '' });
  }

  // ---------- top bar safety + mission facts ----------
  function safety(d) {
    const box = $('hmSafety'), t = $('hmSafetyText'), s = $('hmSafetySub'), r = d && d.ros;
    const p = r ? parse(val(r, 'control_policy')) : null, a = r ? ageOf(r, 'control_policy') : Infinity;
    const mode = $('hmMode');
    if (!p || a > 3) {
      box.className = 'hm-safety unknown'; t.textContent = 'Stop state unknown'; s.textContent = d ? 'Command mux report is stale' : 'No fresh reply from ATLAS';
      mode.textContent = 'Mode unknown'; mode.className = 'chip warn'; return null;
    }
    if (p.stop_latched) { box.className = 'hm-safety latched'; t.textContent = 'E-STOP latched'; s.textContent = String(p.stop_reason || 'Drive commands are blocked'); }
    else if (p.commission_armed) { box.className = 'hm-safety armed'; t.textContent = 'Commissioning armed'; s.textContent = `${fx(p.commission_remaining_s, 0)} s remaining`; }
    else { box.className = 'hm-safety'; t.textContent = 'Stop released'; s.textContent = 'Manual drive commands accepted'; }
    mode.textContent = p.manual_only ? 'Manual only' : 'Autonomy permitted'; mode.className = 'chip ' + (p.manual_only ? 'ok' : 'warn');
    mode.title = 'Command source: ' + String(p.source || '—');
    return p;
  }
  function facts(d, p) {
    const r = d && d.ros, set = (id, text, tone) => { const e = $(id); if (!e) return; e.textContent = text; e.className = tone || ''; };
    if (!r) { ['hmMission', 'hmControl', 'hmPid'].forEach(id => set(id, 'Unknown', 'warn')); }
    else {
      const m = val(r, 'mission_status'); set('hmMission', ageOf(r, 'mission_status') < 5 ? String(m || '—') : 'No recent report', m === 'READY' ? 'ok' : 'warn');
      set('hmControl', p ? `${p.manual_only ? 'Manual only' : 'Autonomy permitted'} · source ${String(p.source || '—').toLowerCase()}` : 'Unknown', p ? '' : 'warn');
      const pid = parse(val(r, 'drive_pid')) || {};
      set('hmPid', pid.state ? `${String(pid.state).toLowerCase()}${pid.inhibited_reason ? ' · ' + String(pid.inhibited_reason).replace(/_/g, ' ') : ''}${pid.fault_reason ? ' · ' + pid.fault_reason : ''}` : 'No report', pid.fault_reason ? 'fail' : '');
    }
    const loc = $('v2Loc');   // mirrors the chip shell.js computes from /api/map (same rules as the Live map)
    if (loc) set('hmLoc', loc.textContent, /\bok\b/.test(loc.className) ? 'ok' : /\bfail\b/.test(loc.className) ? 'fail' : 'warn');
  }

  // ---------- render loop ----------
  function render() {
    const d = fresh(), r = d && d.ros;
    const p = safety(d); facts(d, p); system(d);
    if (r) { battery(r); lidar(r); encoders(r); imu(r); }
    else for (const id of ['cardBattery', 'cardLidar', 'cardEncoders', 'cardImu']) setCard(id, { state: 'stale', pill: 'No reply', sub: 'No fresh reply from ATLAS. Values hidden.', age: '' });
    network(d); renderDepth();
  }

  // ---------- layout helpers ----------
  window.hmOpen = id => { const e = $(id); if (!e) return; e.open = true; e.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  for (const c of document.querySelectorAll('.hm-card')) {
    const go = () => { if (c.dataset.href) location.href = c.dataset.href; else if (c.dataset.detail && typeof openDetail === 'function') openDetail(c.dataset.detail); };
    c.addEventListener('click', go);
    c.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    c.setAttribute('role', 'button');
  }
  for (const dr of document.querySelectorAll('.hm-drawer[id^="drawer"]')) {
    if (store.get('atlasHomeOpen:' + dr.id) === '1') dr.open = true;
    dr.addEventListener('toggle', () => store.set('atlasHomeOpen:' + dr.id, dr.open ? '1' : '0'));
  }
  const menu = document.querySelector('.hm-menu');
  if (menu) document.addEventListener('click', e => { if (menu.open && !menu.contains(e.target)) menu.open = false; });
  // location-check.js inserts its panel after the header; keep it with the position facts instead.
  const slot = $('hmLocSlot');
  const adopt = () => { const box = document.querySelector('.atlas-location'); if (box && slot && box.parentElement !== slot) { slot.append(box); return true; } return false; };
  if (!adopt()) { const mo = new MutationObserver(() => { if (adopt()) mo.disconnect(); }); mo.observe(document.body, { childList: true }); setTimeout(() => mo.disconnect(), 15000); }
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { for (const e of es) lidarVisible = e.isIntersecting; }).observe($('cardLidar'));
  // Map preview: the saved map image only (no live pose); refreshed slowly and only while the page is visible.
  setInterval(() => { if (!document.hidden) $('hmMap').src = '/map.png?home=' + Date.now(); }, 60000);

  // ---------- Live 3D map window (RTAB-Map mapping sessions; feed: scripts/atlas_map3d_live.py) ----------
  // web/v2/map3d_live.txt is rewritten every ~3 s while mapping. "Mapping" only when its sequence number is SEEN to
  // change (an old file means "last map"). Drawn on a 2D canvas: no external libraries (the rover may be offline).
  const m3 = { seq: null, changedAt: 0, d: null, pts: null, yaw: 0.7, pitch: 0.95, zoom: 1, drag: null, visible: true, lastDraw: 0 };
  async function pollMap3d() {
    if (document.hidden) return;
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const r = await fetch('/v2/map3d_live.txt', { cache: 'no-store', signal: AbortSignal.timeout(4000) });
        if (r.status === 404) { m3.d = null; break; }
        if (r.ok) {
          const j = await r.json();
          if (m3.seq !== null && j.seq !== m3.seq && j.live !== false) m3.changedAt = Date.now();   // live:false = stored map
          if (j.seq !== m3.seq || !m3.pts) {
            m3.d = j; m3.pts = Int16Array.from(j.points_cm || []);
            m3.rgb = Array.isArray(j.rgb) && j.rgb.length * 3 === m3.pts.length
              ? j.rgb.map(c => '#' + (c >>> 0).toString(16).padStart(6, '0')) : null;   // real colour (colour maps)
          }
          m3.seq = j.seq;
        }
        break;
      } catch (e) { if (attempt === 0) await new Promise(res => setTimeout(res, 300)); }
    }
    renderMap3dCard();
  }
  function renderMap3dCard() {
    const live = !!m3.d && m3.d.live !== false && Date.now() - m3.changedAt < 12000;
    if (!m3.d) return setCard('cardMap3d', { state: 'idle', pill: 'Off', sub: 'No 3D map yet. It appears here live during a 3D mapping session.', age: '' });
    const n = m3.d.points_shown || 0, tot = m3.d.points_total || 0;
    const when = m3.d.unix ? new Date(m3.d.unix * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '?';
    if (live) setCard('cardMap3d', { state: 'ok', pill: 'Mapping', sub: `Live · ${n.toLocaleString()} of ${tot.toLocaleString()} points (5 cm) · drag to rotate`, age: '' });
    else setCard('cardMap3d', { state: 'idle', pill: m3.d.name ? 'Stored map' : 'Last map', sub: `${m3.d.name ? m3.d.name + ' · ' : 'Not mapping now · last map ' + when + ' · '}${n.toLocaleString()} points · drag to rotate`, age: '' });
  }
  function heightColor(z) {   // 0 m blue -> 0.5 green -> 1.0 yellow -> 1.5+ red
    const t = Math.max(0, Math.min(1, z / 1.5)), h = 230 - 230 * t;
    return `hsl(${h},90%,${55 - 5 * t}%)`;
  }
  function drawMap3d(target) {
    const c = target || document.querySelector('#cardMap3d canvas[data-map3d]'); if (!c) return;
    const big = !!target, dot = big ? 3 : 2;
    const w = c.clientWidth, h = c.clientHeight; if (!w || !h) return;
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const g = c.getContext('2d'); g.fillStyle = '#0b1622'; g.fillRect(0, 0, w, h);
    const p = m3.pts; if (!p || p.length < 3) { g.fillStyle = '#7f93a8'; g.font = '12px system-ui'; g.fillText('No 3D map yet', 12, 22); return; }
    let minx = 1e9, maxx = -1e9, miny = 1e9, maxy = -1e9;
    for (let i = 0; i < p.length; i += 3) { const x = p[i], y = p[i + 1]; if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y; }
    const cx0 = (minx + maxx) / 200, cy0 = (miny + maxy) / 200, ext = Math.max(1, (maxx - minx) / 100, (maxy - miny) / 100);
    const s = Math.min(w, h) / (ext * 1.15) * m3.zoom;
    const cy = Math.cos(m3.yaw), sy = Math.sin(m3.yaw), cp = Math.cos(m3.pitch), sp = Math.sin(m3.pitch);
    const proj = (x, y, z) => { x -= cx0; y -= cy0; const xr = cy * x - sy * y, yr = sy * x + cy * y; return [w / 2 + xr * s, h * 0.58 + (sp * yr - cp * z) * s]; };
    const order = [];   // draw far points first so near ones stay on top
    for (let i = 0; i < p.length; i += 3) {
      const x = p[i] / 100 - cx0, y = p[i + 1] / 100 - cy0;
      order.push([sy * x + cy * y, i]);
    }
    order.sort((a, b) => a[0] - b[0]);   // smaller yr = farther from the viewer
    for (const [, i] of order) {
      const z = p[i + 2] / 100, q = proj(p[i] / 100, p[i + 1] / 100, z);
      g.fillStyle = m3.rgb ? m3.rgb[i / 3] : heightColor(z); g.fillRect(q[0], q[1], dot, dot);
    }
    const path = m3.d && m3.d.path_cm;   // driven route (white line), if the feed provides it
    if (path && path.length >= 6) { g.strokeStyle = '#ffffffcc'; g.lineWidth = 2; g.beginPath(); for (let i = 0; i < path.length; i += 3) { const q = proj(path[i] / 100, path[i + 1] / 100, 0); i ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1]); } g.stroke(); }
    const r = m3.d && m3.d.robot_cm_deg;
    if (r) {   // rover marker: triangle pointing along its heading
      const yaw = r[2] * Math.PI / 180, rx = r[0] / 100, ry = r[1] / 100, L = 0.3;
      const a = proj(rx + L * Math.cos(yaw), ry + L * Math.sin(yaw), 0), b = proj(rx + 0.15 * Math.cos(yaw + 2.5), ry + 0.15 * Math.sin(yaw + 2.5), 0),
            d = proj(rx + 0.15 * Math.cos(yaw - 2.5), ry + 0.15 * Math.sin(yaw - 2.5), 0);
      g.fillStyle = '#ffffff'; g.strokeStyle = '#0b1622'; g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.lineTo(d[0], d[1]); g.closePath(); g.fill(); g.stroke();
    }
  }
  function bindMap3dControls(c, redraw) {   // drag = rotate, wheel = zoom (shared view for card and full screen)
    const stop = e => e.stopPropagation();
    c.addEventListener('click', stop);
    c.addEventListener('pointerdown', e => { stop(e); m3.drag = [e.clientX, e.clientY]; c.setPointerCapture(e.pointerId); c.style.cursor = 'grabbing'; });
    c.addEventListener('pointermove', e => { if (!m3.drag) return; stop(e); m3.yaw += (e.clientX - m3.drag[0]) * 0.01; m3.pitch = Math.max(0.15, Math.min(1.5, m3.pitch + (e.clientY - m3.drag[1]) * 0.01)); m3.drag = [e.clientX, e.clientY]; redraw(); });
    const end = () => { m3.drag = null; c.style.cursor = 'grab'; };
    c.addEventListener('pointerup', end); c.addEventListener('pointercancel', end);
    c.addEventListener('wheel', e => { e.preventDefault(); stop(e); m3.zoom = Math.max(0.3, Math.min(8, m3.zoom * Math.exp(-e.deltaY * 0.001))); redraw(); }, { passive: false });
  }
  function openMap3dFullscreen() {
    const box = document.createElement('div'); box.style.cssText = 'display:flex;flex-direction:column;width:100%;height:100%;gap:6px';
    const big = document.createElement('canvas'); big.setAttribute('aria-label', '3D map, full screen. Drag to rotate, wheel to zoom.');
    big.style.cssText = 'flex:1;min-height:0;width:100%;border-radius:12px;background:#0b1622;touch-action:none;cursor:grab';
    const note = document.createElement('div'); note.style.cssText = 'color:#b8c7da;font:13px system-ui;text-align:center';
    note.textContent = m3.rgb
      ? 'Drag to rotate · scroll to zoom · real camera colours · white line = route'
      : 'Drag to rotate · scroll to zoom · colour = height (blue floor → red 1.5 m+) · white line = route · ▲ = rover';
    box.append(big, note); bindMap3dControls(big, () => drawMap3d(big)); m3.big = big;
    openFullscreen('3D map' + (m3.d && m3.d.name ? ' — ' + m3.d.name : ''), box, () => { m3.big = null; });
    requestAnimationFrame(() => drawMap3d(big));
    setTimeout(() => { if (m3.big === big) drawMap3d(big); }, 250);   // redraw once the overlay has its final size
  }
  (function setupMap3d() {
    const c = document.querySelector('#cardMap3d canvas[data-map3d]'); if (!c) return;
    bindMap3dControls(c, () => drawMap3d());
    c.addEventListener('dblclick', e => { e.stopPropagation(); openMap3dFullscreen(); });
    c.title = 'Drag to rotate · double-click for full screen';
    c.after(fullscreenButton(openMap3dFullscreen));
    if ('IntersectionObserver' in window) new IntersectionObserver(es => { for (const x of es) m3.visible = x.isIntersecting; }).observe(c);
    const loop = t => {   // slow auto-rotation (~10 fps) while visible and not being dragged
      if (!document.hidden && (m3.visible || m3.big) && m3.pts && t - m3.lastDraw > 100) { if (!m3.drag) m3.yaw += 0.006; if (m3.visible) drawMap3d(); if (m3.big) drawMap3d(m3.big); m3.lastDraw = t; }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  })();

  setInterval(render, 1000); setInterval(pollLidar, 1000); setInterval(pollDepth, 5000); setInterval(pollTrackA, 2000); setInterval(pollMap3d, 3000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { pollLidar(); pollDepth(); } });
  render(); pollLidar(); pollDepth(); pollTrackA(); pollMap3d();
})();
