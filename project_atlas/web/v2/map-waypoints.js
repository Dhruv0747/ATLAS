/* 2026-11-15 ATLAS navigation page: tap the map to add a waypoint, then Go. Only asks the server:
   mission control refuses unknown/occupied/too-tight spots (0.35 m clearance on the accepted map), and Go is refused
   unless AUTONOMY is ON and the E-STOP is released. Disabled while mapping (live SLAM map = different frame). */
(function () {
  const side = document.querySelector('aside.side'), cv = document.getElementById('mapCanvas');
  if (!side || !cv) return;
  const card = document.createElement('section');
  card.className = 'card mwp';
  card.innerHTML = `<h2>DRIVE MODE AND WAYPOINTS — TAP THE MAP</h2>
   <div class="mwpState" id="mwpState">Mode …</div>
   <div class="mwpMode"><button id="mwpManual" type="button">Manual mode</button><button id="mwpAuto" type="button">Autonomous mode</button></div>
   <input id="mwpPin" type="password" inputmode="numeric" autocomplete="off" maxlength="12" placeholder="Operator PIN (for Autonomous)" aria-label="Operator PIN to switch to Autonomous mode">
   <div class="mwpWhy" id="mwpWhy"></div>
   <a href="/v2/readiness" style="display:inline-block;margin-bottom:8px;color:#ffcc3d;font-weight:700">→ Readiness: kya rok raha hai / kaise kholein</a>
   <div class="mwpTap" id="mwpTap" hidden>
    <div id="mwpXY"></div>
    <div class="mwpBtns"><button class="mwpGo" id="mwpMove" type="button">Move here</button><button id="mwpCancel" type="button">Cancel</button></div>
    <input id="mwpName" maxlength="24" placeholder="…or save it as a waypoint: name" aria-label="Waypoint name">
    <button id="mwpSave" type="button">Save waypoint</button>
   </div>
   <div id="mwpList"></div>
   <div class="note">Tap a free spot on the map. ATLAS refuses spots that are unknown, occupied or closer than 0.35 m to a wall.
   Move / Go need Autonomous mode and the E-STOP released. ATLAS replans around obstacles and says out loud why it
   stops; B on the remote always stops and switches back to Manual.</div>`;
  side.insertBefore(card, side.children[2] || null);
  const st = document.createElement('style');
  st.textContent = `.mwp input{width:100%;min-height:42px;margin:8px 0;padding:8px 10px;border-radius:8px;border:1px solid #315b74;background:#07131f;color:#edf8ff;font:inherit}
  .mwp button{min-height:42px;padding:6px 12px;border-radius:8px;border:1px solid #2d6a8c;background:#0a3047;color:#fff;font:inherit;font-weight:700;cursor:pointer}
  .mwp button:disabled{opacity:.45;cursor:default}.mwpBtns{display:flex;gap:8px}.mwpState{font-weight:800;margin-bottom:6px}
  .mwpState.ok{color:#34e58b}.mwpState.warn{color:#ffcc3d}.mwpState.bad{color:#ff5261}
  .mwpRow{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid #173047}
  .mwpRow small{display:block;color:#90abc0}.mwpTap{padding:8px;border:1px dashed #ffcc3d;border-radius:8px;margin:8px 0}
  .mwpMode{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mwp button.sel{border-color:#34e58b;color:#34e58b;box-shadow:0 0 0 2px rgba(52,229,139,.2) inset}
  .mwpWhy{font-size:12px;color:#90abc0;margin-bottom:6px}.mwp button.mwpGo{background:#0f4a2c;border-color:#34e58b}`;
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
  async function mode(body) {
    try {
      const r = await fetch('/api/autonomy', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({})); alert(d.message || ('request ' + r.status));
    } catch (e) { alert('CONTROL LINK LOST'); }
    $('mwpPin').value = ''; poll();
  }
  $('mwpManual').onclick = () => mode({ action: 'off' });
  $('mwpAuto').onclick = () => {
    if (!confirm('Switch to AUTONOMOUS mode?\n\nNav2 may then drive after you release the E-STOP. Keep the remote in hand.')) return;
    mode({ action: 'on', pin: $('mwpPin').value });
  };
  $('mwpMove').onclick = async () => {
    if (!tap || $('mwpMove').disabled) return;
    if (!confirm(`Drive autonomously to x ${tap.x.toFixed(2)}, y ${tap.y.toFixed(2)}?\n\nB on the remote stops immediately.`)) return;
    const d = await post({ action: 'go_at', x: tap.x, y: tap.y });
    // 2026-11-15: once the goal is accepted the Nav2 goal marker (red) shows the target; drop the tap crosshair
    if (d && d.ok) { tap = null; $('mwpTap').hidden = true; if (typeof draw === 'function') draw(); }
  };
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
    s.textContent = !d.policy_fresh ? 'MODE UNKNOWN' : on ? (d.stop_latched ? 'MODE: AUTONOMOUS — release E-STOP to move' : 'MODE: AUTONOMOUS — ready') : 'MODE: MANUAL — Move / Go disabled';
    s.className = 'mwpState ' + (!d.policy_fresh ? 'bad' : on ? 'ok' : 'warn');
    const canGo = on && d.stop_latched === false, blockers = a.arm_blockers || [];
    $('mwpManual').classList.toggle('sel', !!d.policy_fresh && !on); $('mwpAuto').classList.toggle('sel', on);
    $('mwpAuto').disabled = !d.policy_fresh || on || blockers.length > 0;
    $('mwpPin').hidden = on;
    $('mwpWhy').textContent = !d.policy_fresh ? 'No fresh state from the mux.' : on ? 'B on the remote stops and switches back to Manual.'
      : (blockers.length ? 'Autonomous blocked: ' + blockers.join(' • ') : 'Enter the PIN and press Autonomous mode.');
    $('mwpMove').disabled = !canGo;
    $('mwpMove').title = canGo ? 'Drive to the tapped point' : 'Needs Autonomous mode and the E-STOP released';
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
