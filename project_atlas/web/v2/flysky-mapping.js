/* ATLAS FlySky Test Lab: channel-to-control mapping (client only, READ ONLY).
 * Labels which transmitter control (stick axis, switch, knob, key) drives each of CH1-CH10 and checks it against
 * the live receiver data the page already polls. It makes NO network request: it listens for the
 * 'atlas-flysky-state' event that flysky-testlab.js dispatches after each GET of /api/flysky/state.
 * The mapping is saved in this browser (localStorage) and can be exported/imported as a JSON file.
 * It is a display label only: nothing here is connected to any drive or command path. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const KEY = 'atlasFlyskyMapping.v1';
  const NCH = 10;                       // usable transmitter channels shown by default
  const SPAN = 60;                      // SBUS counts of travel before a control counts as moved (same as the server)
  const NOW_S = 1.5;
  const CONTROLS = [
    { id: 'rh', name: 'Right stick left–right', group: 'Sticks', kind: 'stick', pad: 'rx' },
    { id: 'rv', name: 'Right stick up–down', group: 'Sticks', kind: 'stick', pad: 'ry' },
    { id: 'lv', name: 'Left stick up–down', group: 'Sticks', kind: 'stick', pad: 'ly' },
    { id: 'lh', name: 'Left stick left–right', group: 'Sticks', kind: 'stick', pad: 'lx' },
    { id: 'swa', name: 'Switch SwA', group: 'Switches', kind: 'switch' },
    { id: 'swb', name: 'Switch SwB', group: 'Switches', kind: 'switch' },
    { id: 'swc', name: 'Switch SwC', group: 'Switches', kind: 'switch' },
    { id: 'swd', name: 'Switch SwD', group: 'Switches', kind: 'switch' },
    { id: 'vra', name: 'Knob VrA', group: 'Knobs and keys', kind: 'knob' },
    { id: 'vrb', name: 'Knob VrB', group: 'Knobs and keys', kind: 'knob' },
    { id: 'key1', name: 'Back key 1', group: 'Knobs and keys', kind: 'key' },
    { id: 'key2', name: 'Back key 2', group: 'Knobs and keys', kind: 'key' }
  ];
  const BY_ID = Object.fromEntries(CONTROLS.map(c => [c.id, c]));
  // FS-i6S mode 2 stick order, then the layout this project uses for CH5-CH10.
  const DEFAULTS = { 1: 'rh', 2: 'rv', 3: 'lv', 4: 'lh', 5: 'swa', 6: 'swb', 7: 'swc', 8: 'swd', 9: 'vra', 10: 'vrb' };

  // ---------- pure model (exported for tests) ----------
  function clean(map) {
    const out = {};
    if (!map || typeof map !== 'object') return out;
    for (let ch = 1; ch <= NCH; ch++) { const v = map[ch] ?? map[String(ch)]; if (typeof v === 'string' && BY_ID[v]) out[ch] = v; }
    return out;
  }
  function problems(map) {
    const seen = {}, errs = [];
    for (const [ch, id] of Object.entries(map)) {
      if (seen[id]) errs.push(BY_ID[id].name + ' is selected for both CH' + seen[id] + ' and CH' + ch + '.');
      else seen[id] = ch;
    }
    return errs;
  }
  function kindOk(ctrl, c) {
    if (!ctrl || !c || !c.moved) return true;
    if (ctrl.kind === 'stick') return c.kind === 'analog';
    if (ctrl.kind === 'switch') return c.kind === 'switch';
    return true;                                          // knobs and keys may read as analog or as a few levels
  }
  function status(ctrlId, c, seen) {
    const ctrl = ctrlId ? BY_ID[ctrlId] : null, span = seen ? seen.hi - seen.lo : 0;
    const now = !!(c && c.changed_ago_s != null && c.changed_ago_s < NOW_S && span >= SPAN);
    if (!c) return { code: 'nodata', text: 'No data', now: false };
    if (!ctrl) return span >= SPAN ? { code: 'stray', text: 'Unassigned, but it changed', now } : { code: 'unassigned', text: 'Unassigned', now: false };
    if (span < SPAN) return { code: 'waiting', text: 'Assigned · move it to check', now: false };
    if (!kindOk(ctrl, c)) return { code: 'check', text: 'Changed, but it reads as ' + c.kind, now };
    return { code: 'verified', text: 'Verified', now };
  }
  function summary(map, chans, seenBy) {
    let assigned = 0, verified = 0, changing = 0;
    for (let ch = 1; ch <= NCH; ch++) {
      const s = status(map[ch], chans[ch], seenBy[ch]);
      if (map[ch]) assigned++;
      if (s.code === 'verified') verified++;
      if (s.now) changing++;
    }
    return { assigned, unassigned: NCH - assigned, verified, changing };
  }

  // ---------- storage ----------
  const store = {
    get() { try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; } },
    set(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); return true; } catch (e) { return false; } }
  };
  const saved0 = store.get();
  let applied = saved0 ? clean(saved0.channels) : {};
  let savedAt = saved0 && saved0.saved_utc || null;
  let draft = Object.assign({}, applied);
  let st = null, seenBy = {}, checkFrom = null;

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v); }
    for (const kid of kids) if (kid != null) n.append(kid);
    return n;
  }
  const setText = (n, t) => { if (n && n.textContent !== t) n.textContent = t; };
  const same = (a, b) => JSON.stringify(clean(a)) === JSON.stringify(clean(b));

  // ---------- UI ----------
  const rows = {};
  function build() {
    const host = $('mapRows'); if (!host) return false;
    for (let ch = 1; ch <= NCH; ch++) {
      const sel = el('select', { 'aria-label': 'Control for channel ' + ch, id: 'mapSel' + ch });
      sel.append(el('option', { value: '', text: 'Unassigned' }));
      let grp = null, g = '';
      for (const c of CONTROLS) { if (c.group !== g) { g = c.group; grp = el('optgroup', { label: g }); sel.append(grp); } grp.append(el('option', { value: c.id, text: c.name })); }
      sel.addEventListener('change', () => { if (sel.value) draft[ch] = sel.value; else delete draft[ch]; renderForm(); });
      const o = { row: el('div', { class: 'fm-row' }), sel, raw: el('span', { class: 'fm-raw' }), seen: el('span', { class: 'fm-seen' }), badge: el('span', { class: 'fm-badge' }) };
      o.row.append(el('b', { class: 'fm-ch', text: 'CH' + ch }), sel, o.raw, o.seen, o.badge);
      host.append(o.row); rows[ch] = o;
    }
    $('mapApply').addEventListener('click', apply);
    $('mapCancel').addEventListener('click', () => { draft = Object.assign({}, applied); renderForm(); note('Changes discarded.'); });
    $('mapDefaults').addEventListener('click', () => { draft = Object.assign({}, DEFAULTS); renderForm(); note('Defaults loaded. Select Apply to keep them.'); });
    $('mapCheck').addEventListener('click', restartCheck);
    $('mapExport').addEventListener('click', exportFile);
    $('mapImport').addEventListener('change', importFile);
    const raw = $('rawToggle');
    if (raw) raw.addEventListener('change', () => { $('chans').classList.toggle('fs-raw16', raw.checked); });
    document.addEventListener('atlas-flysky-state', e => { st = e.detail; track(); render(); });
    renderForm();
    return true;
  }
  function note(t) { setText($('mapNote'), t); }
  function apply() {
    const errs = problems(draft); if (errs.length) { note(errs[0]); return; }
    applied = Object.assign({}, draft); savedAt = new Date().toISOString();
    const ok = store.set({ version: 1, saved_utc: savedAt, channels: applied });
    syncStickPads();
    renderForm(); render();
    note(ok ? 'Mapping saved in this browser.' : 'Applied for this visit only: this browser does not allow saving.');
  }
  function syncStickPads() {
    // Point the existing stick pads at the mapped channels by driving their own selects (their handlers save it).
    const pads = { lx: 'Left stick Left–right channel', ly: 'Left stick Up–down channel', rx: 'Right stick Left–right channel', ry: 'Right stick Up–down channel' };
    for (const [pad, label] of Object.entries(pads)) {
      const s = document.querySelector('select[aria-label="' + label + '"]'); if (!s) continue;
      const ch = Object.keys(applied).find(k => BY_ID[applied[k]].pad === pad);
      const v = ch ? String(ch) : '0';
      if (s.value !== v) { s.value = v; s.dispatchEvent(new Event('change')); }
    }
  }
  function restartCheck() { seenBy = {}; checkFrom = Date.now(); track(); render(); note('Check restarted: move each control once.'); }
  function track() {
    if (!st || !st.link || !(st.link.state === 'LIVE')) return;   // only live frames count as a control movement
    for (const c of st.channels || []) {
      if (c.channel > NCH || c.raw == null) continue;
      const s = seenBy[c.channel] || (seenBy[c.channel] = { lo: c.raw, hi: c.raw });
      s.lo = Math.min(s.lo, c.raw); s.hi = Math.max(s.hi, c.raw);
    }
  }
  function chansBy() { const by = {}; for (const c of (st && st.channels) || []) by[c.channel] = c; return by; }
  function renderForm() {
    for (let ch = 1; ch <= NCH; ch++) { const v = draft[ch] || ''; if (rows[ch].sel.value !== v) rows[ch].sel.value = v; }
    const dirty = !same(draft, applied), errs = problems(draft);
    $('mapApply').disabled = !dirty || errs.length > 0; $('mapCancel').disabled = !dirty;
    const dup = new Set(); for (const e of errs) for (const m of e.match(/CH\d+/g) || []) dup.add(m);
    for (let ch = 1; ch <= NCH; ch++) rows[ch].row.classList.toggle('dup', dup.has('CH' + ch));
    setText($('mapState'), errs.length ? errs[0] : dirty ? 'Unsaved changes' : savedAt ? 'Saved ' + new Date(savedAt).toLocaleString() : 'Not saved yet');
    $('mapState').className = 'fm-state' + (errs.length ? ' bad' : dirty ? ' warn' : '');
  }
  function render() {
    const by = chansBy(), live = !!(st && st.link && st.link.state === 'LIVE');
    for (let ch = 1; ch <= NCH; ch++) {
      const o = rows[ch], c = by[ch], s = status(applied[ch], c, seenBy[ch]);
      setText(o.raw, c && c.raw != null ? String(c.raw) : '–');
      const sn = seenBy[ch]; setText(o.seen, sn ? sn.lo + ' – ' + sn.hi : '–');
      setText(o.badge, s.text + (s.now ? ' · changing now' : ''));
      o.badge.className = 'fm-badge ' + s.code + (s.now ? ' now' : '');
      o.row.classList.toggle('now', s.now); o.row.classList.toggle('old', !live);
    }
    const m = summary(applied, by, seenBy);
    setText($('mapSummary'), m.assigned + ' of ' + NCH + ' assigned · ' + m.verified + ' verified · ' + m.changing + ' changing now' + (live ? '' : ' · receiver not live'));
  }
  function exportFile() {
    const blob = new Blob([JSON.stringify({ version: 1, saved_utc: savedAt, channels: applied }, null, 2)], { type: 'application/json' });
    const a = el('a', { href: URL.createObjectURL(blob), download: 'atlas_flysky_mapping.json' });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  function importFile(e) {
    const f = e.target.files && e.target.files[0]; e.target.value = '';
    if (!f || f.size > 4096) { note('Choose a mapping file under 4 KB.'); return; }
    f.text().then(t => {
      const j = JSON.parse(t), m = clean(j && j.channels), errs = problems(m);
      if (errs.length) { note('Not imported: ' + errs[0]); return; }
      draft = m; renderForm(); note('File loaded. Select Apply to keep it.');
    }).catch(() => note('Not imported: the file is not a mapping file.'));
  }

  window.AtlasFlyskyMap = { CONTROLS, DEFAULTS, NCH, clean, problems, status, summary, maxVisible: () => ($('chans') && $('chans').classList.contains('fs-raw16')) ? 16 : NCH };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build); else build();
})();
