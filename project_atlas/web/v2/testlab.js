/* ATLAS Motor & Encoder Test Lab (client). Display, hand-test and one gated, bounded pulse request.
 * Talks only to /api/testlab/* and, for the page E-STOP, to the same request estop.js sends.
 * It cannot send arbitrary motor values: the server accepts exactly the actions listed in atlas_testlab_web.ACTIONS. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const C_M = 0.392699;
  const COLORS = ['#22B8F0', '#7CC242', '#F2B33D', '#B79CFF'];
  const DASH = [[], [7, 4], [2, 4], [10, 4, 2, 4]];
  const NAMES = ['M1 rear-left', 'M2 rear-right', 'M3 front-left', 'M4 front-right'];
  const FAULT_TEXT = {
    FROZEN_COUNTS: 'Frozen counts', MISSING_PULSES: 'Missing pulses', UNEXPECTED_SIGN: 'Unexpected direction',
    STALE_DATA: 'Stale encoder data', NO_DATA: 'No encoder data', COUNT_JUMP: 'Count jump',
    SEQUENCE_GAP: 'Update sequence reset', CONSENSUS_REJECTED: 'Excluded by the base driver'
  };
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  };
  let st = null, lastOk = 0, selected = Number(store.get('atlasTestlabWheel')) || 1, unit = 'turns', hdir = 'forward', busy = false;
  if (![1, 2, 3, 4].includes(selected)) selected = 1;

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v);
    }
    for (const kid of kids) if (kid != null) n.append(kid);
    return n;
  }
  const setText = (n, t) => { if (n.textContent !== t) n.textContent = t; };
  const fmt = (v, d = 2) => (v == null || !isFinite(v)) ? '–' : Number(v).toFixed(d);
  const SVGNS = 'http://www.w3.org/2000/svg';
  const svg = (tag, attrs) => { const n = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v); return n; };

  async function api(body) {
    const r = await fetch('/api/testlab/action', {
      method: 'POST', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-Atlas-Testlab': '1' }, body: JSON.stringify(body)
    });
    let j = {}; try { j = await r.json(); } catch (e) { /* not JSON */ }
    if (!r.ok) throw new Error(j.error || ('Request refused (' + r.status + ')'));
    return j;
  }

  // ---------- wheels ----------
  const wheelEls = [];
  function buildWheels() {
    const host = $('wheels');
    for (let i = 0; i < 4; i++) {
      const dial = svg('svg', { class: 'tl-dial', viewBox: '0 0 100 100', 'aria-hidden': 'true' });
      dial.append(svg('circle', { class: 'ring', cx: 50, cy: 50, r: 44 }));
      for (let t = 0; t < 12; t++) {
        const a = t * Math.PI / 6;
        dial.append(svg('line', { class: 'tick', x1: 50 + 38 * Math.sin(a), y1: 50 - 38 * Math.cos(a), x2: 50 + 44 * Math.sin(a), y2: 50 - 44 * Math.cos(a) }));
      }
      const arm = svg('line', { class: 'arm', x1: 50, y1: 50, x2: 50, y2: 10 });
      const tape = svg('circle', { class: 'tape', cx: 50, cy: 8, r: 5 });
      const g = svg('g'); g.append(arm, tape);
      dial.append(g, svg('circle', { class: 'hub', cx: 50, cy: 50, r: 5 }));
      const o = {
        btn: el('button', { type: 'button', class: 'tl-wheel', 'data-ch': i + 1, 'aria-pressed': 'false' }),
        g, name: el('span', { class: 'tl-wname' }), count: el('div', { class: 'tl-count', text: '–' }),
        dir: el('b', { class: 'tl-dir' }), rpm: el('b'), delta: el('b'), age: el('b'), dist: el('b'), badge: el('span', { class: 'tl-badge' }),
        sel: el('span', { class: 'tl-badge', text: 'selected' })
      };
      o.name.append(el('span', { text: NAMES[i].split(' ')[0] }), el('small', { text: NAMES[i].split(' ')[1] }), o.badge, o.sel);
      const meta = el('div', { class: 'tl-meta' },
        el('span', { text: 'Direction' }), o.dir, el('span', { text: 'Speed (est.)' }), o.rpm,
        el('span', { text: 'Change, 1 s' }), o.delta, el('span', { text: 'Last change' }), o.age, el('span', { text: 'Travelled' }), o.dist);
      o.btn.append(dial, el('div', {}, o.name, o.count, meta));
      o.btn.addEventListener('click', () => { selected = i + 1; store.set('atlasTestlabWheel', String(selected)); render(); });
      host.append(o.btn); wheelEls.push(o);
    }
  }

  function faultsFor(ch) { return (st && st.faults || []).filter(f => f.channel === ch); }

  function renderWheels() {
    const ch = st.view.channels || [];
    for (let i = 0; i < 4; i++) {
      const o = wheelEls[i], c = ch[i], fs = faultsFor(i + 1);
      o.btn.setAttribute('aria-pressed', String(selected === i + 1));
      o.sel.hidden = selected !== i + 1;
      const worst = fs.some(f => f.severity === 'fault') ? 'fail' : fs.length ? 'warn' : (c ? 'ok' : '');
      o.btn.classList.toggle('ofault', worst === 'fail');
      o.badge.className = 'tl-badge ' + worst;
      setText(o.badge, !c ? 'no data' : worst === 'fail' ? 'fault' : worst === 'warn' ? 'check' : 'ok');
      if (!c) continue;
      setText(o.count, String(c.raw_count));
      const turns = c.distance_m / C_M;
      o.g.setAttribute('transform', 'rotate(' + (((turns % 1) + 1) % 1 * 360).toFixed(1) + ' 50 50)');
      o.dir.className = 'tl-dir ' + c.direction;
      setText(o.dir, c.direction === 'still' ? 'still' : c.direction);
      setText(o.rpm, c.rpm_estimate == null ? '–' : fmt(c.rpm_estimate, 1) + ' rpm');
      setText(o.delta, (c.delta_1s > 0 ? '+' : '') + c.delta_1s + ' counts');
      setText(o.age, c.last_change_age_s == null ? '–' : fmt(c.last_change_age_s, 1) + ' s ago');
      setText(o.dist, fmt(turns, 2) + ' turns');
    }
  }

  // ---------- graph ----------
  function renderGraph() {
    const cv = $('graph'), dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const x = cv.getContext('2d');
    x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, h);
    const g = st.graph;
    x.font = '11px system-ui'; x.fillStyle = '#8DA3B8'; x.strokeStyle = 'rgba(128,190,236,.14)';
    const L = 46, R = 8, T = 8, B = 20;
    const series = unit === 'turns' ? g.turns : g.raw.map(a => a.map(v => v - (a[0] || 0)));
    if (!g.t.length) { x.fillText('Waiting for encoder data…', L + 10, h / 2); return; }
    let lo = Infinity, hi = -Infinity;
    for (const s of series) for (const v of s) { if (v < lo) lo = v; if (v > hi) hi = v; }
    const span = Math.max(hi - lo, unit === 'turns' ? 0.5 : 400); const mid = (hi + lo) / 2; lo = mid - span / 2 * 1.1; hi = mid + span / 2 * 1.1;
    const X = t => L + (t + 30) / 30 * (w - L - R), Y = v => T + (1 - (v - lo) / (hi - lo)) * (h - T - B);
    for (let k = 0; k <= 4; k++) {
      const v = lo + (hi - lo) * k / 4, y = Y(v);
      x.beginPath(); x.moveTo(L, y); x.lineTo(w - R, y); x.stroke();
      x.fillText(unit === 'turns' ? v.toFixed(2) : Math.round(v), 4, y + 4);
    }
    for (const t of [-30, -20, -10, 0]) { x.fillText(t === 0 ? 'now' : t + ' s', X(t) - 12, h - 5); }
    for (let i = 0; i < 4; i++) {
      x.beginPath(); x.setLineDash(DASH[i]); x.strokeStyle = COLORS[i]; x.globalAlpha = selected === i + 1 ? 1 : 0.55; x.lineWidth = selected === i + 1 ? 3 : 1.6;
      series[i].forEach((v, k) => { const px = X(g.t[k]), py = Y(v); k ? x.lineTo(px, py) : x.moveTo(px, py); });
      x.stroke();
    }
    x.setLineDash([]); x.globalAlpha = 1;
  }
  function buildLegend() {
    const lg = $('legend');
    NAMES.forEach((n, i) => { const s = el('span', {}); const sw = el('i'); sw.style.setProperty('--c', COLORS[i]); sw.style.borderTopStyle = i === 0 ? 'solid' : i === 1 ? 'dashed' : i === 2 ? 'dotted' : 'double'; s.append(sw, n); lg.append(s); });
  }

  // ---------- comparison ----------
  function renderCmp() {
    const host = $('cmp'); host.replaceChildren();
    for (const r of st.comparison.rows) {
      const c = COLORS[r.channel - 1];
      const row = el('div', { class: 'tl-cmp' }); row.style.setProperty('--c', c);
      row.append(el('span', { class: 'nm', text: 'M' + r.channel }));
      for (const [lab, v] of [['Forward', r.fwd_ratio], ['Reverse', r.rev_ratio]]) {
        const bar = el('div', { class: 'bar', role: 'img', 'aria-label': lab + ' ' + (v == null ? 'not enough motion yet' : v.toFixed(2)) });
        if (v != null) { const i = el('i'); i.style.width = Math.max(1, Math.min(150, v * 100) / 1.5) + '%'; if (v < 0.75) i.className = 'low'; bar.append(i, el('span', { text: lab + ' ' + v.toFixed(2) })); }
        else bar.append(el('span', { text: lab + ' – need motion' }));
        row.append(bar);
      }
      const t = r.verdict === 'ASYMMETRIC' ? 'Counts differ by direction (' + Math.round(r.asymmetry * 100) + '%)'
        : r.verdict === 'BALANCED' ? 'Balanced both ways' : r.verdict === 'ONE_DIRECTION_ONLY' ? 'Only one direction seen so far' : 'Needs about a quarter turn each way';
      row.append(el('span', { class: 'verdict ' + (r.verdict === 'ASYMMETRIC' ? 'bad' : r.verdict === 'BALANCED' ? 'good' : ''), text: t }));
      host.append(row);
    }
  }

  // ---------- faults, chips, banner ----------
  function renderFaults() {
    const ul = $('faults'); ul.replaceChildren();
    if (!st.faults.length) { ul.append(el('li', { class: 'none', text: 'No faults detected in the last few seconds. Frozen, wrong-direction and missing counts only show once the wheels are moving.' })); return; }
    for (const f of st.faults) ul.append(el('li', { class: f.severity }, el('b', { text: (FAULT_TEXT[f.code] || f.code) + (f.channel ? ' · M' + f.channel : '') }), el('span', { text: f.detail })));
  }
  function chip(id, cls, text) { const n = $(id); n.className = 'chip ' + cls; setText(n, text); }
  function renderChips() {
    const stale = st.faults.some(f => f.code === 'STALE_DATA' || f.code === 'NO_DATA');
    const v = st.view;
    chip('chipData', stale ? 'fail' : 'ok', stale ? 'Encoder data stale' : 'Encoders live' + (v.frame_rate_hz ? ' · ' + v.frame_rate_hz + ' Hz' : ''));
    const g = st.gate;
    chip('chipOwner', st.run && !st.run.done ? 'warn' : g.entry_ok ? 'ok' : 'warn', st.run && !st.run.done ? 'Pulse run active' : g.entry_ok ? 'Pulse ready' : 'Pulse locked');
    chip('chipRec', st.session ? 'info' : '', st.session ? 'Recording · ' + st.session.rows + ' rows' : 'Not recording');
  }
  function renderBanner() {
    const b = $('banner'); let m = null, cls = '';
    if (Date.now() - lastOk > 2500) { m = ['Lost the link to the rover.', 'Controls are disabled. If a pulse was running, the base driver has already timed out to zero.']; cls = 'fail'; }
    else if (st.faults.some(f => f.code === 'NO_DATA' || f.code === 'STALE_DATA')) { m = ['Encoder data is not arriving.', 'Nothing on this page can be trusted until it is. Check that the base driver is running.']; cls = 'fail'; }
    b.hidden = !m; b.className = 'tl-banner ' + cls;
    if (m) { b.replaceChildren(el('b', { text: m[0] }), document.createTextNode(m[1])); }
  }

  // ---------- hand test ----------
  function renderHand() {
    const h = st.hand, open = h.open;
    setText($('handWheel'), NAMES[selected - 1]);
    const live = !st.faults.some(f => f.code === 'STALE_DATA' || f.code === 'NO_DATA');
    $('handStart').disabled = !!open || !live || busy || (st.run && !st.run.done);
    $('handFinish').disabled = !open || busy;
    for (const b of document.querySelectorAll('[data-hdir]')) { b.classList.toggle('on', b.dataset.hdir === hdir); b.disabled = !!open; }
    const bar = $('handBar');
    if (open) {
      const ch = st.view.channels, i = open.wheel - 1, sign = open.direction === 'forward' ? 1 : -1;
      const own = sign * (ch[i].distance_m - open.start_dist_m[i]) / C_M;
      let other = 0; ch.forEach((c, j) => { if (j !== i) other = Math.max(other, Math.abs(c.distance_m - open.start_dist_m[j]) / C_M); });
      bar.style.width = Math.max(0, Math.min(100, own / 1.4 * 100)) + '%';
      setText($('handText'), NAMES[i] + ' ' + open.direction + ': ' + fmt(own, 2) + ' of one turn counted (target 0.75 to 1.30). Other wheels moved ' + fmt(other, 2) + '.');
    } else { bar.style.width = '0%'; setText($('handText'), 'Select a wheel above, choose a direction, then press Start turn.'); }
    const host = $('handResults'); host.replaceChildren();
    for (const r of h.results.slice().reverse()) {
      host.append(el('div', { class: 'r ' + (r.status === 'PASS' ? 'PASS' : 'bad') }, el('span', { text: NAMES[r.wheel - 1].split(' ')[0] + ' ' + r.direction }),
        el('span', { text: fmt(r.ratio, 2) + ' turn · ' + r.status.replace('_', ' ').toLowerCase() + (r.crosstalk_warn ? ' · other wheel moved' : '') })));
    }
    for (const [w, s] of Object.entries(h.summary)) {
      if (s.verdict === 'NOT_TESTED') continue;
      host.prepend(el('div', { class: 'r ' + (s.verdict === 'PASS' ? 'PASS' : 'bad') }, el('b', { text: 'M' + w + ' overall: ' + s.verdict.toLowerCase() }), el('span', { text: s.notes.join('; ') })));
    }
  }

  // ---------- pulse ----------
  function renderPulse() {
    const g = st.gate, run = st.run, active = run && !run.done;
    const ul = $('gates'); ul.replaceChildren();
    for (const x of g.gates) { const li = el('li', { class: x.ok ? 'ok' : '' }, el('span', {}, x.label, !x.ok && x.detail ? el('small', { text: x.detail }) : null)); ul.append(li); }
    const live = !st.faults.some(f => f.code === 'STALE_DATA' || f.code === 'NO_DATA') && Date.now() - lastOk < 2500;
    const phraseOk = $('phrase').value === st.limits.confirmation_phrase;
    const checked = [...document.querySelectorAll('[data-ck]')].every(c => c.checked);
    const open = g.entry_ok && !active && live;
    $('pulseSet').disabled = !open;
    const ready = open && phraseOk && checked && !busy;
    $('goFwd').disabled = !ready; $('goRev').disabled = !ready;
    $('stopBtn').disabled = false;
    const tag = $('pulseTag');
    tag.className = 'tl-tag ' + (active ? 'warn' : open ? 'ok' : 'warn'); setText(tag, active ? 'running' : open ? 'gates open' : 'locked');
    let why = '';
    if (!active && !open) {
      if (!g.state && g.gates[0] && !g.gates[0].ok) why = 'Safety state unknown, so the pulse controls stay locked. Ask the owner to check the base driver.';
      else { const f = g.gates.find(x => !x.ok); why = 'Locked: ' + (f ? f.label + (f.detail ? ' — ' + f.detail : '') : 'waiting for the owner') + (!live ? ' Encoder data is not live.' : ''); }
    }
    setText($('lockWhy'), why);
    setText($('pwmOut'), $('pwm').value); setText($('durOut'), Number($('dur').value).toFixed(2));
    const r = $('run');
    if (run) {
      const msg = run.guidance + (run.error ? ' (' + run.error.replace(/_/g, ' ') + ')' : '') + (run.session_fingerprint ? ' Session ' + run.session_fingerprint + '.' : '');
      r.className = 'tl-run on' + (run.needs_operator ? ' need' : run.error ? ' bad' : ''); setText(r, msg);
    } else { r.className = 'tl-run'; setText(r, ''); }
    $('phrase').disabled = false;
    const host = $('pulseResults'); host.replaceChildren();
    for (const p of st.pulse_results.slice().reverse()) {
      host.append(el('div', { class: 'r ' + (p.result === 'MATCH' ? 'MATCH' : 'bad') }, el('span', { text: 'M' + p.wheel + ' ' + p.direction + ' pwm ' + Math.abs(p.pwm) + ' · ' + p.duration_s + ' s' }),
        el('span', { text: p.delta_count + ' counts · ' + p.result.toLowerCase().replace('_', ' ') })));
    }
    if (st.pulse_results.length) host.append(el('div', { class: 'tl-note', text: 'These are the base driver\'s observations. They are evidence, not a physical pass.' }));
  }

  // ---------- recording ----------
  function renderRec() {
    const s = st.session, last = st.last_session;
    $('recStart').disabled = !!s || busy; $('recStop').disabled = !s || busy;
    setText($('recInfo'), s ? s.mode + ' session ' + s.id + ' · ' + s.rows + ' rows' + (s.truncated ? ' · size limit reached' : '') : last ? 'Last session ' + last.id + ' saved (' + last.rows + ' rows).' : 'No session open.');
    const a = $('csvCurrent'); const cur = s || last;
    a.hidden = !cur; if (cur) a.href = '/api/testlab/session.csv?id=' + cur.id;
    const ul = $('files'); ul.replaceChildren();
    if (!st.saved_files.length) ul.append(el('li', { class: 'tl-note', text: 'Nothing saved yet.' }));
    for (const f of st.saved_files.slice().reverse()) { const id = f.replace(/\.csv$/, '').split('_').pop(); const a2 = el('a', { href: '/api/testlab/session.csv?id=' + id, text: f }); ul.append(el('li', {}, a2)); }
  }

  function render() {
    if (!st) return;
    renderChips(); renderBanner(); renderWheels(); renderGraph(); renderCmp(); renderFaults(); renderHand(); renderPulse(); renderRec();
  }

  // ---------- polling ----------
  async function poll() {
    try {
      const r = await fetch('/api/testlab/state', { cache: 'no-store' });
      if (!r.ok) throw new Error(String(r.status));
      st = await r.json(); lastOk = Date.now(); render();
    } catch (e) {
      if (st) { renderBanner(); renderPulse(); } else { const b = $('banner'); b.hidden = false; b.className = 'tl-banner fail'; b.textContent = 'Cannot reach the Test Lab service on the rover.'; }
    }
    setTimeout(poll, document.hidden ? 2000 : 250);
  }

  // ---------- actions ----------
  async function run(body, ok) {
    if (busy) return; busy = true;
    try { const j = await api(body); if (ok) ok(j); } catch (e) { const r = $('run'); r.className = 'tl-run on bad'; setText(r, e.message); }
    finally { busy = false; }
  }
  async function pulse(direction) {
    const checklist = {}; for (const c of document.querySelectorAll('[data-ck]')) checklist[c.dataset.ck] = c.checked;
    await run({ action: 'pulse_start', wheel: selected, direction, pwm: Number($('pwm').value), duration_s: Number(Number($('dur').value).toFixed(2)),
      confirm: $('phrase').value, checklist }, () => { $('phrase').value = ''; for (const c of document.querySelectorAll('[data-ck]')) c.checked = false; });
  }
  async function stopAll() {
    // Abort any running pulse AND send the dashboard's normal E-STOP request. Both are zero-ing actions only.
    const a = fetch('/api/testlab/action', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Testlab': '1' }, body: JSON.stringify({ action: 'pulse_cancel' }) }).catch(() => null);
    const b = fetch('/', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ action: 'e_stop' }) }).catch(() => null);
    const r = $('run'); r.className = 'tl-run on need'; setText(r, 'Stop sent. Output is being zeroed.');
    await Promise.all([a, b]);
  }

  function wire() {
    for (const b of document.querySelectorAll('[data-unit]')) b.addEventListener('click', () => { unit = b.dataset.unit; for (const x of document.querySelectorAll('[data-unit]')) x.classList.toggle('on', x === b); if (st) renderGraph(); });
    for (const b of document.querySelectorAll('[data-hdir]')) b.addEventListener('click', () => { hdir = b.dataset.hdir; if (st) renderHand(); });
    $('handStart').addEventListener('click', () => run({ action: 'hand_begin', wheel: selected, direction: hdir }));
    $('handFinish').addEventListener('click', () => run({ action: 'hand_finish' }));
    $('handReset').addEventListener('click', () => run({ action: 'hand_reset' }));
    $('recStart').addEventListener('click', () => run({ action: 'session_start', mode: 'observe' }));
    $('recStop').addEventListener('click', () => run({ action: 'session_stop' }));
    $('goFwd').addEventListener('click', () => pulse('forward'));
    $('goRev').addEventListener('click', () => pulse('reverse'));
    // STOP acts on pointerdown like the dock E-STOP, so a second-finger tap still works.
    let at = 0; const sb = $('stopBtn');
    sb.addEventListener('pointerdown', e => { e.preventDefault(); at = Date.now(); stopAll(); });
    sb.addEventListener('click', e => { if (e.detail === 0 && Date.now() - at > 1000) stopAll(); });
    for (const id of ['pwm', 'dur', 'phrase']) $(id).addEventListener('input', () => { if (st) renderPulse(); });
    for (const c of document.querySelectorAll('[data-ck]')) c.addEventListener('change', () => { if (st) renderPulse(); });
    const lab = document.querySelector('label[for=phrase]');
    fetch('/api/testlab/state?history=0', { cache: 'no-store' }).then(r => r.json()).then(j => { if (lab) lab.textContent = 'Type the confirmation phrase: ' + j.limits.confirmation_phrase; }).catch(() => null);
  }

  buildWheels(); buildLegend(); wire(); poll();
})();
