/* ATLAS 3D Vision Lab: user-facing session state from REAL frame evidence (Stage 32 UI fix).
 * Pure functions only (no DOM, no network) so they can be tested offline. Inputs are the fields the deployed receiver
 * already reports: runtime {state, reason, mode, worker_pid, driver_pid, driver_stopped, failed_resources} and
 * streams[k] {state, received, source_age_s, fps_observed}. "Camera driver running" is never presented as "live":
 * a requested stream is Live only while the receiver holds a fresh frame from it. */
(function (root) {
  'use strict';
  const STREAMS = { depth: ['depth'], concurrent: ['depth', 'rgb'], ir: ['ir'], ir_depth: ['ir', 'depth'], rgb_ir: ['rgb', 'ir'], depth_cloud: ['depth', 'cloud'] };
  const NAMES = { depth: 'Depth', rgb: 'Colour', ir: 'Infrared', cloud: '3D cloud' };
  const WAIT_S = 10;   // after the driver reports running, frames normally arrive within ~2-3 s (measured 21 Oct)

  function newMemo() { return { key: null, activeAt: null, maxRx: {}, outcome: null }; }
  const list = ks => ks.map(k => NAMES[k]).join(' and ');

  // memo is updated in place: per-session (worker_pid) frame evidence survives the receiver clearing its counters at stop.
  function sessionView(rt, streams, memo, nowS) {
    streams = streams || {};
    const st = rt ? String(rt.state || 'OFF') : 'NONE', reason = rt ? String(rt.reason || '') : '';
    const want = STREAMS[(rt && rt.mode) || 'depth'] || ['depth'];
    const key = rt && rt.worker_pid ? String(rt.worker_pid) : null;
    if (key && key !== memo.key && (st === 'CHECKING' || st === 'ACTIVE')) { memo.key = key; memo.activeAt = null; memo.maxRx = {}; memo.outcome = null; }
    const chips = {};
    for (const k of ['depth', 'rgb', 'ir', 'cloud']) {
      const s = streams[k] || {}, rx = Number(s.received) || 0;
      if (memo.key === key && key) memo.maxRx[k] = Math.max(memo.maxRx[k] || 0, rx);
      chips[k] = { label: 'Off', cls: '' };
    }
    const out = { tone: 'idle', title: 'Camera off', text: 'Choose a mode and press Start. A session runs for up to 60 seconds.', chips,
                  driver: 'Off', run: 'Camera off · press Start', requested: want, live: [], waiting: [], missing: [], stale: [] };
    if (!rt) { return Object.assign(out, { tone: 'fail', title: 'Viewer not installed', text: 'The Vision Lab runtime is not available on this Jetson.', driver: '—' }); }
    if (st === 'CHECKING') {
      for (const k of want) chips[k] = { label: 'Starting', cls: 'busy' };
      return Object.assign(out, { tone: 'busy', title: 'Starting', text: 'Checking that ATLAS is stopped and has CPU, memory and thermal headroom, then turning the camera on.',
                                  driver: 'Not started yet', run: 'Starting…' });
    }
    if (st === 'ACTIVE') {
      if (memo.activeAt === null) memo.activeAt = nowS;
      const since = nowS - memo.activeAt;
      for (const k of want) {
        const s = streams[k] || {}, ever = (memo.maxRx[k] || 0) > 0;
        if (s.state === 'ACTIVE') { out.live.push(k); chips[k] = { label: 'Live', cls: 'ok' }; }
        else if (ever) { out.stale.push(k); chips[k] = { label: 'No new frames', cls: 'warn' }; }
        else if (since < WAIT_S) { out.waiting.push(k); chips[k] = { label: 'Waiting for frames', cls: 'busy' }; }
        else { out.missing.push(k); chips[k] = { label: 'No frames received', cls: 'warn' }; }
      }
      const left = rt && Number.isFinite(rt.remaining_s) ? Math.ceil(rt.remaining_s) : null, tail = left !== null ? ` ${left} s left in this session.` : '';
      out.driver = out.live.length === want.length ? 'Running · frames arriving' : 'Running · ' + (out.live.length ? 'some frames missing' : 'no frames yet');
      if (out.live.length === want.length) Object.assign(out, { tone: 'ok', title: 'Live', text: `${list(want)} frames are arriving from the camera.${tail} Distances are uncalibrated sensor readings.` });
      else if (out.missing.length || out.stale.length) {
        const parts = [];
        if (out.missing.length) parts.push(`${list(out.missing)}: no frames received in ${Math.floor(since)} s`);
        if (out.stale.length) parts.push(`${list(out.stale)}: frames stopped arriving`);
        Object.assign(out, { tone: 'warn', title: out.missing.length ? 'No frames received' : 'Frames stopped',
                             text: `The camera driver is running, but ${parts.join('; ')}.${out.live.length ? ' ' + list(out.live) + ' is live.' : ''} This is not a working view; see Developer Diagnostics.` });
      } else Object.assign(out, { tone: 'busy', title: 'Waiting for frames', text: `The camera driver is running; waiting for the first ${list(out.waiting)} frames.${tail}` });
      out.run = `${out.title} · ${want.map(k => NAMES[k].toLowerCase()).join(' + ')}`;
      return out;
    }
    // session ended: summarise what this session actually delivered (per-page memory, keyed by worker)
    if (memo.key && memo.key === key && !memo.outcome) memo.outcome = want.map(k => [k, memo.maxRx[k] || 0]);
    const delivered = memo.key === key && memo.outcome ? memo.outcome : null;
    const none = delivered ? delivered.filter(([, n]) => n === 0).map(([k]) => k) : [];
    const frames = delivered ? ' ' + delivered.map(([k, n]) => `${NAMES[k]}: ${n.toLocaleString('en-US')} frames received.`).join(' ') : '';
    out.driver = rt.driver_pid ? (rt.driver_stopped ? 'Stopped safely' : 'Stopping…') : 'Off';
    if (st === 'RESOURCE BLOCKED') {
      const failed = rt.failed_resources || {}, lim = rt.limits || { cpu_percent: 75, ram_percent: 80, temperature_c: 70 };
      const what = Number.isFinite(failed.cpu) ? `CPU reached ${failed.cpu.toFixed(1)}%, above the ${lim.cpu_percent}% limit` :
        /RAM/.test(reason) ? `memory went above the ${lim.ram_percent}% limit` : /temperature|thermal/i.test(reason) ? `temperature went above ${lim.temperature_c} °C` : 'a resource limit was exceeded';
      return Object.assign(out, { tone: 'warn', title: 'Resource blocked', run: 'Camera off · resource blocked',
        text: `${what}, so the camera was turned off${rt.driver_stopped ? ' and the driver was stopped safely' : ''}. This says nothing about whether the camera mode works. Nothing else on ATLAS was changed.${frames}` });
    }
    // 26 Oct 2026: the worker's clear refusal text (E-STOP released / zero speed unconfirmed). The camera never
    // started; nothing is engaged or retried from here. Raw gate reason: rt.diagnostic_reason / lifecycle.
    if (rt.operator_message) {
      const began = !!rt.driver_pid;   // refused at admission, or a running session stopped by the same gate
      return Object.assign(out, { tone: 'warn', title: began ? 'Stopped safely' : 'Not started',
        text: String(rt.operator_message) + (began ? frames : ''), run: began ? 'Camera off · press Start' : 'Camera off · not started' });
    }
    if (reason) {
      const why = /session complete/i.test(reason) ? 'The 60-second session ended.' :
        /lease/i.test(reason) ? 'The viewing page stopped checking in for more than 4 seconds, so the camera was turned off.' :
        /paused|closed/i.test(reason) ? 'The camera was stopped because you pressed Stop, or the page was hidden or closed.' :
        /domain .* in use/i.test(reason) ? 'Another program is already using the private Vision Lab ROS domain, so the camera was not started.' :
        /existing Astra/i.test(reason) ? 'Another Astra camera process is already running, so a second one was not started.' :
        /policy|stationary|nonzero|stale/i.test(reason) ? 'ATLAS was not confirmed stopped and E-STOP latched, so the camera was not started.' : reason;
      const stoppedSafely = !!rt.driver_stopped || /session complete|lease|paused|closed/i.test(reason);
      const title = none.length ? 'No frames received' : stoppedSafely ? 'Stopped safely' : 'Camera off';
      return Object.assign(out, { tone: none.length || !/session complete/i.test(reason) ? 'warn' : 'idle', title,
        text: `${why}${none.length ? ` ${list(none)} delivered no frames in this session.` : ''}${frames} Press Start for another session.`,
        run: 'Camera off · press Start' });
    }
    return out;
  }

  // Mode selector notes from the receiver's mode_support manifest (states: verified | untested | unsupported | needs_calibration).
  function modeNote(m, info) {
    const st = info ? info.state : (m === 'depth' ? 'verified' : 'untested');
    if (m === 'depth_cloud' && st === 'unsupported') return { state: 'unsupported', note: 'Calibration required', disabled: true };
    return { state: st, note: st === 'verified' ? 'Tested' : st === 'unsupported' ? 'Not supported (tested)' : 'Not yet tested', disabled: st === 'unsupported' };
  }

  // ---------- UNCALIBRATED 3D preview (diagnostic only) ----------
  // Nominal geometry from the camera's own reported field of view (read-only OpenNI query, 21 Oct 2026:
  // 1.0226 x 0.7966 rad, identical to ZPD/ZPPS). This is NOT a calibration: no principal-point or lens-distortion
  // measurement exists, so X/Y are approximate. Z is the sensor's own axial reading. Never published to ROS or navigation.
  const NOMINAL_FOV = { h: 1.0225999355316162, v: 0.7966156601905823 };
  const PREVIEW_LABEL = 'UNCALIBRATED \u2014 DIAGNOSTIC ONLY';
  function nominalK(w, h) { return { fx: (w / 2) / Math.tan(NOMINAL_FOV.h / 2), fy: (h / 2) / Math.tan(NOMINAL_FOV.v / 2), cx: (w - 1) / 2, cy: (h - 1) / 2 }; }
  function previewPoints(buf, hdr, limit) {
    const get = k => (hdr.get ? hdr.get(k) : hdr[k]);
    const w = +get('X-Width'), h = +get('X-Height'), enc = get('X-Encoding'), step = +get('X-Step'), be = get('X-Bigendian') === '1';
    if (!(enc === '16UC1' || enc === '32FC1')) throw Error('Preview needs native depth (16UC1 or 32FC1)');
    const bpp = enc === '16UC1' ? 2 : 4;
    if (!(w > 0 && h > 0) || step < w * bpp || buf.byteLength !== step * h) throw Error('Depth frame size mismatch');
    limit = Math.max(1, Math.min(6000, limit || 6000));
    const stride = Math.max(1, Math.ceil(Math.sqrt(w * h / limit))), k = nominalK(w, h), dv = new DataView(buf), points = [];
    let invalid = 0;
    for (let v = 0; v < h; v += stride) for (let u = 0; u < w; u += stride) {
      const raw = bpp === 2 ? dv.getUint16(v * step + u * 2, !be) : dv.getFloat32(v * step + u * 4, !be);
      const z = bpp === 2 ? (raw === 0 || raw === 65535 ? NaN : raw / 1000) : raw;
      if (!(z > 0 && z <= 8)) { invalid++; continue; }
      points.push([(u - k.cx) / k.fx * z, (v - k.cy) / k.fy * z, z, u, v]);
    }
    return { points: points.slice(0, limit), stride, invalid, w, h, k, label: PREVIEW_LABEL, calibrated: false };
  }

  const api = { sessionView, newMemo, modeNote, previewPoints, nominalK, NOMINAL_FOV, PREVIEW_LABEL, STREAMS, WAIT_S };
  if (typeof module === 'object' && module.exports) module.exports = api; else root.AtlasVisionState = api;
})(typeof window !== 'undefined' ? window : globalThis);
