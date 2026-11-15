/* 2026-11-15 ATLAS navigation page: tap the map to add a waypoint, then Go. Only asks the server:
   mission control refuses unknown/occupied/too-tight spots (0.35 m clearance on the accepted map), and Go is refused
   unless AUTONOMY is ON and the E-STOP is released. Disabled while mapping (live SLAM map = different frame). */
(function () {
  const side = document.querySelector('aside.side'), cv = document.getElementById('mapCanvas');
  if (!side || !cv) return;
  const card = document.createElement('section');
  card.className = 'card mwp';
  card.innerHTML = `<h2>WAYPOINTS — TAP THE MAP</h2>
   <div class="mwpState" id="mwpState">Autonomy state …</div>
   <div class="mwpTap" id="mwpTap" hidden>
    <div id="mwpXY"></div>
    <input id="mwpName" maxlength="24" placeholder="Name (e.g. kitchen)" aria-label="Waypoint name">
    <div class="mwpBtns"><button id="mwpSave" type="button">Save waypoint</button><button id="mwpCancel" type="button">Cancel</button></div>
   </div>
   <div id="mwpList"></div>
   <div class="note">Tap a free spot on the map. ATLAS refuses spots that are unknown, occupied or closer than 0.35 m to a wall.
   Go needs AUTONOMY ON (Command center, PIN) and the E-STOP released; B on the remote always stops.</div>`;
  side.insertBefore(card, side.children[2] || null);
  const st = document.createElement('style');
  st.textContent = `.mwp input{width:100%;min-height:42px;margin:8px 0;padding:8px 10px;border-radius:8px;border:1px solid #315b74;background:#07131f;color:#edf8ff;font:inherit}
  .mwp button{min-height:42px;padding:6px 12px;border-radius:8px;border:1px solid #2d6a8c;background:#0a3047;color:#fff;font:inherit;font-weight:700;cursor:pointer}
  .mwp button:disabled{opacity:.45;cursor:default}.mwpBtns{display:flex;gap:8px}.mwpState{font-weight:800;margin-bottom:6px}
  .mwpState.ok{color:#34e58b}.mwpState.warn{color:#ffcc3d}.mwpState.bad{color:#ff5261}
  .mwpRow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid #173047}
  .mwpRow small{display:block;color:#90abc0}.mwpTap{padding:8px;border:1px dashed #ffcc3d;border-radius:8px;margin-bottom:8px}`;
  document.head.appendChild(st);
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let tap = null, auto = null;

  function mapMeta() { return (typeof state !== 'undefined' && state && state.map && state.map.width) ? state.map : null; }
  function mapping() { try { return typeof mappingMode === 'function' && mappingMode(state); } catch (e) { return true; } }
  function toWorld(px, py, meta) {
    const t = transform(meta), gx = (px - t.ox) / t.scale, gy = meta.height - 1 - (py - t.oy) / t.scale;
    const c = Math.cos(meta.origin_yaw || 0), s = Math.sin(meta.origin_yaw || 0), r = meta.resolution;
    return [meta.origin_x + (c * gx - s * gy) * r, meta.origin_y + (s * gx + c * gy) * r];
  }
  cv.addEventListener('click', e => {
    const meta = mapMeta();
    if (!meta) return;
    if (mapping()) { alert('Mapping in progress: waypoints can be added on the accepted map only.'); return; }
    const r = cv.getBoundingClientRect(), k = cv.width / r.width;
    const [x, y] = toWorld((e.clientX - r.left) * k, (e.clientY - r.top) * k, meta);
    tap = { x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100 };
    $('mwpXY').textContent = `Tapped point: x ${tap.x.toFixed(2)} m, y ${tap.y.toFixed(2)} m`;
    $('mwpTap').hidden = false;
    if (typeof draw === 'function') draw();
  });
  const baseDraw = window.draw;
  if (typeof baseDraw === 'function') {
    window.draw = function () {
      baseDraw.apply(this, arguments);
      const meta = mapMeta();
      if (!tap || !meta) return;
      const p = worldPixel(tap.x, tap.y, meta, transform(meta)), d = Math.max(1, window.devicePixelRatio || 1);
      ctx.save(); ctx.strokeStyle = '#ffcc3d'; ctx.lineWidth = 3 * d;
      ctx.beginPath(); ctx.arc(p[0], p[1], 10 * d, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(p[0] - 16 * d, p[1]); ctx.lineTo(p[0] + 16 * d, p[1]); ctx.moveTo(p[0], p[1] - 16 * d); ctx.lineTo(p[0], p[1] + 16 * d); ctx.stroke();
      ctx.restore();
    };
  }
  async function post(body) {
    try {
      const r = await fetch('/api/places', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({}));
      alert(d.message || ('request ' + r.status)); return d;
    } catch (e) { alert('CONTROL LINK LOST'); return {}; }
  }
  $('mwpCancel').onclick = () => { tap = null; $('mwpTap').hidden = true; if (typeof draw === 'function') draw(); };
  $('mwpSave').onclick = async () => {
    const name = $('mwpName').value.trim();
    if (!tap || !name) { alert('Tap the map and type a name first'); return; }
    await post({ action: 'save_at', name, x: tap.x, y: tap.y });
    $('mwpName').value = ''; tap = null; $('mwpTap').hidden = true; setTimeout(poll, 1500);
  };
  $('mwpList').onclick = async e => {
    const b = e.target.closest('[data-go]');
    if (!b || b.disabled) return;
    if (!confirm('Drive autonomously to "' + b.dataset.go + '"?\n\nB on the remote stops immediately.')) return;
    await post({ action: 'go', name: b.dataset.go });
  };
  function render(d) {
    auto = d;
    const a = d.autonomy || {}, on = a.armed === true, s = $('mwpState');
    s.textContent = !d.policy_fresh ? 'AUTONOMY STATE UNKNOWN' : on ? (d.stop_latched ? 'AUTONOMY ON — release E-STOP to Go' : 'AUTONOMY ON — ready') : 'AUTONOMY OFF — Go disabled';
    s.className = 'mwpState ' + (!d.policy_fresh ? 'bad' : on ? 'ok' : 'warn');
    const canGo = on && d.stop_latched === false;
    $('mwpList').innerHTML = (d.places || []).filter(p => p.current_map).map(p => `<div class="mwpRow"><div><b>${esc(p.name)}</b><small>${p.x.toFixed(2)}, ${p.y.toFixed(2)}</small></div>
      <button data-go="${esc(p.name)}" ${canGo ? '' : 'disabled'}>Go</button></div>`).join('') || '<div class="note">No waypoints on this map yet</div>';
  }
  async function poll() {
    if (document.hidden) return;
    try { render(await fetch('/api/autonomy', { cache: 'no-store' }).then(r => r.json())); }
    catch (e) { render({ policy_fresh: false, places: (auto && auto.places) || [] }); }
  }
  setInterval(poll, 1500); poll();
})();
