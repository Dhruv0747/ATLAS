/* 2026-11-26 ATLAS add-only map extension preview (docs/design/guided_mapping_assistant.md section 10). READ ONLY.
   Shows the extend job's latest result: the preview image (gray = saved map, unchanged; green = new area; red = new
   walls in saved free space), the numbers and the checks. It never changes the map: adding the area to the saved map
   is a separate, owner-approved step (parked, E-STOP latched, backup first). */
(function () {
  const side = document.querySelector('aside.side');
  if (!side) return;
  const card = document.createElement('section');
  card.className = 'card mx';
  card.hidden = true;
  card.innerHTML = `<h2>MAP EXTENSION PREVIEW</h2><div class="mxVerdict" id="mxVerdict"></div>
   <img id="mxImg" alt="Extension preview: gray saved map, green new area, red disagreement" style="width:100%;border-radius:8px;border:1px solid #315b74;margin:6px 0;image-rendering:pixelated" hidden>
   <div id="mxRows"></div><div id="mxNext" class="note"></div>`;
  side.insertBefore(card, side.children[1] || null);
  const st = document.createElement('style');
  st.textContent = `.mx .mxVerdict{font-weight:800;margin-bottom:4px}.mx .mxVerdict.ok{color:#34e58b}.mx .mxVerdict.bad{color:#ff5261}
  .mx ul{margin:6px 0;padding-left:18px;color:#ffbdc4}`;
  document.head.appendChild(st);
  const $ = id => document.getElementById(id);
  function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  const fmt = (v, d) => (v === null || v === undefined || !isFinite(Number(v))) ? '—' : Number(v).toFixed(d);
  const row = (a, b) => `<div class="row"><span>${esc(a)}</span><b>${esc(b)}</b></div>`;
  let lastKey = '';
  function render(x) {
    if (!x) { card.hidden = true; lastKey = ''; return; }
    const key = JSON.stringify([x.session_id, x.ok, x.created_unix]);
    card.hidden = false;
    const ageMin = Math.round((Number(x.age_s) || 0) / 60);
    if (key === lastKey) return;
    lastKey = key;
    const s = x.stats || {}, id8 = String(x.session_id || '').slice(0, 8);
    const v = $('mxVerdict');
    v.className = 'mxVerdict ' + (x.ok ? 'ok' : 'bad');
    v.textContent = x.ok
      ? `Ready to add ${fmt(s.added_free_m2, 1)} m² of new area — saved map unchanged (${s.saved_cells_changed || 0} cells changed)`
      : 'Not added — the saved map is unchanged';
    const img = $('mxImg');
    img.hidden = !x.has_preview;
    if (x.has_preview) img.src = `/map_extend_preview.png?t=${encodeURIComponent(x.created_unix)}`;
    $('mxRows').innerHTML = row('Session', id8) + row('Match with saved walls', `${fmt((x.match || 0) * 100, 0)} %`)
      + row('New walls in saved free space', `${fmt((s.conflict_fraction || 0) * 100, 1)} %`)
      + row('New area not reachable', `${fmt(s.unreachable_m2, 2)} m²`)
      + row('Result age', `${ageMin} min`)
      + ((x.failures || []).length ? `<ul>${x.failures.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : '');
    $('mxNext').textContent = x.ok
      ? `To add it to the saved map, ask Claude to "promote extension ${id8}". That is done parked with the E-STOP latched, after a backup; the map acceptance checks run again first.`
      : 'Nothing was changed. Drive the extension again from a LiDAR-verified spot, slowly, through the doorway into the new area.';
  }
  async function poll() {
    if (document.hidden) return;
    try {
      const r = await fetch('/api/map_extend', { cache: 'no-store', signal: AbortSignal.timeout(3000) });
      if (r.ok) render((await r.json()).extend);
    } catch (e) { /* keep the last card */ }
  }
  poll();
  setInterval(poll, 20000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
})();
