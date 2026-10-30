/* ATLAS controller mapping for the FlySky Driving page (pure data + pure functions, no DOM, no network).
 *
 * Xbox: every assignment below is read from the code running on the rover (verified 2026-10-29, file hashes match):
 *   config/teleop_twist_joy.yaml (edfea663)   enable_button 4, turbo 5, axis_linear.x 1 (0.52 / 0.65 m/s),
 *                                              axis_angular.yaw 3 (1.20 / 1.60 rad/s)
 *   scripts/atlas_remote_stop.py (1a44fb37)   button 1 latches the stop; button 4 held 2 s with sticks 0,1,3,4 centred
 *                                              and no other button, then released, clears it
 *   scripts/camera_joystick_node.py (6b5ad455) axes 6/7 camera pan/tilt, button 3 camera home, ignored while B is held
 *   /joy on this rover: 8 axes, 11 buttons (joy_node, Xbox 360 pad). Triggers rest at +1.0.
 * FlySky: channel numbers are the owner-verified mapping of 2026-10-29. Which channel DRIVES what is never taken from
 * this file: it is read from the drive node's own reported config, so this page cannot silently disagree with it.
 */
(function (root) {
  'use strict';

  // ---------------------------------------------------------------- Xbox 360 (joy_node indices on this rover)
  // group: drive (needs Xbox selected and the E-STOP released), stop (always live), camera (separate camera service,
  // independent of the selected drive remote), none (unassigned).
  const XBOX = [
    { id: 'ls', name: 'Left stick', kind: 'stick', axes: [0, 1], click: 9,
      functions: [{ axis: 1, text: 'Up / down: drive forward / reverse', group: 'drive', detail: 'Up to 0.52 m/s, 0.65 m/s with RB. Only while LB is held.' },
                  { axis: 0, text: 'Left / right: not used', group: 'none' },
                  { button: 9, text: 'Click: not used', group: 'none' }] },
    { id: 'rs', name: 'Right stick', kind: 'stick', axes: [3, 4], click: 10,
      functions: [{ axis: 3, text: 'Left / right: steering', group: 'drive', detail: 'Up to 1.20 rad/s, 1.60 rad/s with RB. Only while LB is held.' },
                  { axis: 4, text: 'Up / down: not used', group: 'none' },
                  { button: 10, text: 'Click: not used', group: 'none' }] },
    { id: 'lb', name: 'LB', kind: 'bumper', button: 4,
      functions: [{ button: 4, text: 'Hold to drive (dead-man)', group: 'drive', detail: 'Release LB and the drive command stops.' },
                  { button: 4, text: 'E-STOP reset: hold 2 s, sticks centred, nothing else pressed, then release', group: 'stop' }] },
    { id: 'rb', name: 'RB', kind: 'bumper', button: 5,
      functions: [{ button: 5, text: 'Hold with LB: turbo speed', group: 'drive' }] },
    { id: 'lt', name: 'LT', kind: 'trigger', axis: 2, functions: [{ axis: 2, text: 'Not used', group: 'none' }] },
    { id: 'rt', name: 'RT', kind: 'trigger', axis: 5, functions: [{ axis: 5, text: 'Not used', group: 'none' }] },
    { id: 'b', name: 'B', kind: 'face', button: 1,
      functions: [{ button: 1, text: 'REMOTE STOP: stops the rover and latches the E-STOP', group: 'stop' }] },
    { id: 'a', name: 'A', kind: 'face', button: 0, functions: [{ button: 0, text: 'Not used', group: 'none' }] },
    { id: 'x', name: 'X', kind: 'face', button: 2, functions: [{ button: 2, text: 'Not used', group: 'none' }] },
    { id: 'y', name: 'Y', kind: 'face', button: 3, functions: [{ button: 3, text: 'Camera home', group: 'camera' }] },
    { id: 'dpad', name: 'D-pad', kind: 'dpad', axes: [6, 7],
      functions: [{ axis: 6, text: 'Left / right: camera pan', group: 'camera' },
                  { axis: 7, text: 'Up / down: camera tilt', group: 'camera' }] },
    { id: 'back', name: 'Back', kind: 'small', button: 6, functions: [{ button: 6, text: 'Not used', group: 'none' }] },
    { id: 'guide', name: 'Guide', kind: 'small', button: 8, functions: [{ button: 8, text: 'Not used', group: 'none' }] },
    { id: 'start', name: 'Start', kind: 'small', button: 7, functions: [{ button: 7, text: 'Not used', group: 'none' }] }
  ];
  const XBOX_AXES = 8, XBOX_BUTTONS = 11, STICK_DEAD = 0.1, TRIGGER_REST = 1.0;

  // ---------------------------------------------------------------- FlySky FS-i6S
  // role: which drive-config field may claim this channel. planned: proposed but not implemented anywhere.
  const FLYSKY = [
    { ch: 1, id: 'ch1', control: 'Right stick, left / right', name: 'CH1', kind: 'stick-x', stick: 'right', role: 'steering', proposal: 'Steering' },
    { ch: 2, id: 'ch2', control: 'Right stick, up / down', name: 'CH2', kind: 'stick-y', stick: 'right', role: 'throttle', proposal: 'Throttle (springs back to centre)' },
    { ch: 3, id: 'ch3', control: 'Left stick, up / down', name: 'CH3', kind: 'stick-y', stick: 'left', role: null, note: 'Does not spring back to centre, so it is not used to drive.' },
    { ch: 4, id: 'ch4', control: 'Left stick, left / right', name: 'CH4', kind: 'stick-x', stick: 'left', role: null },
    { ch: 5, id: 'swa', control: 'Switch SwA (2 positions)', name: 'SwA', kind: 'switch', positions: 2, role: 'arm', proposal: 'Arm / disarm (up = off, down = arm)' },
    { ch: 6, id: 'swb', control: 'Switch SwB (3 positions)', name: 'SwB', kind: 'switch', positions: 3, role: 'stop', proposal: 'Run / stop (up = run, middle or down = stop and latch)' },
    { ch: 7, id: 'swc', control: 'Switch SwC (3 positions)', name: 'SwC', kind: 'switch', positions: 3, role: 'speed', proposal: 'Speed (up 33 %, middle 66 %, down 100 % of the limit)' },
    { ch: 8, id: 'swd', control: 'Switch SwD (2 positions)', name: 'SwD', kind: 'switch', positions: 2, role: null,
      reset: 'E-STOP reset: SwD up 1 s, down 2-5 s, then up' },
    { ch: 9, id: 'vra', control: 'Knob VrA', name: 'VrA', kind: 'knob', role: null, planned: 'Camera pan (proposed, not implemented)' },
    { ch: 10, id: 'vrb', control: 'Knob VrB', name: 'VrB', kind: 'knob', role: null, planned: 'Camera tilt (proposed, not implemented)' }
  ];
  const FLYSKY_KEYS = [
    { id: 'key1', name: 'Key 1', control: 'Rear key', note: 'Not sent on any receiver channel in this setup.' },
    { id: 'key2', name: 'Key 2', control: 'Rear key', note: 'Not sent on any receiver channel in this setup.' }
  ];
  const RAW = { low: 240, mid: 1024, high: 1807 };         // this transmitter, owner-verified
  const SW_LOW = 400, SW_HIGH = 1700;                       // same thresholds as config arm/stop
  const STICK_RAW_DEAD = 63;                                // 8 % of 783: the drive dead zone

  // ---------------------------------------------------------------- pure helpers
  const finite = x => typeof x === 'number' && isFinite(x);

  function xboxInputActive(fn, axes, buttons) {
    if (fn.button != null) return buttons[fn.button] === 1;
    const v = axes[fn.axis];
    if (!finite(v)) return false;
    if (fn.axis === 2 || fn.axis === 5) return v < TRIGGER_REST - 0.1;
    return Math.abs(v) >= (fn.axis >= 6 ? 0.5 : STICK_DEAD);
  }

  /* State of one Xbox function: active | inactive | unassigned | blocked, with a short reason. */
  function xboxFunctionState(fn, ctx) {
    if (fn.group === 'none') return { state: 'unassigned', why: 'No function on this rover.' };
    if (!ctx.xboxLive) return { state: 'blocked', why: 'Xbox signal not live.' };
    if (fn.group === 'stop') return { state: 'active', why: 'Always active, whichever remote is selected.' };
    if (fn.group === 'camera') return { state: 'active', why: 'Camera service; independent of the selected remote.' };
    if (ctx.controller !== 'XBOX') return { state: 'inactive', why: ctx.controller === 'FLYSKY' ? 'FlySky is the selected remote.' : 'Selected remote unknown.' };
    if (ctx.latched !== false) return { state: 'blocked', why: 'E-STOP latched.' };
    return { state: 'active', why: 'Xbox drives.' };
  }

  function xboxLayoutOk(axes, buttons) { return Array.isArray(axes) && Array.isArray(buttons) && axes.length === XBOX_AXES && buttons.length === XBOX_BUTTONS; }

  function switchPosition(raw, positions) {
    if (!finite(raw)) return null;
    if (raw < SW_LOW) return 'up';
    if (raw > SW_HIGH) return 'down';
    return positions === 3 ? 'middle' : 'between';
  }

  /* -1..1 from raw using the config's calibration when it has one for this channel, else the verified raw range. */
  function stickNorm(raw, cal) {
    if (!finite(raw)) return null;
    const lo = cal && finite(cal.min) ? cal.min : RAW.low, mid = cal && finite(cal.centre) ? cal.centre : RAW.mid, hi = cal && finite(cal.max) ? cal.max : RAW.high;
    const v = raw >= mid ? (raw - mid) / Math.max(1, hi - mid) : (raw - mid) / Math.max(1, mid - lo);
    return Math.max(-1, Math.min(1, v));
  }

  /* Which drive role each channel actually has, from the drive node's reported config (never from this file). */
  function rolesFromConfig(cfg) {
    const out = {};
    if (!cfg) return out;
    const put = (ch, role) => { if (Number.isInteger(ch)) (out[ch] = out[ch] || []).push(role); };
    put(cfg.throttle && cfg.throttle.channel, 'throttle'); put(cfg.steering && cfg.steering.channel, 'steering');
    put(cfg.arm_channel, 'arm'); put(cfg.stop_channel, 'stop'); put(cfg.speed_mode_channel, 'speed');
    return out;
  }

  /* Channels where the running drive config disagrees with the owner-verified layout. */
  function configMismatches(cfg) {
    const roles = rolesFromConfig(cfg), bad = [];
    if (!cfg) return bad;
    for (const c of FLYSKY) {
      const got = roles[c.ch] || [];
      if (c.role && !got.includes(c.role)) bad.push(c.name + ' is not ' + c.role + ' in the running config');
      for (const r of got) if (r !== c.role) bad.push(c.name + ' (CH' + c.ch + ') is used for ' + r + ' in the running config');
      if (got.length > 1) bad.push('CH' + c.ch + ' has more than one role');
    }
    return bad;
  }

  /* State of one FlySky channel's drive function: active | proposed | inactive | blocked | unassigned | planned. */
  function flyskyFunctionState(c, ctx) {
    if (!ctx.config && c.role) return { state: 'proposed', text: c.proposal, why: 'The drive node is not reporting its setup, so this is the proposed layout only.' };
    const roles = rolesFromConfig(ctx.config)[c.ch] || [];
    if (c.reset && !roles.length) {                      // Stage 29 FlySky reset: from the drive node's report only
      const r = ctx.reset;
      if (!r || !r.enabled) return { state: 'unassigned', text: 'Not assigned', why: 'The FlySky E-STOP reset is off on this rover.' };
      if (ctx.controller !== 'FLYSKY') return { state: 'inactive', text: c.reset, why: 'Xbox is the selected remote.' };
      if (ctx.latched === false) return { state: 'inactive', text: c.reset, why: 'E-STOP is not latched.' };
      if (r.available) return { state: 'active', text: c.reset, why: 'Ready: do the reset gesture.' };
      return { state: 'blocked', text: c.reset, why: (r.blocked || []).join(' · ') || 'Put SwD up for 1 s.' };
    }
    if (!roles.length) {
      if (c.planned) return { state: 'planned', text: c.planned, why: 'Not implemented on the rover.' };
      return { state: 'unassigned', text: 'Not assigned', why: c.note || 'No function on this rover.' };
    }
    const text = c.proposal || roles.join(', ');
    if (!ctx.config || !ctx.enabled) return { state: 'proposed', text, why: ctx.blockReason || 'FlySky driving is off.' };
    if (ctx.controller !== 'FLYSKY') return { state: 'inactive', text, why: 'Xbox is the selected remote.' };
    if (!ctx.flyskyLive) return { state: 'blocked', text, why: 'FlySky signal not live.' };
    if (ctx.latched !== false) return { state: 'blocked', text, why: 'E-STOP latched.' };
    return { state: 'active', text, why: 'FlySky drives.' };
  }

  const api = { XBOX, FLYSKY, FLYSKY_KEYS, RAW, SW_LOW, SW_HIGH, STICK_RAW_DEAD, XBOX_AXES, XBOX_BUTTONS,
    xboxInputActive, xboxFunctionState, xboxLayoutOk, switchPosition, stickNorm, rolesFromConfig, configMismatches,
    flyskyFunctionState };
  if (typeof module === 'object' && module.exports) module.exports = api; else root.AtlasControllerMap = api;
})(typeof window !== 'undefined' ? window : this);
