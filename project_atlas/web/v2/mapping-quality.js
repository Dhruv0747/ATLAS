/* 2026-11-26 ATLAS guided mapping assistant (phase 1b; docs/design/guided_mapping_assistant.md). READ ONLY.
   Draws the per-area map quality, unexplored openings and objects the LiDAR cannot see over the live mapping map, and
   shows the assistant's prompts in a side card. It makes no request of its own: it reads state.mapping_quality from
   the /api/map poll this page already runs. Advice only: the map acceptance check still decides accept or reject.
   Shown only during a mapping session (q.state !== 'inactive').
   2026-11-26 outside mapping sessions the same card is the SAVED MAP CHECK (q.state === 'map_check'): orange boxes
   where the LiDAR keeps seeing something the saved map does not have (owner: "where can I see the map needs updating"). */
(function () {
  const side = document.querySelector('aside.side'), cv = document.getElementById('mapCanvas');
  if (!side || !cv) return;
  const card = document.createElement('section');
  card.className = 'card mq';
  card.hidden = true;
  card.innerHTML = `<h2 id="mqTitle">MAPPING ASSISTANT</h2><div class="mqVerdict" id="mqVerdict"></div>
   <div id="mqPrompts"></div><div id="mqCounts" class="mqSmall"></div><div id="mqObjects"></div><div id="mqNotes" class="mqSmall"></div>
   <div class="note" id="mqNote"></div>`;
  const NOTE_MAPPING = 'Green = area mapped well. Amber = weak: drive slowly through it again. Cyan = unexplored opening. ' +
    'Magenta = object the LiDAR cannot see (depth camera / ultrasonic). Advice only: the map acceptance check decides. ' +
    'Objects are added to the map only after you confirm them.';
  const NOTE_CHECK = 'Orange = the LiDAR keeps seeing something the saved map does not have (furniture moved or added). ' +
    'Checked only while ATLAS is sure where it is. To fix it: run a new mapping session, or ask to add it as a fixed object. ' +
    'Advice only: nothing is changed automatically.';
  side.insertBefore(card, side.firstChild);
  const st = document.createElement('style');
  st.textContent = `.mq .mqVerdict{font-weight:800;margin-bottom:6px}.mq .mqVerdict.ok{color:#34e58b}.mq .mqVerdict.warn{color:#ffcc3d}
  .mq .mqVerdict.bad{color:#ff5261}.mq .mqPrompt{padding:8px;border-radius:8px;background:#2a2108;border:1px solid #ffcc3d;
  color:#ffe9a8;font-weight:700;margin:6px 0}.mq .mqSmall{font-size:12px;color:#90abc0;margin:6px 0}
  .mq .mqObj{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-bottom:1px solid #173047}`;
  document.head.appendChild(st);
  const $ = id => document.getElementById(id);
  function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function quality() { return (typeof state !== 'undefined' && state && state.mapping_quality) || null; }
  function decodeRows(rows) {
    const out = [];
    (rows || []).forEach(r => { const iy = r[0], x0 = r[1], s = String(r[2] || '');
      for (let k = 0; k < s.length; k++) if (s[k] !== '.') out.push([x0 + k, iy, s[k]]); });
    return out;
  }
  let lastKey = '';
  function renderCard(q) {
    if (!q || q.state === 'inactive') { card.hidden = true; lastKey = ''; return; }
    const check = !q.session_id;                  // mapping-session payloads always carry their session id
    const key = JSON.stringify([q.state, q.verdict_text, q.prompts, q.notes, q.counts, q.objects, q.map_changes, q.samples]);
    card.hidden = false;
    if (key === lastKey) return;
    lastKey = key;
    $('mqTitle').textContent = check ? 'SAVED MAP CHECK' : 'MAPPING ASSISTANT';
    $('mqNote').textContent = check ? NOTE_CHECK : NOTE_MAPPING;
    const v = $('mqVerdict');
    v.textContent = q.verdict_text || '';
    const clean = q.state === 'map_check' && !(q.map_changes || []).length && (q.counts || {}).frames_used > 0;
    v.className = 'mqVerdict ' + (q.ready || clean ? 'ok' : (q.state === 'active' || q.state === 'map_check') ? 'warn' : 'bad');
    $('mqPrompts').innerHTML = (q.prompts || []).map(p => `<div class="mqPrompt">${esc(p)}</div>`).join('');
    const c = q.counts || {};
    $('mqCounts').textContent = q.state === 'active'
      ? `Areas: ${c.ACCEPTED || 0} good, ${c.WEAK || 0} weak · openings ${(q.frontiers || []).length} · scans used ${q.samples || 0}`
      : check ? `Positions checked: ${c.positions || 0} · scans used ${c.frames_used || 0} · skipped (position unsure): ${c.frames_skipped_fit || 0}` : '';
    $('mqObjects').innerHTML = (q.map_changes || []).map(o => `<div class="mqObj"><b style="color:#ff9d3d">${esc(o.name)}</b><small>${esc(o.area_m2)} m²</small></div>`).join('') + (q.objects || []).map(o => `<div class="mqObj"><b>${esc(o.name)}</b><small>${esc((o.sources || []).join(' + '))} · ${esc(o.area_m2)} m²</small></div>`).join('');
    $('mqNotes').innerHTML = (q.notes || []).map(n => `<div>${esc(n)}</div>`).join('');
  }
  function drawOverlay(q, meta) {
    const t = transform(meta), d = Math.max(1, window.devicePixelRatio || 1), tm = Number(q.tile_m) || 0.5;
    ctx.save();
    decodeRows(q.rows).forEach(([ix, iy, code]) => {
      const a = worldPixel(ix * tm, (iy + 1) * tm, meta, t), b = worldPixel((ix + 1) * tm, iy * tm, meta, t);
      ctx.fillStyle = code === 'A' ? 'rgba(52,229,139,0.22)' : 'rgba(255,204,61,0.34)';
      ctx.fillRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
    });
    ctx.strokeStyle = '#17d5ff'; ctx.lineWidth = 2 * d;
    (q.frontiers || []).forEach(f => { const p = worldPixel(f.x, f.y, meta, t);
      ctx.beginPath(); ctx.arc(p[0], p[1], 9 * d, 0, Math.PI * 2); ctx.stroke(); });
    ctx.strokeStyle = '#ff4fd8'; ctx.lineWidth = 3 * d; ctx.fillStyle = '#ff4fd8';
    ctx.font = `bold ${Math.max(11, 12 * d)}px system-ui`;
    (q.objects || []).forEach(o => { const poly = o.polygon || []; if (poly.length < 3) return;
      ctx.beginPath(); poly.forEach((v, i) => { const p = worldPixel(v[0], v[1], meta, t); i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); });
      ctx.closePath(); ctx.stroke();
      const p = worldPixel(poly[0][0], poly[0][1], meta, t); ctx.fillText(String(o.name || ''), p[0] + 4 * d, p[1] - 4 * d); });
    ctx.restore();
  }
  function drawChanges(q, meta) {
    const t = transform(meta), d = Math.max(1, window.devicePixelRatio || 1);
    ctx.save(); ctx.strokeStyle = '#ff9d3d'; ctx.fillStyle = 'rgba(255,157,61,0.25)'; ctx.lineWidth = 3 * d;
    ctx.font = `bold ${Math.max(11, 12 * d)}px system-ui`;
    (q.map_changes || []).forEach(o => { const poly = o.polygon || []; if (poly.length < 3) return;
      ctx.beginPath(); poly.forEach((v, i) => { const p = worldPixel(v[0], v[1], meta, t); i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); });
      ctx.closePath(); ctx.fill(); ctx.stroke();
      const p = worldPixel(poly[0][0], poly[0][1], meta, t); ctx.fillStyle = '#ff9d3d';
      ctx.fillText(String(o.name || ''), p[0] + 4 * d, p[1] - 4 * d); ctx.fillStyle = 'rgba(255,157,61,0.25)'; });
    ctx.restore();
  }
  const baseDraw = window.draw;
  if (typeof baseDraw === 'function') {
    window.draw = function () {
      baseDraw.apply(this, arguments);
      const q = quality();
      renderCard(q);
      const meta = (typeof state !== 'undefined' && state && state.map && state.map.width) ? state.map : null;
      if (!q || !meta) return;
      try {
        if (q.state === 'map_check') drawChanges(q, meta);
        if (q.state !== 'active') return;
        drawOverlay(q, meta);
      } catch (e) { /* never break the base map */ }
    };
  }
  if (typeof module !== 'undefined') module.exports = { decodeRows };
})();
