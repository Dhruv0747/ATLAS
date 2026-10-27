/* ATLAS FlySky Remote Test Lab (client). READ ONLY.
 * Talks only to /api/flysky/*; the only POSTs it can make are record start/stop and "reset min/max".
 * The dock E-STOP is the shared /v2/estop.js button. Nothing here can send a drive command. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const COLORS = ['#22B8F0', '#7CC242', '#F2B33D', '#B79CFF', '#FF8A95', '#5FD6C2', '#E8D36A', '#8FA8FF'];
  const DASH = [[], [7, 4], [2, 4], [10, 4, 2, 4]];
  const MAXCH = 16;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  };
  const load = (k, d) => { try { const v = JSON.parse(store.get(k)); return v == null ? d : v; } catch (e) { return d; } };
  let st = null, show = 'moved', busy = false;
  const assign = load('atlasFlyskyAssign', { lx: 0, ly: 0, rx: 0, ry: 0 });
  const labels = load('atlasFlyskyLabels', {});

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v); }
    for (const kid of kids) if (kid != null) n.append(kid);
    return n;
  }
  const setText = (n, t) => { if (n && n.textContent !== t) n.textContent = t; };
  const fmt = (v, d = 2) => (v == null || !isFinite(v)) ? '–' : Number(v).toFixed(d);

  async function api(body) {
    const r = await fetch('/api/flysky/action', {
      method: 'POST', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-Atlas-Flysky': '1' }, body: JSON.stringify(body)
    });
    let j = {}; try { j = await r.json(); } catch (e) { /* not JSON */ }
    if (!r.ok) throw new Error(j.error || ('Request refused (' + r.status + ')'));
    return j;
  }

  // ---------- sticks ----------
  const sticks = {};
  function buildSticks() {
    const host = $('sticks');
    for (const [side, title] of [['l', 'Left stick'], ['r', 'Right stick']]) {
      const dot = el('div', { class: 'fs-dot' }), pad = el('div', { class: 'fs-pad off', role: 'img', 'aria-label': title + ' position' }, dot);
      const outs = {}, sel = el('div', { class: 'fs-sel' });
      for (const [axis, name] of [['x', 'Left–right'], ['y', 'Up–down']]) {
        const s = el('select', { 'aria-label': title + ' ' + name + ' channel' });
        s.append(el('option', { value: '0', text: 'not assigned' }));
        for (let i = 1; i <= MAXCH; i++) s.append(el('option', { value: String(i), text: 'CH' + i }));
        s.value = String(assign[side + axis] || 0);
        s.addEventListener('change', () => { assign[side + axis] = Number(s.value); store.set('atlasFlyskyAssign', JSON.stringify(assign)); if (st) renderSticks(); });
        outs[axis] = el('output', { text: '–' });
        sel.append(el('label', {}, el('span', { text: name }), s), el('div', {}, el('span', { text: 'now ' }), outs[axis]));
      }
      host.append(el('div', { class: 'fs-stick' }, el('h3', { text: title }), pad, sel));
      sticks[side] = { pad, dot, outs };
    }
  }
  function chan(n) { return st && st.channels.find(c => c.channel === n); }
  function renderSticks() {
    for (const side of ['l', 'r']) {
      const s = sticks[side], cx = assign[side + 'x'] ? chan(assign[side + 'x']) : null, cy = assign[side + 'y'] ? chan(assign[side + 'y']) : null;
      const live = st.link.verified;
      s.pad.classList.toggle('off', !(live && (cx || cy)));
      const x = cx && cx.norm != null ? cx.norm : 0, y = cy && cy.norm != null ? cy.norm : 0;
      s.dot.style.left = (50 + 44 * Math.max(-1, Math.min(1, x))) + '%';
      s.dot.style.top = (50 - 44 * Math.max(-1, Math.min(1, y))) + '%';
      setText(s.outs.x, cx ? fmt(cx.norm, 2) + dirWord(cx, 'x') : '–');
      setText(s.outs.y, cy ? fmt(cy.norm, 2) + dirWord(cy, 'y') : '–');
    }
  }
  function dirWord(c, axis) {
    if (c.direction === 'steady') return '';
    return c.direction === 'up' ? (axis === 'x' ? ' → right' : ' ↑ up') : (axis === 'x' ? ' ← left' : ' ↓ down');
  }

  // ---------- channel rows ----------
  const rows = [];
  function buildRows() {
    const host = $('chans');
    for (let i = 1; i <= MAXCH; i++) {
      const inp = el('input', { type: 'text', maxlength: '24', 'aria-label': 'Label for channel ' + i, placeholder: 'label', value: labels[i] || '' });
      inp.addEventListener('input', () => { labels[i] = inp.value; store.set('atlasFlyskyLabels', JSON.stringify(labels)); });
      const o = {
        row: el('div', { class: 'fs-row', hidden: '' }), raw: el('span', { class: 'raw' }), nrm: el('span', { class: 'nrm' }),
        bar: el('div', { class: 'fs-bar' }, el('i')), arrow: el('span', { class: 'fs-arrow' }), mv: el('span'), rg: el('span', { class: 'rg' }), pos: el('span')
      };
      o.row.append(el('div', { class: 'nm' }, el('b', { text: 'CH' + i }), inp), o.raw, o.nrm, o.bar, el('div', { class: 'mv' }, o.arrow, o.mv), o.rg);
      host.append(o.row); rows.push(o);
    }
    host.append(el('div', { class: 'fs-empty', id: 'noChans', text: 'No channel data yet.' }));
  }
  function renderChannels() {
    const list = st.channels, by = {}; for (const c of list) by[c.channel] = c;
    setText($('noChans'), st.link.state === 'NO_SOURCE' || st.link.state === 'NO_FRAMES'
      ? 'No channel data. ' + st.link.reason : 'Waiting for channel data…');
    $('noChans').hidden = list.length > 0;
    rows.forEach((o, k) => {
      const c = by[k + 1]; o.row.hidden = !c; if (!c) return;
      const fresh = st.link.verified || st.link.state === 'FAILSAFE' || st.link.state === 'FRAME_LOST';
      o.row.classList.toggle('old', !fresh);
      o.row.classList.toggle('hot', fresh && c.changed_ago_s != null && c.changed_ago_s < 1.5 && c.moved);
      o.row.classList.toggle('sw', c.kind === 'switch');
      setText(o.raw, c.raw == null ? '–' : String(c.raw)); setText(o.nrm, fmt(c.norm, 2));
      const bar = o.bar.firstChild, v = Math.max(-1, Math.min(1, c.norm || 0));
      bar.style.left = (v < 0 ? 50 + v * 50 : 50) + '%'; bar.style.width = Math.abs(v) * 50 + '%';
      o.arrow.textContent = c.direction === 'up' ? '▲' : c.direction === 'down' ? '▼' : '·';
      setText(o.mv, c.kind === 'switch' ? 'switch ' + (c.switch_position || '') : c.kind === 'analog' ? 'analog' : 'not moved yet');
      setText(o.rg, c.min == null ? '–' : c.min + ' – ' + c.max);
    });
  }

  // ---------- graph ----------
  function renderGraph() {
    const cv = $('graph'), dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const x = cv.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, h);
    x.font = '11px system-ui'; x.fillStyle = '#8DA3B8'; x.strokeStyle = 'rgba(128,190,236,.14)';
    const g = st.graph, L = 38, R = 8, T = 8, B = 20;
    const maxN = window.AtlasFlyskyMap ? window.AtlasFlyskyMap.maxVisible() : MAXCH;          // CH11-16 only with the raw SBUS toggle
    const want = (g && g.ch || []).map((_, i) => i + 1).filter(n => n <= maxN && (show === 'all' || (chan(n) && chan(n).moved)));
    if (!g || !g.t.length) { x.fillText(st.link.verified ? 'Waiting for frames…' : 'No receiver frames to graph.', L + 10, h / 2); renderLegend([]); return; }
    if (!want.length) { x.fillText('Move a stick or flip a switch to graph its channel.', L + 10, h / 2); renderLegend([]); return; }
    const X = t => L + (t + 30) / 30 * (w - L - R), Y = v => T + (1 - (v + 1.1) / 2.2) * (h - T - B);
    for (const v of [-1, -0.5, 0, 0.5, 1]) { const y = Y(v); x.beginPath(); x.moveTo(L, y); x.lineTo(w - R, y); x.stroke(); x.fillText(v.toFixed(1), 4, y + 4); }
    for (const t of [-30, -20, -10, 0]) x.fillText(t === 0 ? 'now' : t + ' s', X(t) - 12, h - 5);
    for (const n of want) {
      const k = n - 1; x.beginPath(); x.setLineDash(DASH[Math.floor(k / 8) % 4]); x.strokeStyle = COLORS[k % 8]; x.lineWidth = 2;
      let started = false;
      g.ch[k].forEach((v, i) => { if (v == null) return; const px = X(g.t[i]), py = Y(v); started ? x.lineTo(px, py) : x.moveTo(px, py); started = true; });
      x.stroke();
    }
    x.setLineDash([]); renderLegend(want);
  }
  let legendKey = '';
  function renderLegend(want) {
    const key = want.join(','); if (key === legendKey) return; legendKey = key;
    const host = $('legend'); host.textContent = '';
    for (const n of want) { const k = n - 1, i = el('i'); i.style.borderTop = '3px solid ' + COLORS[k % 8]; host.append(el('span', {}, i, 'CH' + n + (labels[n] ? ' ' + labels[n] : ''))); }
  }

  // ---------- link / chips / banner ----------
  const BADGE = { LIVE: 'ok', NO_SOURCE: 'warn', NO_FRAMES: 'warn', STALE: 'warn', LOST: 'fail', FAILSAFE: 'fail', FRAME_LOST: 'warn' };
  function chip(id, cls, text) { const n = $(id); n.className = 'chip ' + cls; setText(n, text); }
  function renderChips() {
    chip('chipLink', BADGE[st.link.state] || 'warn', st.link.label);
    chip('chipRate', st.link.verified ? 'ok' : 'warn', st.link.rate_hz ? st.link.rate_hz + ' frames/s' : 'No frames');
    const s = st.session; chip('chipRec', s ? 'info' : '', s ? 'Recording · ' + s.frames + ' frames' : 'Not recording');
  }
  function renderBanner() {
    const b = $('banner'); b.hidden = false;
    b.className = 'tl-banner' + (st.link.state === 'LIVE' ? ' ok' : (st.link.state === 'LOST' || st.link.state === 'FAILSAFE') ? ' fail' : '');
    b.textContent = '';
    b.append(el('span', { class: 'big', text: st.link.label }), document.createTextNode(st.link.reason));
    if (st.channels.length && !(st.link.state === 'LIVE' || st.link.state === 'FAILSAFE' || st.link.state === 'FRAME_LOST')) b.append(el('span', { class: 'fs-oldnote', text: 'Channel values below are the last known values, not live.' }));
  }
  function row(dl, k, v, cls) { dl.append(el('dt', { text: k }), el('dd', { class: cls || '', text: v })); }
  function renderInfo() {
    const dl = $('linkInfo'); dl.textContent = '';
    const l = st.link, f = st.frames, p = l.protocol ? f[l.protocol] : null, fl = st.flags;
    row(dl, 'Link', l.label, l.verified ? 'ok' : 'bad');
    row(dl, 'Source topic', st.topic + (st.publishers ? ' (' + st.publishers + ' publisher)' : ' (no publisher)'), st.publishers ? '' : 'dim');
    row(dl, 'Protocol', l.protocol ? l.protocol.toUpperCase() : 'none decoded yet', l.protocol ? '' : 'dim');
    row(dl, 'Frame rate', l.rate_hz ? l.rate_hz + ' Hz' : '–');
    row(dl, 'Last frame', l.frame_age_s == null ? 'never' : fmt(l.frame_age_s, 2) + ' s ago', l.frame_age_s != null && l.frame_age_s > l.live_max_age_s ? 'bad' : '');
    row(dl, 'Valid frames', String(l.frames_total));
    const bad = (f.sbus.invalid + f.sbus.incomplete + f.ibus.invalid + f.ibus.incomplete);
    row(dl, 'Rejected frames', bad + (p ? '  (resyncs ' + (f.sbus.resyncs + f.ibus.resyncs) + ')' : ''), bad ? 'bad' : '');
    row(dl, 'Failsafe flag', fl.observable ? (fl.failsafe ? 'ACTIVE' : 'clear') + ' · seen ' + fl.failsafe_count + '×' : 'not observable', fl.failsafe ? 'bad' : fl.observable ? 'ok' : 'dim');
    row(dl, 'Frame-lost flag', fl.observable ? (fl.frame_lost ? 'ACTIVE' : 'clear') + ' · seen ' + fl.frame_lost_count + '×' : 'not observable', fl.frame_lost ? 'bad' : fl.observable ? 'ok' : 'dim');
    row(dl, 'Signal strength', 'not available', 'dim');
    dl.append(el('dt', { text: '' }), el('dd', { class: 'dim', text: st.rssi.note }));
  }
  function renderDigital() {
    const d = $('digital'); d.textContent = '';
    if (st.digital) for (const k of ['ch17', 'ch18']) d.append(el('span', { class: 'tl-badge ' + (st.digital[k] ? 'ok' : ''), text: k.toUpperCase().replace('CH', 'Digital ch ') + ': ' + (st.digital[k] ? 'on' : 'off') }));
  }

  // ---------- recording ----------
  function renderRec() {
    const s = st.session; $('recStart').disabled = !!s; $('recStop').disabled = !s;
    const a = $('csvCurrent');
    if (s) { setText($('recInfo'), 'Recording. ' + s.frames + ' frames saved so far' + (s.truncated ? ' (limit reached)' : '') + '.'); a.hidden = false; a.href = '/api/flysky/session.csv?id=' + s.id; }
    else if (st.last_session) { setText($('recInfo'), 'Last session: ' + st.last_session.rows + ' rows.'); a.hidden = false; a.href = '/api/flysky/session.csv?id=' + st.last_session.id; }
    else { setText($('recInfo'), 'No session open.'); a.hidden = true; }
    const ul = $('files'); const key = (st.saved_files || []).join('|');
    if (ul.dataset.k !== key) { ul.dataset.k = key; ul.textContent = ''; for (const f of (st.saved_files || []).slice().reverse()) { const m = /_([0-9a-f]{12})\.csv$/.exec(f); ul.append(el('li', {}, m ? el('a', { href: '/api/flysky/session.csv?id=' + m[1], text: f }) : document.createTextNode(f))); } if (!key) ul.append(el('li', { class: 'tl-note', text: 'None yet.' })); }
  }

  function render() { if (!st) return; renderChips(); renderBanner(); renderSticks(); renderChannels(); renderGraph(); renderInfo(); renderDigital(); renderRec(); }

  async function poll() {
    try {
      const r = await fetch('/api/flysky/state', { cache: 'no-store' });
      if (!r.ok) throw new Error(String(r.status));
      st = await r.json(); render();
      document.dispatchEvent(new CustomEvent('atlas-flysky-state', { detail: st }));   // read by flysky-mapping.js (no extra request)
    } catch (e) {
      const b = $('banner'); b.hidden = false; b.className = 'tl-banner fail'; b.textContent = 'Cannot reach the FlySky Test Lab service on the rover.';
      chip('chipLink', 'fail', 'Service unreachable');
    }
    setTimeout(poll, document.hidden ? 2000 : 250);
  }
  async function run(body) {
    if (busy) return; busy = true;
    try { await api(body); } catch (e) { setText($('recInfo'), e.message); } finally { busy = false; }
  }
  function wire() {
    for (const b of document.querySelectorAll('[data-show]')) b.addEventListener('click', () => { show = b.dataset.show; for (const x of document.querySelectorAll('[data-show]')) x.classList.toggle('on', x === b); legendKey = ''; if (st) renderGraph(); });
    $('recStart').addEventListener('click', () => run({ action: 'session_start' }));
    $('recStop').addEventListener('click', () => run({ action: 'session_stop' }));
    $('resetRange').addEventListener('click', () => run({ action: 'reset_ranges' }));
  }
  buildSticks(); buildRows(); wire(); poll();
})();
