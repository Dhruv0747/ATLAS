/* ATLAS "FIX MY LOCATION" (2026-11-21 owner request).
 * When the dashboard says "Localization unknown" / "lost", one button re-runs the boot-time LiDAR map search
 * (POST /api/relocalize). ATLAS never moves; AMCL is set only for a unique, strong match. Autonomy must be OFF.
 * The button sits in the location-check panel; the red localization chip in the top bar opens it too. */
(function () {
  'use strict';
  const css = `
  #findLocSheet{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:99998;width:min(92vw,460px);box-sizing:border-box;padding:16px;border-radius:16px;background:#06192a;color:#e8f4ff;border:2px solid #19cfff;box-shadow:0 12px 40px rgba(0,0,0,.55);font:15px/1.4 system-ui,sans-serif}
  #findLocSheet b{display:block;font-size:18px;margin-bottom:4px}
  #findLocSheet .row{display:flex;gap:10px;margin-top:12px}
  #findLocSheet button{flex:1;min-height:52px;border-radius:12px;font:700 16px system-ui,sans-serif;cursor:pointer}
  #findLocSheet #findLocGo{background:#0a7fb8!important;color:#fff!important;border:0!important}
  #findLocSheet #findLocGo:disabled{opacity:.6}
  #findLocSheet #findLocNo{background:transparent!important;color:#e8f4ff!important;border:1px solid #6fc8ee!important}
  #findLocSheet .msg{margin-top:10px;font-size:14px;white-space:pre-line}
  #findLocSheet .ok{color:#5dfcae;font-weight:700}#findLocSheet .bad{color:#ff8a94;font-weight:700}
  .findLocBtn{margin-left:6px}`;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  let pollTimer = null, closeTimer = null;
  const $ = id => document.getElementById(id);
  function close() { clearInterval(pollTimer); clearInterval(closeTimer); pollTimer = closeTimer = null; const s = $('findLocSheet'); if (s) s.remove(); }
  function msg(html) { const m = $('findLocMsg'); if (m) m.innerHTML = html; }
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function showResult(last) {
    const go = $('findLocGo'); if (go) { go.disabled = false; go.textContent = 'TRY AGAIN'; }
    const no = $('findLocNo'); if (no) no.textContent = 'Close';
    if (!last) { msg('<span class="bad">No result.</span>'); return; }
    if (last.seeded) {
      const p = last.pose || {};
      msg(`<span class="ok">✅ Location found and set</span>\nx ${Number(p.x).toFixed(2)} m • y ${Number(p.y).toFixed(2)} m • facing ${Math.round(p.yaw_deg)}°${last.fit != null ? ` • fit ${Number(last.fit).toFixed(2)}` : ''}\nThe location chip turns green after the next check (about 30 s).`);
    } else {
      msg(`<span class="bad">❌ Location not found</span>\n${esc(last.reason || last.state)}\nClear around ATLAS (1 m, nothing in front of the LiDAR, nobody walking past) or drive it to an open mapped spot, then TRY AGAIN.`);
    }
  }

  async function poll() {
    try {
      const r = await fetch('/api/relocalize', { cache: 'no-store' }); const d = await r.json();
      if (d.running) { msg(`Searching the map with the LiDAR… ${d.elapsed_s != null ? Math.round(d.elapsed_s) + ' s' : ''}\nKeep ATLAS still and the LiDAR clear.`); return; }
      clearInterval(pollTimer); pollTimer = null; showResult(d.last);
    } catch (e) { msg('<span class="bad">Lost contact with ATLAS: ' + esc(e.message) + '</span>'); }
  }

  async function go() {
    clearInterval(closeTimer); closeTimer = null;
    const b = $('findLocGo'); b.disabled = true; b.textContent = 'Searching…';
    msg('Starting…');
    try {
      const r = await fetch('/api/relocalize', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: JSON.stringify({ confirm: 'FIND_LOCATION' }) });
      const d = await r.json();
      if (!r.ok || !d.ok) throw Error(d.message || ('HTTP ' + r.status));
      msg(esc(d.message));
      clearInterval(pollTimer); pollTimer = setInterval(poll, 2000);
    } catch (e) { b.disabled = false; b.textContent = 'FIX MY LOCATION'; msg('<span class="bad">' + esc(e.message) + '</span>'); }
  }

  window.findMyLocation = function () {
    if ($('findLocSheet')) return;
    const s = document.createElement('div'); s.id = 'findLocSheet'; s.setAttribute('role', 'alertdialog');
    s.innerHTML = '<b>Fix ATLAS location?</b>ATLAS stays still while the LiDAR searches the whole map (up to about 90 s). Its location is set only for a single, strong match. Autonomy must be OFF; keep 1 m clear around ATLAS.' +
      '<div class="row"><button id="findLocGo" type="button">FIX MY LOCATION</button><button id="findLocNo" type="button">Cancel</button></div><div class="msg" id="findLocMsg">Closes in 15 s</div>';
    document.body.appendChild(s);
    $('findLocGo').onclick = go; $('findLocNo').onclick = close;
    let left = 15; closeTimer = setInterval(() => { left -= 1; msg('Closes in ' + left + ' s'); if (left <= 0) close(); }, 1000);
    fetch('/api/relocalize', { cache: 'no-store' }).then(r => r.json()).then(d => { if (d.running) { clearInterval(closeTimer); closeTimer = null; $('findLocGo').disabled = true; $('findLocGo').textContent = 'Searching…'; pollTimer = setInterval(poll, 2000); poll(); } }).catch(() => {});
  };

  // Button in the location panel (inserted by location-check.js) and a click on the red localization chip.
  function attach() {
    const actions = document.querySelector('.atlas-location .actions');
    if (actions && !actions.querySelector('.findLocBtn')) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'findLocBtn'; b.textContent = 'FIX MY LOCATION';
      b.onclick = () => window.findMyLocation();
      const first = actions.querySelector('[data-cancel]');
      first ? first.after(b) : actions.appendChild(b);
    }
    const chip = $('v2Loc');
    if (chip && !chip.dataset.findLoc) {
      chip.dataset.findLoc = '1'; chip.style.cursor = 'pointer';
      chip.addEventListener('click', () => { if (/unknown|lost/i.test(chip.textContent)) window.findMyLocation(); });
    }
    return !!actions && !!chip;
  }
  if (!attach()) {
    const mo = new MutationObserver(() => { if (attach()) mo.disconnect(); });
    mo.observe(document.body, { childList: true, subtree: true }); setTimeout(() => mo.disconnect(), 20000);
  }
})();
