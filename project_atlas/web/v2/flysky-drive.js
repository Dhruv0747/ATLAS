/* ATLAS FlySky Driving page (client). Reads GET /api/manual_controller; its only POST asks the mux to change the
 * active remote ({"target": "XBOX"|"FLYSKY"}), which the mux allows only while the E-STOP is latched.
 * The dock E-STOP is the shared /v2/estop.js button. Nothing here can release the E-STOP or send a drive command. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let v = null, busy = false, noteUntil = 0;
  const setText = (n, t) => { if (n && n.textContent !== t) n.textContent = t; };
  const fmt = (x, d = 2) => (x == null || !isFinite(x)) ? '–' : Number(x).toFixed(d);
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, val] of Object.entries(attrs || {})) { if (k === 'class') n.className = val; else if (k === 'text') n.textContent = val; else n.setAttribute(k, val); }
    for (const kid of kids) if (kid != null) n.append(kid);
    return n;
  }
  function chip(id, cls, text) { const n = $(id); n.className = 'chip ' + cls; setText(n, text); }
  function row(dl, k, val, cls) { dl.append(el('dt', { text: k }), el('dd', { class: cls || '', text: val })); }

  const STATE_TEXT = {
    DISABLED: 'FlySky driving is turned off on this rover.',
    POLICY_STALE: 'The drive node cannot see the stop multiplexer. Motion is held at zero.',
    NOT_SELECTED: 'The Xbox controller is the active remote.',
    STOP_LATCHED: 'E-STOP latched. Reset it the usual way to drive.',
    NO_SIGNAL: 'No FlySky signal. Motion is held at zero.',
    FAILSAFE: 'The receiver reports failsafe. Motion is held at zero.',
    FRAME_LOST: 'The receiver reports lost frames. Arm again when the signal is steady.',
    STOP_SWITCH: 'The FlySky stop switch is on.',
    INVALID_INPUT: 'A switch or stick reading is not valid. Motion is held at zero.',
    WAIT_ARM_OFF: 'Switch the arm switch off, then on, to arm.',
    WAIT_ARM_ON: 'Ready. Switch the arm switch on to arm.',
    WAIT_NEUTRAL: 'Centre the throttle to finish arming.',
    ARMED: 'Armed. The FlySky drives the rover.'
  };

  function render() {
    const p = v.policy, d = v.drive, s = d.status;
    chip('chipCtl', p.manual_controller ? 'info' : 'warn', p.manual_controller ? 'Remote: ' + (p.manual_controller === 'FLYSKY' ? 'FlySky' : 'Xbox') : 'Remote: unknown');
    chip('chipStop', p.stop_latched ? 'ok' : p.fresh ? 'warn' : 'fail', p.fresh ? (p.stop_latched ? 'E-STOP latched' : 'E-STOP released') : 'Stop state unknown');
    chip('chipGate', p.flysky_drive_enabled ? 'warn' : '', p.flysky_drive_enabled ? 'FlySky driving enabled' : 'FlySky driving off');
    chip('chipState', d.running ? (s.state === 'ARMED' ? 'fail' : 'info') : '', d.running ? 'Drive node: ' + s.state.replace(/_/g, ' ').toLowerCase() : 'Drive node not running');

    const b = $('banner'); b.hidden = false; b.textContent = '';
    let big, small;
    if (!p.fresh) { big = 'Stop state unknown'; small = 'The page cannot read the stop multiplexer. Treat the rover as live and use the physical stop.'; b.className = 'tl-banner fail'; }
    else if (!p.selection_supported) { big = 'Xbox only'; small = 'This rover runs the stop multiplexer without remote selection. FlySky driving has not been installed.'; b.className = 'tl-banner'; }
    else if (!d.running) { big = p.manual_controller === 'FLYSKY' ? 'FlySky selected, drive node not running' : 'Xbox drives'; small = p.manual_controller === 'FLYSKY' ? 'Nothing can drive until the FlySky drive node runs. Motion stays at zero.' : 'The FlySky drive node is not running.'; b.className = 'tl-banner'; }
    else { big = s.state === 'ARMED' ? 'FlySky armed' : p.manual_controller === 'FLYSKY' ? 'FlySky selected' : 'Xbox drives'; small = STATE_TEXT[s.state] || s.reason; b.className = 'tl-banner' + (s.state === 'ARMED' ? ' fail' : ''); }
    b.append(el('span', { class: 'big', text: big }), document.createTextNode(small));

    $('useXbox').disabled = busy || !v.can_select.XBOX; $('useFlysky').disabled = busy || !v.can_select.FLYSKY;
    $('useXbox').classList.toggle('tl-primary', p.manual_controller === 'XBOX'); $('useFlysky').classList.toggle('tl-primary', p.manual_controller === 'FLYSKY');
    for (const [id, k] of [['useXbox', 'XBOX'], ['useFlysky', 'FLYSKY']]) {
      const btn = $(id), sel = p.fresh && p.manual_controller === k;
      btn.setAttribute('aria-pressed', String(!!sel)); setText(btn.querySelector('.fd-sel'), sel ? 'Selected' : v.can_select[k] ? 'Available' : 'Blocked');
    }
    if (!busy && Date.now() > noteUntil) setText($('selNote'), (v.can_select.XBOX || v.can_select.FLYSKY) ? 'Ready to change remote.' : v.blocked_reason ? 'Change not possible now: ' + v.blocked_reason + '.' : '');

    const live = $('live'); live.textContent = '';
    const i = s && s.inputs;
    if (!d.running) row(live, 'Input', 'drive node not running', 'dim');
    else if (!i) row(live, 'Input', 'no receiver frame yet', 'dim');
    else {
      row(live, 'Arm switch', i.arm === 'ON' ? 'on' : i.arm === 'OFF' ? 'off' : 'not valid', i.arm === 'ON' ? 'bad' : i.arm === 'OFF' ? 'ok' : 'bad');
      row(live, 'Stop switch', i.stop === 'RUN' ? 'run' : 'stop', i.stop === 'RUN' ? '' : 'bad');
      row(live, 'Throttle', i.throttle == null ? 'not valid' : fmt(i.throttle));
      row(live, 'Steering', i.steering == null ? 'not valid' : fmt(i.steering));
      if (i.speed_scale != null) row(live, 'Speed setting', Math.round(i.speed_scale * 100) + ' %');
      row(live, 'Receiver flags', i.failsafe ? 'failsafe' : i.frame_lost ? 'frame lost' : 'clear', i.failsafe || i.frame_lost ? 'bad' : 'ok');
      row(live, 'Last frame', s.frame_age_s == null ? 'never' : fmt(s.frame_age_s) + ' s ago');
      const c = s.command; row(live, 'Request to mux', c ? fmt(c[0]) + ' m/s · ' + fmt(c[1]) + ' rad/s' : 'none');
    }

    // Stage 29 FlySky reset: what the drive node and the mux report (this page cannot reset anything)
    const rs = $('reset'); rs.textContent = '';
    const g = s && s.reset, mx = g && g.mux;
    if (!d.running || !g) row(rs, 'Reset', d.running ? 'not reported by the drive node' : 'shown when the drive node runs', 'dim');
    else if (!g.enabled || !mx || !mx.enabled) row(rs, 'Reset', 'off on this rover. Use Xbox LB.', 'dim');
    else {
      row(rs, 'E-STOP', p.stop_latched ? 'latched' : 'released', p.stop_latched ? 'ok' : 'bad');
      const RS = { READY: 'available: SwD down now', HOLDING: 'holding SwD ' + fmt(g.held_s) + ' s of ' + fmt(g.hold_s), RELEASE_NOW: 'release SwD up now',
                   SENT: 'requested, waiting for the stop multiplexer', WAIT_SWD_UP: 'put SwD up for 1 s', BLOCKED: 'blocked',
                   UNAVAILABLE: 'select FlySky first', NOT_NEEDED: 'not needed', OFF: 'off' };
      row(rs, 'Reset', RS[g.state] || g.state, g.state === 'BLOCKED' ? 'bad' : g.available ? 'ok' : '');
      if (g.blocked && g.blocked.length) row(rs, 'Blocked because', g.blocked.join(' · '), 'bad');
      row(rs, 'Rover still', mx.stationary ? 'yes' : 'not confirmed', mx.stationary ? 'ok' : 'bad');
      if (mx.last_result) row(rs, 'Last request', (mx.last_result === 'RELEASED' ? 'released' : 'refused: ' + mx.last_reason) + (mx.age_s != null ? ' (' + fmt(mx.age_s) + ' s ago)' : ''), mx.last_result === 'RELEASED' ? '' : 'bad');
    }

    const cfg = $('cfg'); cfg.textContent = '';
    const k = s && s.config;
    if (!k) row(cfg, 'Setup', d.running ? 'not reported' : 'shown when the drive node runs', 'dim');
    else {
      const axis = a => a ? 'CH' + a.channel + (a.reversed ? ', reversed' : '') + ', dead zone ' + Math.round(a.deadband * 100) + ' %' : '–';
      row(cfg, 'Reviewed by owner', k.reviewed_by_owner ? 'yes' : 'no', k.reviewed_by_owner ? 'ok' : 'bad');
      row(cfg, 'Throttle', axis(k.throttle)); row(cfg, 'Steering', axis(k.steering));
      row(cfg, 'Arm switch', k.arm_channel ? 'CH' + k.arm_channel : '–'); row(cfg, 'Stop switch', k.stop_channel ? 'CH' + k.stop_channel : '–');
      row(cfg, 'Speed switch', k.speed_mode_channel ? 'CH' + k.speed_mode_channel : 'none');
      row(cfg, 'Top speed', fmt(k.max_linear_mps) + ' m/s (limit ' + fmt(k.hard_max_linear_mps) + ')');
      row(cfg, 'Top turn rate', fmt(k.max_angular_radps) + ' rad/s (limit ' + fmt(k.hard_max_angular_radps) + ')');
      if (k.errors && k.errors.length) row(cfg, 'Not ready because', k.errors.join(' · '), 'bad');
    }
  }

  async function poll() {
    try {
      const r = await fetch('/api/manual_controller', { cache: 'no-store' });
      if (!r.ok) throw new Error(String(r.status));
      v = await r.json(); render();
      window.dispatchEvent(new CustomEvent('atlas:controller', { detail: v }));     // read by controller-viz.js
    } catch (e) {
      const b = $('banner'); b.hidden = false; b.className = 'tl-banner fail'; b.textContent = 'Cannot reach the rover. Treat it as live and use the physical stop.';
      chip('chipStop', 'fail', 'Stop state unknown'); $('useXbox').disabled = $('useFlysky').disabled = true;
      window.dispatchEvent(new CustomEvent('atlas:controller', { detail: null }));
    }
    setTimeout(poll, document.hidden ? 2000 : 500);
  }
  async function pick(target) {
    if (busy) return; busy = true; $('useXbox').disabled = $('useFlysky').disabled = true;
    setText($('selNote'), 'Asking the stop multiplexer…');
    try {
      const r = await fetch('/api/manual_controller', {
        method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-Atlas-Controller': '1' }, body: JSON.stringify({ target })
      });
      let j = {}; try { j = await r.json(); } catch (e) { /* not JSON */ }
      setText($('selNote'), j.message || ('Request refused (' + r.status + ')')); noteUntil = Date.now() + 5000;
    } catch (e) { setText($('selNote'), 'The rover did not answer. Nothing was changed.'); noteUntil = Date.now() + 5000; }
    finally { busy = false; }
  }
  $('useXbox').addEventListener('click', () => pick('XBOX'));
  $('useFlysky').addEventListener('click', () => pick('FLYSKY'));
  poll();
})();
