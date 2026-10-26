/* ATLAS Camera settings page (issue #11). Read-only summary by default; changes only through the Settings dialog.
 * GET /api/cameras/summary, GET /api/cameras/<cam>/capabilities, POST /api/cameras/<cam> {validate|apply|reset}.
 * Nothing here starts a camera. Astra settings are used at the next Vision Lab Start; Pi Camera Apply restarts the
 * Pi camera only while ATLAS is parked (the Jetson enforces this and explains any refusal). */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), api = '/api/cameras/';
  const CARD = { astra: $('camAstra'), picam: $('camPicam') };
  let summary = null, caps = {}, dlgCam = null, validateTimer = null, busy = false, measuring = false, lastMeasure = null;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const mode = m => esc(String(m).replace('x', ' × ').replace('@', ' @ '));
  const num = v => typeof v === 'number' && Number.isFinite(v);

  async function get(path) {
    const r = await fetch(api + path, { cache: 'no-store' });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(j.error || ('HTTP ' + r.status));
    return j;
  }
  async function post(cam, body) {
    const r = await fetch(api + cam, { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-Atlas-Camera': '1' }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(j.error || ('HTTP ' + r.status));
    return j;
  }
  function chip(el, cls, text) { el.className = 'chip' + (cls ? ' ' + cls : ''); el.textContent = text; }
  function q(cam, sel) { return CARD[cam].querySelector(sel); }

  // ---------- summary cards ----------
  const ASTRA_CONN = { CONNECTED: ['ok', 'Connected'], NOT_DETECTED: ['fail', 'Disconnected'], NO_ACCESS: ['warn', 'No access'],
    PARTIAL: ['warn', 'Check USB'], AMBIGUOUS: ['warn', 'Check USB'], MISMATCH: ['warn', 'Check USB'] };
  function renderAstra(a) {
    const c = a.usb_start_failed ? ['fail', 'USB start failed'] : (ASTRA_CONN[a.connection] || ['', 'Unknown']);
    chip(q('astra', '[data-conn]'), c[0], c[1]);
    const st = a.session_state;
    chip(q('astra', '[data-stream]'), st === 'ACTIVE' ? 'ok' : st === 'CHECKING' ? 'warn' : '', st === 'ACTIVE' ? 'Streaming' : st === 'CHECKING' ? 'Starting' : 'Idle');
    q('astra', '[data-dev]').textContent = [a.device || 'USB port unknown', a.connection_detail && a.connection !== 'CONNECTED' ? a.connection_detail : ''].filter(Boolean).join(' · ');
    const s = a.saved;
    q('astra', '[data-current]').innerHTML = `Depth ${mode(s.depth)} · RGB ${mode(s.color)} · IR ${mode(s.ir)} <small>${a.customised ? 'Your saved settings' : 'Defaults'}, used at the next Vision Lab Start.</small>`;
    const f = a.measured_fps || {}, cf = a.configured_fps || {};
    const live = ['depth', 'rgb', 'ir'].filter(k => num(f[k])).map(k => `${k.toUpperCase()} ${f[k].toFixed(1)} received (set ${cf[k]})`);
    q('astra', '[data-fps]').innerHTML = live.length ? esc(live.join(' · ')) + `<small>${esc(a.measured_note)}</small>` : '<small>Shown while a Vision Lab session is running.</small>';
    const r = a.recommended.settings;
    q('astra', '[data-rec]').textContent = `Depth ${r.depth.replace('x', ' × ').replace('@', ' @ ')} · RGB ${r.color.replace('x', ' × ').replace('@', ' @ ')} · IR ${r.ir.replace('x', ' × ').replace('@', ' @ ')}`;
    q('astra', '[data-recwhy]').textContent = a.recommended.reason;
  }
  function renderPicam(p) {
    chip(q('picam', '[data-conn]'), p.connection === 'CONNECTED' ? 'ok' : 'fail', p.connection === 'CONNECTED' ? 'Connected' : 'Camera service ' + String(p.service || 'unknown'));
    chip(q('picam', '[data-stream]'), p.service === 'active' ? 'ok' : '', p.service === 'active' ? 'Running' : 'Stopped');
    const run = p.running || {}, s = p.saved;
    q('picam', '[data-dev]').textContent = p.device;
    const sensor = num(run.sensor_mode) ? ` · sensor mode ${run.sensor_mode}${run.stream_w ? ` (${run.stream_w} × ${run.stream_h}, up to ${num(run.sensor_fps) ? Math.round(run.sensor_fps) : '?'} fps)` : ''}` : '';
    const now = num(run.width) ? `${run.width} × ${run.height} @ ${run.framerate} fps${sensor}` : 'Running settings not reported yet';
    const differs = num(run.width) && (run.width !== s.width || run.height !== s.height || run.framerate !== s.framerate);
    q('picam', '[data-current]').innerHTML = esc(now) + `<small>${differs ? 'Saved settings differ from the running camera.' : (p.customised ? 'Your saved settings.' : 'Defaults.')}</small>`;
    const cfg = p.configured_fps || run.framerate || s.framerate;
    if (measuring) return renderPicamTail(p);
    q('picam', '[data-fps]').innerHTML = num(p.measured_fps)
      ? `${p.measured_fps.toFixed(1)} fps <small>Measured from camera frame timestamps; configured ${cfg} fps.</small>`
      : (lastMeasure ? measureText(lastMeasure, cfg) : `<button class="btn ghost cs-measure" type="button" data-measure>Measure (3 s)</button><small>Configured ${cfg} fps. ${esc(p.measured_note)}</small>`);
    renderPicamTail(p);
  }
  function measureText(m, cfg) {
    return `${m.source_fps.toFixed(1)} fps <small>Measured ${new Date(m.at).toLocaleTimeString()} over ${m.window_s} s (${m.frames} frames, camera timestamps); configured ${cfg} fps. <button class="btn ghost cs-measure" type="button" data-measure>Measure again</button></small>`;
  }
  function renderPicamTail(p) {
    const r = p.recommended.settings;
    q('picam', '[data-rec]').textContent = `${r.width} × ${r.height} @ ${r.framerate} fps`;
    q('picam', '[data-recwhy]').textContent = p.recommended.reason;
  }
  async function refresh() {
    if (document.hidden) return;
    try { summary = await get('summary'); renderAstra(summary.astra); renderPicam(summary.picam); }
    catch (e) { for (const cam of ['astra', 'picam']) { chip(q(cam, '[data-conn]'), '', 'No reply'); q(cam, '[data-dev]').textContent = e.message; } }
  }

  // ---------- capabilities ----------
  function badges(list, verified, notServed) {
    if (!list || !list.length) return '<span class="cs-badge">none reported</span>';
    return list.map(m => `<span class="cs-badge${verified && verified[m] ? ' ok' : ''}" title="${esc(verified && verified[m] || 'Reported by the camera; not yet measured on ATLAS')}">${mode(m)}</span>`).join('')
      + (notServed || []).map(m => `<span class="cs-badge off" title="Advertised but never delivered by this unit">${mode(m)}</span>`).join('');
  }
  function renderCaps(cam, c) {
    const box = q(cam, '[data-caps]');
    if (cam === 'astra') {
      const d = c.detected, ctl = d.controls;
      box.innerHTML = `<table>
        <tr><th>Depth (detected)</th><td>${badges(d.depth, c.verified.depth)}</td></tr>
        <tr><th>RGB (detected)</th><td>${badges(d.color, c.verified.color)}</td></tr>
        <tr><th>IR (detected)</th><td>${badges(d.ir, c.verified.ir, d.not_served.ir)}</td></tr>
        <tr><th>Hardware controls</th><td>${Object.entries({ 'IR gain': ctl.ir_gain, 'IR exposure': ctl.ir_exposure, 'Laser on/off': ctl.laser_on_off, 'RGB-depth registration': ctl.depth_registration })
          .map(([k, v]) => `<span class="cs-badge${v ? ' ok' : ' off'}">${esc(k)}</span>`).join('')}</td></tr>
        <tr><th>Manufacturer maximum</th><td>Depth ${esc(c.manufacturer.depth_max)}; RGB ${esc(c.manufacturer.rgb)}<br><small>${esc(c.manufacturer.note)}</small></td></tr>
        <tr><th>Pixel formats</th><td><small>Depth: ${esc(c.formats.depth)}<br>IR: ${esc(c.formats.ir)}<br>RGB: ${esc(c.formats.color)}</small></td></tr>
        <tr><th>Source</th><td><small>${esc(d.source.depth_ir)}. Detected ${esc(d.detected_at)}. RGB: ${esc(d.source.color)}.${d.serial ? ' Serial ' + esc(d.serial) + '.' : ''}</small>
          <br><button class="btn ghost cs-measure" type="button" data-detect>Re-detect modes (read-only)</button> <small data-detectmsg></small></td></tr></table>
        <p class="cs-note">Green = measured on this ATLAS. Struck through = advertised but not delivered. Registration is disabled until the calibration is validated.</p>`;
    } else {
      const d = c.detected;
      box.innerHTML = `<table>
        <tr><th>Sensor modes (detected)</th><td>${d.modes.map(m => `<span class="cs-badge">${m.index}: ${m.width} × ${m.height} up to ${Math.round(m.max_fps)} fps</span>`).join('') || 'none reported yet'}</td></tr>
        <tr><th>Gain / exposure</th><td>${d.modes[0] ? `Analogue gain ${d.modes[0].gain[0]}–${d.modes[0].gain[1]}× · exposure ${(d.modes[0].exposure_ns[0] / 1e6).toFixed(1)}–${(d.modes[0].exposure_ns[1] / 1e6).toFixed(0)} ms` : '—'}</td></tr>
        <tr><th>Pixel format</th><td><small>${esc(c.formats)}</small></td></tr>
        <tr><th>Not available here</th><td>${Object.entries(c.unsupported).map(([k, v]) => `<span class="cs-badge off" title="${esc(v)}">${esc(k)}</span>`).join('')}</td></tr>
        <tr><th>Manufacturer modes</th><td>${c.manufacturer.modes.map(esc).join(' · ')}<br><small>${esc(c.manufacturer.note)}</small></td></tr>
        <tr><th>Source</th><td><small>${esc(d.source)}</small></td></tr></table>`;
    }
  }
  async function loadCaps(cam) {
    try { caps[cam] = await get(cam + '/capabilities'); renderCaps(cam, caps[cam]); }
    catch (e) { q(cam, '[data-caps]').textContent = 'Capabilities unavailable: ' + e.message; }
    return caps[cam];
  }

  // ---------- settings dialog ----------
  function field(label, control, hint = '', disabled = false) {
    return `<div class="cs-field${disabled ? ' disabled' : ''}"><label>${esc(label)}</label>${control}<span class="cs-hint">${hint}</span></div>`;
  }
  function select(name, options, value, disabled = false) {
    return `<select name="${name}"${disabled ? ' disabled' : ''}>${options.map(([v, t, off]) => `<option value="${esc(v)}"${String(v) === String(value) ? ' selected' : ''}${off ? ' disabled' : ''}>${esc(t)}</option>`).join('')}</select>`;
  }
  function range(name, spec, value) {
    return `<input type="range" name="${name}" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${value}"><output>${value}</output>`;
  }
  function astraForm(c, s) {
    const mb = c.mbps || {}, budget = c.usb_budget_mbps || 32;
    const opt = (list, ver, kind) => list.map(m => { const need = (mb[kind] || {})[m], over = num(need) && need > budget;
      return [m, m.replace('x', ' × ').replace('@', ' @ ') + ' fps' + (num(need) ? `  · ${need} MB/s` : '') + (over ? '  · too much for USB 2.0' : '') + (ver && ver[m] ? '  ✓ measured' : ''), over]; });
    const d = c.detected;
    return `<div class="cs-group"><h3>STREAM MODES</h3>
      ${field('Depth', select('depth', opt(d.depth.length ? d.depth : [s.depth], c.verified.depth, 'depth'), s.depth))}
      ${field('RGB (MJPEG)', select('color', opt(d.color.length ? d.color : [s.color], c.verified.color, 'color'), s.color))}
      ${field('Infrared', select('ir', opt(d.ir.length ? d.ir : [s.ir], c.verified.ir, 'ir'), s.ir))}
      <p class="cs-note" data-bw>USB 2.0 budget ${budget} MB/s for the streams a session uses together.</p>
      <p class="cs-note">Used at the next Vision Lab Start. The camera is never restarted by Apply. Higher modes cost more CPU and USB bandwidth; the existing 75% CPU, 80% RAM and 70 °C guards still stop a session safely.</p></div>
      <div class="cs-group"><h3>NOT SUPPORTED BY THIS UNIT</h3>
      ${field('IR gain', '<select disabled><option>Not supported</option></select>', '', true)}
      ${field('IR exposure', '<select disabled><option>Not supported</option></select>', '', true)}
      ${field('Laser on/off', '<select disabled><option>Not supported</option></select>', '', true)}</div>`;
  }
  function picamForm(c, s) {
    const d = c.detected, ctl = c.controls;
    const sm = [['-1', 'Auto (Argus picks)']].concat(d.modes.map(m => [String(m.index), `${m.index}: ${m.width} × ${m.height} up to ${Math.round(m.max_fps)} fps`]));
    const o = c.options[String(s.sensor_mode)] || c.options['-1'] || { sizes: [], max_fps: {} };
    const size = `${s.width}x${s.height}`, maxfps = o.max_fps[size] || '?';
    const en = (name) => select(name, Object.entries(ctl[name].enum), s[name]);
    const tog = (name) => `<input type="checkbox" name="${name}"${s[name] ? ' checked' : ''}>`;
    return `<div class="cs-group"><h3>MODE</h3>
      ${field('Sensor mode', select('sensor_mode', sm, s.sensor_mode))}
      ${field('Resolution', select('size', o.sizes.map(z => [z, z.replace('x', ' × ')]), size))}
      ${field('Frame rate', `<input type="number" name="framerate" min="1" max="${maxfps}" step="1" value="${s.framerate}">`, `max ${maxfps}`)}
      <p class="cs-note">Measured FPS can be lower than the configured rate.</p></div>
      <div class="cs-group"><h3>IMAGE</h3>
      ${field(ctl.exposure_compensation.label, range('exposure_compensation', ctl.exposure_compensation, s.exposure_compensation))}
      ${field(ctl.saturation.label, range('saturation', ctl.saturation, s.saturation))}
      ${field(ctl.white_balance_mode.label, en('white_balance_mode'))}
      ${field(ctl.ae_antibanding.label, en('ae_antibanding'))}
      ${field(ctl.ae_lock.label, tog('ae_lock'))}
      ${field(ctl.awb_lock.label, tog('awb_lock'))}</div>
      <div class="cs-group"><h3>PROCESSING &amp; OUTPUT</h3>
      ${field(ctl.edge_enhancement.label, range('edge_enhancement', ctl.edge_enhancement, s.edge_enhancement))}
      ${field(ctl.noise_reduction.label, range('noise_reduction', ctl.noise_reduction, s.noise_reduction))}
      ${field(ctl.jpeg_quality.label, range('jpeg_quality', ctl.jpeg_quality, s.jpeg_quality))}
      ${field(ctl.rotate_180.label, tog('rotate_180'))}</div>
      <div class="cs-group"><h3>NOT AVAILABLE ON THIS JETSON</h3>
      ${Object.entries(c.unsupported).map(([k, v]) => field(k === 'hdr' ? 'HDR' : 'Autofocus', '<select disabled><option>Not available</option></select>', '', true) + `<p class="cs-note">${esc(v)}</p>`).join('')}</div>`;
  }
  function collect() {
    const f = $('csForm'), v = {};
    if (dlgCam === 'astra') { for (const k of ['depth', 'color', 'ir']) v[k] = f.elements[k].value; return v; }
    const [w, h] = f.elements.size.value.split('x').map(Number);
    Object.assign(v, { sensor_mode: Number(f.elements.sensor_mode.value), width: w, height: h, framerate: Math.round(Number(f.elements.framerate.value)) });
    for (const k of ['exposure_compensation', 'saturation', 'edge_enhancement', 'noise_reduction']) v[k] = Number(f.elements[k].value);
    v.jpeg_quality = Math.round(Number(f.elements.jpeg_quality.value));
    for (const k of ['white_balance_mode', 'ae_antibanding']) v[k] = Number(f.elements[k].value);
    for (const k of ['ae_lock', 'awb_lock', 'rotate_180']) v[k] = f.elements[k].checked;
    return v;
  }
  function msg(text, cls = '') { const m = $('csMsg'); m.textContent = text; m.className = 'cs-msg' + (cls ? ' ' + cls : ''); }
  function setApply() {
    const blocked = dlgCam === 'picam' && summary && summary.picam.apply_blocked && summary.picam.apply_blocked.length;
    $('csApply').disabled = busy || !!blocked; $('csReset').disabled = busy || !!blocked;
    if (blocked && !busy) msg('Apply is available while ATLAS is parked: ' + summary.picam.apply_blocked.join('; ') + '.', 'warn');
  }
  async function validate() {
    try {
      const r = await post(dlgCam, { action: 'validate', settings: collect() }); msg('Valid for this camera.', 'ok'); setApply();
      const bw = r.bandwidth, el = document.querySelector('#csBody [data-bw]');
      if (bw && el) el.textContent = `Estimated USB use: depth ${bw.per_stream_mbps.depth}, RGB ${bw.per_stream_mbps.color}, IR ${bw.per_stream_mbps.ir} MB/s (budget ${bw.budget_mbps} MB/s for the streams a session uses together; a combination above it starts with the defaults).`;
      return true;
    }
    catch (e) { msg(e.message, 'err'); $('csApply').disabled = true; return false; }
  }
  function render(cam, s) {
    const c = caps[cam];
    $('csDlgTitle').textContent = (cam === 'astra' ? 'Astra Pro' : 'Pi Camera Module 3') + ' settings';
    $('csBody').innerHTML = cam === 'astra' ? astraForm(c, s) : picamForm(c, s);
    $('csBody').querySelectorAll('input[type=range]').forEach(r => r.addEventListener('input', () => { r.nextElementSibling.textContent = r.value; }));
  }
  async function open(cam) {
    dlgCam = cam; msg('');
    if (!caps[cam]) await loadCaps(cam);
    if (!caps[cam] || !summary) return;
    render(cam, summary[cam].saved);
    $('csDialog').showModal(); setApply();
  }
  $('csForm').addEventListener('change', e => {
    if (dlgCam === 'picam' && e.target.name === 'sensor_mode') render('picam', Object.assign({}, collect(), { sensor_mode: Number(e.target.value) }));
    clearTimeout(validateTimer); validateTimer = setTimeout(validate, 250);
  });
  $('csApply').addEventListener('click', async () => {
    if (!(await validate())) return;
    if (dlgCam === 'picam' && !confirm('Apply restarts the Pi camera (about 5 seconds). Camera images and camera obstacles pause during the restart. Continue?')) return;
    busy = true; setApply(); msg(dlgCam === 'picam' ? 'Restarting the Pi camera…' : 'Saving…', 'warn');
    try { const r = await post(dlgCam, { action: 'apply', settings: collect() }); msg(r.message, 'ok'); await refresh(); }
    catch (e) { msg(e.message, 'err'); }
    finally { busy = false; setApply(); }
  });
  $('csReset').addEventListener('click', async () => {
    if (!confirm(dlgCam === 'picam' ? 'Restore the default Pi Camera settings? This restarts the Pi camera.' : 'Restore the default Astra modes?')) return;
    busy = true; setApply(); msg('Restoring defaults…', 'warn');
    try { const r = await post(dlgCam, { action: 'reset' }); msg(r.message, 'ok'); await refresh(); render(dlgCam, summary[dlgCam].saved); }
    catch (e) { msg(e.message, 'err'); }
    finally { busy = false; setApply(); }
  });
  document.addEventListener('click', async e => {
    if (e.target.closest('[data-measure]') && !measuring) {
      measuring = true; q('picam', '[data-fps]').innerHTML = '<small>Measuring for 3 seconds…</small>';
      try { lastMeasure = Object.assign(await get('picam/measure'), { at: Date.now() }); }
      catch (err) { lastMeasure = null; q('picam', '[data-fps]').innerHTML = `<small>${esc(err.message)}</small>`; measuring = false; return; }
      measuring = false; q('picam', '[data-fps]').innerHTML = measureText(lastMeasure, lastMeasure.configured_fps || '?');
    }
    const det = e.target.closest('[data-detect]');
    if (det) {
      det.disabled = true; const m = q('astra', '[data-detectmsg]'); m.textContent = 'Detecting (about 2 s)…';
      try { const r = await post('astra', { action: 'detect' }); await loadCaps('astra'); q('astra', '[data-detectmsg]').textContent = `${r.message} Serial ${r.serial}.`; }
      catch (err) { m.textContent = err.message; det.disabled = false; }
    }
  });
  document.querySelectorAll('[data-open]').forEach(b => b.addEventListener('click', () => open(b.dataset.open)));
  document.querySelectorAll('.cs-caps').forEach((d, i) => d.addEventListener('toggle', () => { const cam = i ? 'picam' : 'astra'; if (d.open && !caps[cam]) loadCaps(cam); }));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  refresh(); setInterval(refresh, 4000);
})();
