/* ATLAS FlySky Driving page: live controller visualisation (Xbox 360 pad / FlySky FS-i6S). READ ONLY.
 *
 * It only reads: GET /api/controller_inputs (live Xbox /joy) and GET /api/flysky/state?history=0 (receiver channels),
 * plus the page state that flysky-drive.js broadcasts ('atlas:controller'). It has no POST, cannot select a remote,
 * cannot touch the E-STOP and cannot send a drive command: SELECT XBOX / SELECT FLYSKY live in flysky-drive.js and go
 * through the stop multiplexer. The drawings are original schematics (not product artwork), labelled as such.
 * Function labels come from controller-map.js; which FlySky channel drives what comes from the drive node's own
 * reported config, so the page cannot silently disagree with the rover.
 */
(() => {
  'use strict';
  const M = window.AtlasControllerMap;
  const SVGNS = 'http://www.w3.org/2000/svg';
  const $ = id => document.getElementById(id);
  const POLL_MS = 200, HIDDEN_MS = 2000, FLYSKY_CHANGE_S = 0.7;

  function s(tag, attrs, parent) {
    const n = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, String(v));
    if (parent) parent.append(n);
    return n;
  }
  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v); }
    for (const kid of kids) if (kid != null) n.append(kid);
    return n;
  }
  const setText = (n, t) => { if (n && n.textContent !== t) n.textContent = t; };
  const fmt = (x, d = 2) => (x == null || !isFinite(x)) ? '–' : (x >= 0 ? ' ' : '') + Number(x).toFixed(d);
  function text(parent, x, y, str, cls, anchor) { const t = s('text', { x, y, class: cls || '', 'text-anchor': anchor || 'start' }, parent); t.textContent = str; return t; }

  const STATE_WORD = { active: 'Active', inactive: 'Inactive', unassigned: 'Not used', blocked: 'Blocked', proposed: 'Proposed', planned: 'Planned' };

  // ---------------------------------------------------------------------------------------------- page state
  let view = null, pinned = false, ctl = null, xb = null, xbMissing = false, xbErr = false, fs = null, fsErr = false;
  let stage = null, timer = null;

  // ---------------------------------------------------------------------------------------------- callouts
  function callout(g, side, y, anchorPt, title) {
    const x = side === 'left' ? 24 : 916, w = 260, lx = side === 'left' ? x + w : x;
    const c = s('g', { class: 'cv-callout' }, g);
    s('path', { class: 'cv-lead', d: `M${lx} ${y + 18} L${side === 'left' ? lx + 18 : lx - 18} ${y + 18} L${anchorPt[0]} ${anchorPt[1]}` }, c);
    s('circle', { class: 'cv-lead-dot', cx: anchorPt[0], cy: anchorPt[1], r: 4 }, c);
    s('rect', { class: 'cv-co-box', x, y: y - 4, width: w, height: 70, rx: 10 }, c);
    const t1 = text(c, x + 12, y + 16, title, 'cv-co-title');
    const badge = s('g', { class: 'cv-badge' }, c);
    const br = s('rect', { x: x + w - 92, y: y + 43, width: 82, height: 20, rx: 10 }, badge);
    const bt = text(badge, x + w - 51, y + 57, '', 'cv-badge-t', 'middle');
    const t2 = text(c, x + 12, y + 38, '', 'cv-co-fn');
    const t3 = text(c, x + 12, y + 58, '', 'cv-co-val');
    return { g: c, title: t1, badge, br, bt, fn: t2, val: t3 };
  }
  function setBadge(co, st) { co.badge.setAttribute('class', 'cv-badge st-' + st); setText(co.bt, STATE_WORD[st] || st); co.g.setAttribute('data-state', st); }

  // ---------------------------------------------------------------------------------------------- Xbox drawing
  function buildXbox() {
    const svg = s('svg', { class: 'cv-svg cv-xbox', viewBox: '0 0 1200 640', role: 'img', 'aria-labelledby': 'cvTitleX' });
    const title = s('title', { id: 'cvTitleX' }, svg); title.textContent = 'Xbox 360 controller schematic with live input and the function of each control on ATLAS';
    const art = s('g', { class: 'cv-art' }, svg);
    const P = {};
    // triggers sit behind the bumpers
    P.lt = s('rect', { class: 'cv-ctl cv-trig', x: 372, y: 104, width: 120, height: 40, rx: 16 }, art);
    P.ltFill = s('rect', { class: 'cv-trig-fill', x: 372, y: 104, width: 0, height: 40, rx: 16 }, art);
    P.rt = s('rect', { class: 'cv-ctl cv-trig', x: 708, y: 104, width: 120, height: 40, rx: 16 }, art);
    P.rtFill = s('rect', { class: 'cv-trig-fill', x: 708, y: 104, width: 0, height: 40, rx: 16 }, art);
    text(art, 432, 130, 'LT', 'cv-tag', 'middle'); text(art, 768, 130, 'RT', 'cv-tag', 'middle');
    P.lb = s('rect', { class: 'cv-ctl', x: 360, y: 146, width: 150, height: 28, rx: 14 }, art);
    P.rb = s('rect', { class: 'cv-ctl', x: 690, y: 146, width: 150, height: 28, rx: 14 }, art);
    text(art, 435, 166, 'LB', 'cv-tag', 'middle'); text(art, 765, 166, 'RB', 'cv-tag', 'middle');
    s('path', { class: 'cv-body', d: 'M420 176 C500 160 700 160 780 176 C860 186 905 236 925 326 C948 436 958 522 888 548 C838 564 800 524 770 474 C742 432 702 420 600 420 C498 420 458 432 430 474 C400 524 362 564 312 548 C242 522 252 436 275 326 C295 236 340 186 420 176 Z' }, art);
    // left stick
    s('circle', { class: 'cv-well', cx: 420, cy: 266, r: 48 }, art);
    P.ls = s('circle', { class: 'cv-ctl cv-knob', cx: 420, cy: 266, r: 30 }, art);
    P.lsTag = text(art, 420, 272, 'LS', 'cv-tag cv-tag-sm', 'middle');
    // D-pad
    const dp = s('g', { class: 'cv-dpad' }, art);
    s('path', { class: 'cv-ctl-base', d: 'M492 324 h26 v26 h26 v26 h-26 v26 h-26 v-26 h-26 v-26 h26 Z' }, dp);
    P.dUp = s('rect', { class: 'cv-ctl cv-dir', x: 494, y: 326, width: 22, height: 24, rx: 4 }, dp);
    P.dDown = s('rect', { class: 'cv-ctl cv-dir', x: 494, y: 376, width: 22, height: 24, rx: 4 }, dp);
    P.dLeft = s('rect', { class: 'cv-ctl cv-dir', x: 468, y: 352, width: 24, height: 22, rx: 4 }, dp);
    P.dRight = s('rect', { class: 'cv-ctl cv-dir', x: 518, y: 352, width: 24, height: 22, rx: 4 }, dp);
    // right stick
    s('circle', { class: 'cv-well', cx: 695, cy: 363, r: 44 }, art);
    P.rs = s('circle', { class: 'cv-ctl cv-knob', cx: 695, cy: 363, r: 28 }, art);
    text(art, 695, 369, 'RS', 'cv-tag cv-tag-sm', 'middle');
    // face buttons (conventional colours identify the buttons; letters are the labels)
    const face = [['y', 790, 222, 'Y'], ['x', 748, 264, 'X'], ['b', 832, 264, 'B'], ['a', 790, 306, 'A']];
    for (const [id, cx, cy, lt] of face) {
      P[id] = s('circle', { class: 'cv-ctl cv-face cv-face-' + id, cx, cy, r: 21 }, art);
      text(art, cx, cy + 7, lt, 'cv-face-t', 'middle');
    }
    P.back = s('rect', { class: 'cv-ctl', x: 528, y: 256, width: 36, height: 18, rx: 9 }, art);
    P.start = s('rect', { class: 'cv-ctl', x: 636, y: 256, width: 36, height: 18, rx: 9 }, art);
    P.guide = s('circle', { class: 'cv-ctl', cx: 600, cy: 228, r: 24 }, art);
    text(art, 546, 296, 'Back', 'cv-tag cv-tag-xs', 'middle'); text(art, 654, 296, 'Start', 'cv-tag cv-tag-xs', 'middle');
    text(art, 600, 234, 'Guide', 'cv-tag cv-tag-xs', 'middle');
    // callouts for every assigned control; unused ones are grouped (and each is still named on the drawing)
    const C = {};
    const g = s('g', { class: 'cv-callouts' }, svg);
    C.lb = callout(g, 'left', 92, [360, 160], 'LB · button 4');
    C.ls = callout(g, 'left', 232, [372, 266], 'Left stick · axes 0 and 1');
    C.dpad = callout(g, 'left', 372, [466, 363], 'D-pad · axes 6 and 7');
    C.rb = callout(g, 'right', 92, [840, 160], 'RB · button 5');
    C.y = callout(g, 'right', 180, [811, 216], 'Y · button 3');
    C.b = callout(g, 'right', 268, [853, 264], 'B · button 1');
    C.rs = callout(g, 'right', 372, [739, 363], 'Right stick · axes 3 and 4');
    const un = s('g', { class: 'cv-callout cv-unused' }, g);
    s('rect', { class: 'cv-co-box', x: 290, y: 552, width: 620, height: 80, rx: 10 }, un);
    text(un, 306, 574, 'Not used on ATLAS', 'cv-co-title');
    text(un, 306, 596, 'A · X · LT · RT · Back · Start · Guide · both stick clicks · left stick left/right · right stick up/down', 'cv-co-fn cv-co-small');
    const unVal = text(un, 306, 619, '', 'cv-co-val');
    return { kind: 'XBOX', svg, P, C, unVal, title: 'Xbox 360 controller',
      caption: 'Original schematic of an Xbox 360 controller layout, not product artwork. Button numbers are the /joy indices this rover reads.' };
  }

  // ---------------------------------------------------------------------------------------------- FlySky drawing
  function buildFlysky() {
    const svg = s('svg', { class: 'cv-svg cv-flysky', viewBox: '0 0 1200 640', role: 'img', 'aria-labelledby': 'cvTitleF' });
    const title = s('title', { id: 'cvTitleF' }, svg); title.textContent = 'FlySky FS-i6S transmitter schematic with raw channel values and the function of each control on ATLAS';
    const art = s('g', { class: 'cv-art' }, svg);
    const P = {};
    // switches stand on the top edge; slot with a lever dot at up / middle / down
    const sw = [['swa', 400, 'SwA'], ['swb', 462, 'SwB'], ['swc', 738, 'SwC'], ['swd', 800, 'SwD']];
    for (const [id, x, lab] of sw) {
      P[id + 'Base'] = s('rect', { class: 'cv-ctl', x: x - 14, y: 46, width: 28, height: 72, rx: 10 }, art);
      P[id] = s('circle', { class: 'cv-lever', cx: x, cy: 60, r: 10 }, art);
      text(art, x, 36, lab, 'cv-tag', 'middle');
    }
    s('path', { class: 'cv-body', d: 'M360 150 C360 128 380 116 410 116 L790 116 C820 116 840 128 840 150 L862 300 C882 382 892 470 862 560 C846 602 790 606 760 576 L700 522 L500 522 L440 576 C410 606 354 602 338 560 C308 470 318 382 338 300 Z' }, art);
    P.screen = s('rect', { class: 'cv-screen', x: 512, y: 142, width: 176, height: 128, rx: 10 }, art);
    text(art, 600, 212, 'Touch screen', 'cv-tag cv-tag-xs cv-on-screen', 'middle');
    for (const [id, cx, lab] of [['vra', 432, 'VrA'], ['vrb', 768, 'VrB']]) {
      P[id] = s('circle', { class: 'cv-ctl cv-dial', cx, cy: 214, r: 24 }, art);
      P[id + 'Ptr'] = s('line', { class: 'cv-ptr', x1: cx, y1: 214, x2: cx, y2: 194 }, art);
      text(art, cx, 258, lab, 'cv-tag cv-tag-xs', 'middle');
    }
    for (const [id, x] of [['left', 440], ['right', 760]]) {
      P[id + 'Plate'] = s('rect', { class: 'cv-ctl cv-plate', x: x - 76, y: 330, width: 152, height: 152, rx: 18 }, art);
      s('line', { class: 'cv-cross', x1: x, y1: 342, x2: x, y2: 470 }, art);
      s('line', { class: 'cv-cross', x1: x - 64, y1: 406, x2: x + 64, y2: 406 }, art);
      P[id] = s('circle', { class: 'cv-knob cv-gimbal', cx: x, cy: 406, r: 17 }, art);
    }
    text(art, 440, 500, 'Left stick', 'cv-tag cv-tag-xs', 'middle'); text(art, 760, 500, 'Right stick', 'cv-tag cv-tag-xs', 'middle');
    s('circle', { class: 'cv-ctl-base', cx: 578, cy: 486, r: 9 }, art); s('circle', { class: 'cv-ctl-base', cx: 622, cy: 486, r: 9 }, art);
    text(art, 600, 512, 'Power', 'cv-tag cv-tag-xs', 'middle');
    // rear keys inset
    const rear = s('g', { class: 'cv-rear' }, art);
    s('rect', { class: 'cv-inset', x: 500, y: 548, width: 200, height: 76, rx: 10 }, rear);
    text(rear, 600, 568, 'Rear (back of the transmitter)', 'cv-tag cv-tag-xs', 'middle');
    P.key1 = s('circle', { class: 'cv-ctl', cx: 556, cy: 590, r: 11 }, rear); text(rear, 556, 617, 'Key 1', 'cv-tag cv-tag-xs', 'middle');
    P.key2 = s('circle', { class: 'cv-ctl', cx: 644, cy: 590, r: 11 }, rear); text(rear, 644, 617, 'Key 2', 'cv-tag cv-tag-xs', 'middle');
    const C = {};
    const g = s('g', { class: 'cv-callouts' }, svg);
    C.swa = callout(g, 'left', 40, [386, 100], 'SwA · CH5');
    C.swb = callout(g, 'left', 126, [448, 112], 'SwB · CH6');
    C.vra = callout(g, 'left', 212, [408, 214], 'VrA · CH9');
    C.left = callout(g, 'left', 372, [364, 406], 'Left stick · CH3 and CH4');
    C.swd = callout(g, 'right', 40, [814, 100], 'SwD · CH8');
    C.swc = callout(g, 'right', 126, [752, 112], 'SwC · CH7');
    C.vrb = callout(g, 'right', 212, [792, 214], 'VrB · CH10');
    C.right = callout(g, 'right', 372, [836, 406], 'Right stick · CH1 and CH2');
    const keys = s('g', { class: 'cv-callout' }, g);
    s('rect', { class: 'cv-co-box', x: 916, y: 556, width: 260, height: 58, rx: 10 }, keys);
    text(keys, 928, 578, 'Key 1 / Key 2 (rear)', 'cv-co-title'); text(keys, 928, 600, 'Not on any channel: not used', 'cv-co-fn');
    s('path', { class: 'cv-lead', d: 'M916 584 L700 590' }, keys);
    return { kind: 'FLYSKY', svg, P, C, title: 'FlySky FS-i6S',
      caption: 'Original schematic of the FlySky FS-i6S, not to scale and not product artwork. SwA and SwD have 2 positions, SwB and SwC have 3. Identify switches by the SwA to SwD labels printed on your transmitter.' };
  }

  // ---------------------------------------------------------------------------------------------- legend
  function legendRows(kind) {
    const rows = [];
    if (kind === 'XBOX') {
      for (const c of M.XBOX) for (const f of c.functions) {
        const input = f.button != null ? 'button ' + f.button : 'axis ' + f.axis;
        rows.push({ key: c.id + ':' + (f.button != null ? 'b' + f.button : 'a' + f.axis) + ':' + f.group, control: c.name, input, fn: f, detail: f.detail || '' });
      }
    } else {
      for (const c of M.FLYSKY) rows.push({ key: c.id, control: c.control, input: 'CH' + c.ch, ch: c });
      for (const k of M.FLYSKY_KEYS) rows.push({ key: k.id, control: k.name + ' (' + k.control.toLowerCase() + ')', input: 'none', key_: k });
    }
    return rows;
  }
  function buildLegend(kind) {
    const tb = $('cvLegendBody'); tb.textContent = '';
    const out = {};
    for (const r of legendRows(kind)) {
      const st = h('span', { class: 'cv-st' }), live = h('td', { class: 'cv-live' }), fn = h('td', { class: 'cv-fn' });
      const tr = h('tr', {}, h('th', { scope: 'row', text: r.control }), h('td', { class: 'cv-in', text: r.input }), live, fn, h('td', {}, st));
      tb.append(tr); out[r.key] = { tr, live, fn, st, r };
    }
    setText($('cvLegendInputHead'), kind === 'XBOX' ? 'Input' : 'Channel');
    setText($('cvLegendLiveHead'), kind === 'XBOX' ? 'Live' : 'Raw');
    return out;
  }
  function setRow(row, st, fnText, why, live, hot) {
    row.st.className = 'cv-st st-' + st; setText(row.st, STATE_WORD[st] || st);
    row.st.title = why || '';
    const want = fnText + (why ? '\n' : '');
    if (row.fn.dataset.v !== want + why) {
      row.fn.textContent = ''; row.fn.dataset.v = want + why;
      row.fn.append(h('b', { text: fnText }));
      if (why) row.fn.append(h('small', { text: why }));
    }
    setText(row.live, live);
    row.tr.classList.toggle('hot', !!hot);
  }

  // ---------------------------------------------------------------------------------------------- context
  function context() {
    const p = ctl && ctl.policy, d = ctl && ctl.drive, sDrv = d && d.status;
    const xbLive = !!(xb && xb.state === 'LIVE' && xb.layout_ok);
    const link = fs && fs.link, flags = fs && fs.flags;
    const fsLive = !!(link && link.state === 'LIVE' && !(flags && (flags.failsafe || flags.frame_lost)));
    return {
      controller: p && p.fresh ? p.manual_controller : null,
      latched: p && p.fresh ? p.stop_latched : null,
      enabled: !!(p && p.flysky_drive_enabled && sDrv && sDrv.config && sDrv.config.reviewed_by_owner && !(sDrv.config.errors || []).length),
      config: sDrv && sDrv.config || null,
      blockReason: ctl && ctl.blocked_reason,
      xboxLive: xbLive, flyskyLive: fsLive
    };
  }

  // ---------------------------------------------------------------------------------------------- Xbox update
  function updateXbox(ctx) {
    const st = stage, P = st.P, axes = (xb && xb.axes) || [], btn = (xb && xb.buttons) || [];
    const live = ctx.xboxLive;
    const on = i => live && btn[i] === 1;
    const ax = i => (live && isFinite(axes[i])) ? axes[i] : 0;
    const hot = (n, v) => n.classList.toggle('hot', !!v);
    // joy convention: +x is left, +y is up
    P.ls.setAttribute('cx', 420 - ax(0) * 18); P.ls.setAttribute('cy', 266 - ax(1) * 18);
    P.rs.setAttribute('cx', 695 - ax(3) * 16); P.rs.setAttribute('cy', 363 - ax(4) * 16);
    hot(P.ls, Math.abs(ax(0)) >= 0.1 || Math.abs(ax(1)) >= 0.1 || on(9)); hot(P.rs, Math.abs(ax(3)) >= 0.1 || Math.abs(ax(4)) >= 0.1 || on(10));
    P.ls.classList.toggle('pressed', on(9)); P.rs.classList.toggle('pressed', on(10));
    const trig = i => live && isFinite(axes[i]) ? Math.max(0, Math.min(1, (1 - axes[i]) / 2)) : 0;
    P.ltFill.setAttribute('width', 120 * trig(2)); P.rtFill.setAttribute('width', 120 * trig(5));
    hot(P.lt, trig(2) > 0.05); hot(P.rt, trig(5) > 0.05);
    for (const [id, b] of [['a', 0], ['b', 1], ['x', 2], ['y', 3], ['lb', 4], ['rb', 5], ['back', 6], ['start', 7], ['guide', 8]]) hot(P[id], on(b));
    hot(P.dLeft, ax(6) >= 0.5); hot(P.dRight, ax(6) <= -0.5); hot(P.dUp, ax(7) >= 0.5); hot(P.dDown, ax(7) <= -0.5);
    st.svg.classList.toggle('cv-dim', !live);

    // callouts (assigned controls)
    const fnState = (c, f) => M.xboxFunctionState(f, ctx);
    const best = list => ['active', 'blocked', 'inactive', 'unassigned'].find(x => list.includes(x)) || 'unassigned';
    const byId = Object.fromEntries(M.XBOX.map(c => [c.id, c]));
    const valStick = (a, b) => live ? 'x' + fmt(ax(a)) + '   y' + fmt(ax(b)) : 'no live input';
    const co = (id, fn, val, stOverride) => {
      const c = st.C[id]; const states = byId[id].functions.filter(f => f.group !== 'none').map(f => fnState(byId[id], f).state);
      setBadge(c, stOverride || best(states)); setText(c.fn, fn); setText(c.val, val);
      c.g.classList.toggle('hot', byId[id].functions.some(f => M.xboxInputActive(f, live ? axes : [], live ? btn : [])));
    };
    co('lb', ctx.latched !== false ? 'E-STOP reset: hold 2 s, then release' : 'Hold to drive (dead-man)', live ? (on(4) ? 'pressed' : 'released') : 'no live input');
    co('rb', 'Turbo while LB is held', live ? (on(5) ? 'pressed' : 'released') : 'no live input');
    co('ls', 'Up / down: forward / reverse', valStick(0, 1));
    co('rs', 'Left / right: steering', valStick(3, 4));
    co('b', 'REMOTE STOP: latches the E-STOP', live ? (on(1) ? 'PRESSED' : 'released') : 'no live input');
    co('y', 'Camera home', live ? (on(3) ? 'pressed' : 'released') : 'no live input');
    co('dpad', 'Camera pan / tilt', live ? 'x' + fmt(ax(6), 0) + '   y' + fmt(ax(7), 0) : 'no live input');
    const unused = [];
    if (live) {
      for (const [n, b] of [['A', 0], ['X', 2], ['Back', 6], ['Start', 7], ['Guide', 8], ['LS click', 9], ['RS click', 10]]) if (on(b)) unused.push(n);
      if (trig(2) > 0.05) unused.push('LT'); if (trig(5) > 0.05) unused.push('RT');
    }
    setText(st.unVal, !live ? 'No live input' : unused.length ? 'Pressed now: ' + unused.join(', ') + ' (no effect, but blocks the E-STOP reset)' : 'Nothing pressed');

    // legend
    for (const row of Object.values(st.rows)) {
      const f = row.r.fn, sf = M.xboxFunctionState(f, ctx);
      let v = '–';
      if (live) {
        if (f.button != null) v = btn[f.button] === 1 ? 'pressed' : 'released';
        else if (f.axis === 2 || f.axis === 5) v = Math.round(trig(f.axis) * 100) + ' %';
        else v = fmt(axes[f.axis]);
      }
      setRow(row, sf.state, f.text, (f.detail ? f.detail + ' ' : '') + sf.why, v, live && M.xboxInputActive(f, axes, btn));
    }
  }

  // ---------------------------------------------------------------------------------------------- FlySky update
  function chanMap() {
    const m = {};
    for (const c of (fs && fs.channels) || []) m[c.channel] = c;
    return m;
  }
  function updateFlysky(ctx) {
    const st = stage, P = st.P, ch = chanMap();
    const linkLive = !!(fs && fs.link && fs.link.state === 'LIVE');
    const raw = n => ch[n] && isFinite(ch[n].raw) ? ch[n].raw : null;
    const changed = n => !!(linkLive && ch[n] && ch[n].changed_ago_s != null && ch[n].changed_ago_s < FLYSKY_CHANGE_S);
    const hot = (n, v) => n.classList.toggle('hot', !!v);
    // switches
    for (const c of M.FLYSKY.filter(x => x.kind === 'switch')) {
      const r = raw(c.ch), pos = M.switchPosition(r, c.positions);
      const y = pos === 'up' ? 60 : pos === 'down' ? 104 : 82;
      P[c.id].setAttribute('cy', y); P[c.id].classList.toggle('unknown', pos == null);
      hot(P[c.id + 'Base'], changed(c.ch)); hot(P[c.id], changed(c.ch));
    }
    // knobs: -135..135 degrees
    for (const [id, n, cx] of [['vra', 9, 432], ['vrb', 10, 768]]) {
      const v = M.stickNorm(raw(n)), a = (v == null ? 0 : v) * 135 * Math.PI / 180;
      P[id + 'Ptr'].setAttribute('x2', cx + 20 * Math.sin(a)); P[id + 'Ptr'].setAttribute('y2', 214 - 20 * Math.cos(a));
      hot(P[id], changed(n));
    }
    // sticks: raw 1807 = right / up on this transmitter (verified)
    const stick = (id, x0, nx, ny) => {
      const vx = M.stickNorm(raw(nx)), vy = M.stickNorm(raw(ny));
      P[id].setAttribute('cx', x0 + (vx || 0) * 58); P[id].setAttribute('cy', 406 - (vy || 0) * 58);
      const dev = [nx, ny].some(n => raw(n) != null && Math.abs(raw(n) - M.RAW.mid) > M.STICK_RAW_DEAD);
      hot(P[id], linkLive && (dev || changed(nx) || changed(ny))); hot(P[id + 'Plate'], linkLive && (dev || changed(nx) || changed(ny)));
    };
    stick('left', 440, 4, 3); stick('right', 760, 1, 2);
    st.svg.classList.toggle('cv-dim', !linkLive);

    const fsState = c => M.flyskyFunctionState(c, ctx);
    const byCh = Object.fromEntries(M.FLYSKY.map(c => [c.ch, c]));
    const shortFn = c => { const r = fsState(c); return { st: r.state, text: r.state === 'unassigned' ? 'Not used' : r.state === 'planned' ? (c.ch === 9 ? 'Camera pan (planned)' : 'Camera tilt (planned)') : r.text.split(' (')[0] }; };
    const rv = n => raw(n) == null ? '–' : String(raw(n));
    const posWord = c => { const p = M.switchPosition(raw(c.ch), c.positions); return p == null ? 'no value' : p.toUpperCase(); };
    for (const id of ['swa', 'swb', 'swc', 'swd']) {
      const c = M.FLYSKY.find(x => x.id === id), f = shortFn(c), co = st.C[id];
      setBadge(co, f.st); setText(co.fn, f.text); setText(co.val, 'raw ' + rv(c.ch) + ' · ' + posWord(c)); co.g.classList.toggle('hot', changed(c.ch));
    }
    for (const [id, n] of [['vra', 9], ['vrb', 10]]) {
      const f = shortFn(byCh[n]), co = st.C[id];
      setBadge(co, f.st); setText(co.fn, f.text); setText(co.val, 'raw ' + rv(n)); co.g.classList.toggle('hot', changed(n));
    }
    const stickCo = (id, nx, ny) => {
      const fx = shortFn(byCh[nx]), fy = shortFn(byCh[ny]), co = st.C[id];
      const rank = ['blocked', 'active', 'inactive', 'proposed', 'planned', 'unassigned'];
      setBadge(co, rank.find(x => x === fx.st || x === fy.st));
      setText(co.fn, (fx.st === 'unassigned' && fy.st === 'unassigned') ? 'Not used' : 'CH' + nx + ' ' + fx.text.toLowerCase() + ' · CH' + ny + ' ' + fy.text.toLowerCase());
      setText(co.val, 'CH' + nx + ' ' + rv(nx) + ' · CH' + ny + ' ' + rv(ny));
      co.g.classList.toggle('hot', changed(nx) || changed(ny));
    };
    stickCo('left', 4, 3); stickCo('right', 1, 2);

    for (const row of Object.values(st.rows)) {
      if (row.r.key_) { setRow(row, 'unassigned', 'Not used', row.r.key_.note, '–', false); continue; }
      const c = row.r.ch, r = fsState(c);
      const full = r.state === 'unassigned' ? 'Not assigned' : r.text;
      const extra = c.kind === 'switch' ? ' · ' + posWord(c) : '';
      setRow(row, r.state, full, r.why, rv(c.ch) + extra, changed(c.ch) || (c.kind.startsWith('stick') && raw(c.ch) != null && linkLive && Math.abs(raw(c.ch) - M.RAW.mid) > M.STICK_RAW_DEAD));
    }
  }

  // ---------------------------------------------------------------------------------------------- frame + status
  function signalText(kind) {
    if (kind === 'XBOX') {
      if (xbMissing) return { cls: 'warn', t: 'Xbox live input: dashboard update not installed' };
      if (xbErr || !xb) return { cls: 'fail', t: 'Xbox input: no reply' };
      if (xb.state === 'LIVE' && !xb.layout_ok) return { cls: 'fail', t: 'Xbox: unexpected layout (' + xb.axes.length + ' axes, ' + xb.buttons.length + ' buttons)' };
      return { LIVE: { cls: 'ok', t: 'Xbox connected' }, STALE: { cls: 'fail', t: 'Xbox signal lost (' + fmt(xb.age_s, 1).trim() + ' s)' },
        LOST: { cls: 'fail', t: 'Xbox signal lost' }, NO_DATA: { cls: 'fail', t: 'Xbox not connected' } }[xb.state] || { cls: 'fail', t: 'Xbox: ' + xb.state };
    }
    if (fsErr || !fs) return { cls: 'fail', t: 'FlySky receiver: no reply' };
    const l = fs.link || {}, f = fs.flags || {};
    if (l.state === 'LIVE' && f.failsafe) return { cls: 'fail', t: 'FlySky receiver failsafe' };
    if (l.state === 'LIVE' && f.frame_lost) return { cls: 'warn', t: 'FlySky frames dropped' };
    return { cls: l.state === 'LIVE' ? 'ok' : 'fail', t: 'FlySky: ' + (l.label || l.state || 'unknown').toLowerCase() };
  }
  const SOURCE = { STOPPED: 'nothing (stopped)', REMOTE: 'Xbox', FLYSKY: 'FlySky' };

  function updateFrame(ctx) {
    const p = ctl && ctl.policy;
    const selected = ctx.controller === 'XBOX' ? 'Xbox' : ctx.controller === 'FLYSKY' ? 'FlySky' : 'unknown';
    const viewing = view === 'XBOX' ? 'Xbox' : 'FlySky';
    for (const [id, k] of [['cvTabX', 'XBOX'], ['cvTabF', 'FLYSKY']]) {
      const b = $(id); b.setAttribute('aria-selected', String(view === k)); b.classList.toggle('on', view === k);
      setText(b.querySelector('.cv-tab-sel'), ctx.controller === k ? 'Selected remote' : 'Not selected');
    }
    const note = $('cvViewNote');
    if (!ctx.controller) setText(note, 'Selected remote unknown. Showing ' + viewing + '.');
    else if ((view === 'XBOX') === (ctx.controller === 'XBOX')) setText(note, 'Showing the selected remote: ' + selected + '.');
    else setText(note, 'Preview only: showing ' + viewing + '. The selected remote is still ' + selected + '. Use SELECT above to change it.');
    note.className = 'cv-viewnote' + (ctx.controller && (view === 'XBOX') !== (ctx.controller === 'XBOX') ? ' preview' : '');
    $('cvFollow').hidden = !pinned;

    const sig = signalText(view);
    const so = $('cvSignal'); so.className = 'cv-pill ' + sig.cls; setText(so, sig.t);
    const es = $('cvEstop'); const lat = ctx.latched;
    es.className = 'cv-pill ' + (lat === true ? 'ok' : lat === false ? 'warn' : 'fail');
    setText(es, lat === true ? 'E-STOP latched' : lat === false ? 'E-STOP released' : 'E-STOP state unknown');
    const gate = $('cvGate'); gate.className = 'cv-pill ' + (ctx.enabled ? 'warn' : '');
    setText(gate, ctx.enabled ? 'FlySky driving enabled' : 'FlySky driving off');
    setText($('cvSel'), 'Selected remote: ' + selected);
    setText($('cvSrc'), 'Command source: ' + (p && p.fresh ? (SOURCE[p.source] || String(p.source).toLowerCase()) : 'unknown'));

    const lost = $('cvLost');
    const stale = view === 'XBOX' ? !ctx.xboxLive : !(fs && fs.link && fs.link.state === 'LIVE');
    lost.hidden = !stale;
    if (stale) {
      const ls = fs && fs.link && fs.link.state;
      const fsMsg = { FAILSAFE: 'Receiver failsafe: the transmitter is off or out of range. The values shown are the receiver\'s failsafe output, not your sticks.',
        FRAME_LOST: 'The receiver reports dropped frames. Values may lag.',
        NO_SOURCE: 'No receiver data is reaching the rover.', NO_FRAMES: 'No receiver frame received yet.' }[ls] || 'No live FlySky signal. Values shown are not live.';
      setText(lost, view === 'XBOX' ? (xbMissing ? 'Live Xbox input is not installed on the rover yet. Labels are correct; nothing moves on the drawing.'
        : 'No live Xbox input. Values shown are not live.') : fsErr ? 'The rover did not answer. Values shown are not live.' : fsMsg);
    }
    const mm = view === 'FLYSKY' ? M.configMismatches(ctx.config) : [];
    const warn = $('cvMismatch'); warn.hidden = !mm.length;
    if (mm.length) setText(warn, 'The running drive config differs from the verified channel layout: ' + mm.join('; ') + '.');
  }

  function render() {
    if (!stage) return;
    const ctx = context();
    if (stage.kind === 'XBOX') updateXbox(ctx); else updateFlysky(ctx);
    updateFrame(ctx);
  }

  // ---------------------------------------------------------------------------------------------- view switching
  function show(kind, byUser) {
    if (byUser) pinned = true;
    if (view === kind && stage) { render(); return; }
    view = kind;
    const box = $('cvStage'); box.textContent = '';
    stage = kind === 'XBOX' ? buildXbox() : buildFlysky();
    box.append(stage.svg);
    setText($('cvCaption'), stage.caption);
    stage.rows = buildLegend(kind);
    setText($('cvLegendTitle'), kind === 'XBOX' ? 'Xbox controls on ATLAS' : 'FlySky controls on ATLAS');
    fitView();
    render();
    restart();
  }
  function fitView() {
    if (!stage) return;
    const narrow = window.matchMedia('(max-width: 760px)').matches;
    stage.svg.setAttribute('viewBox', narrow ? (stage.kind === 'XBOX' ? '250 90 700 480' : '300 20 600 615') : '0 0 1200 640');
    stage.svg.classList.toggle('narrow', narrow);
  }

  // ---------------------------------------------------------------------------------------------- polling (GET only)
  async function pollOnce() {
    const kind = view;
    try {
      if (kind === 'XBOX') {
        const r = await fetch('/api/controller_inputs', { cache: 'no-store' });
        if (r.status === 404) { xbMissing = true; xb = null; xbErr = false; }
        else if (!r.ok) throw new Error(String(r.status));
        else { const j = await r.json(); xb = j.xbox; xbMissing = false; xbErr = false; }
      } else {
        const r = await fetch('/api/flysky/state?history=0', { cache: 'no-store' });
        if (!r.ok) throw new Error(String(r.status));
        fs = await r.json(); fsErr = false;
      }
    } catch (e) {
      if (kind === 'XBOX') { xbErr = true; xb = null; } else { fsErr = true; fs = null; }
    }
    if (kind === view) render();
  }
  function restart() { clearTimeout(timer); loop(); }
  async function loop() {
    await pollOnce();
    timer = setTimeout(loop, document.hidden ? HIDDEN_MS : POLL_MS);
  }

  window.addEventListener('atlas:controller', e => {
    ctl = e.detail;
    const c = ctl && ctl.policy && ctl.policy.fresh ? ctl.policy.manual_controller : null;
    if (!pinned && (c === 'XBOX' || c === 'FLYSKY') && c !== view) show(c, false); else render();
  });
  $('cvTabX').addEventListener('click', () => show('XBOX', true));
  $('cvTabF').addEventListener('click', () => show('FLYSKY', true));
  $('cvFollow').addEventListener('click', () => {
    pinned = false; const c = ctl && ctl.policy && ctl.policy.manual_controller;
    show(c === 'FLYSKY' ? 'FLYSKY' : 'XBOX', false);
  });
  window.matchMedia('(max-width: 760px)').addEventListener('change', fitView);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) restart(); });
  show('XBOX', false);
})();
