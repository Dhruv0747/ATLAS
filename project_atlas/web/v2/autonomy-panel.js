/* 2026-11-15 ATLAS dashboard: AUTONOMY ON/OFF + waypoints. The server/mux/mission control decide; this only asks.
   ON needs the operator PIN and is refused unless the E-STOP is latched, the rover is still, encoders are
   autonomy-ready and the autonomous speed is validated. OFF and any E-STOP always win. */
(function () {
  const box = document.getElementById('autonomyPanel');
  if (!box) return;
  box.innerHTML = `
   <div class="apHead">
    <span class="apState warn" id="apState">MODE …</span>
    <input id="apPin" type="password" inputmode="numeric" autocomplete="off" maxlength="12" placeholder="Operator PIN (for Autonomous)" aria-label="Operator PIN to switch to Autonomous mode">
    <button class="btn apOffBtn" id="apOff" type="button" aria-pressed="false">Manual mode</button>
    <button class="btn" id="apOn" type="button" aria-pressed="false">Autonomous mode</button>
   </div>
   <div class="apWhy" id="apWhy"></div>
   <a class="btn apReady" href="/v2/readiness">Autonomy readiness: kya rok raha hai / kaise kholein</a>
   <div class="apSave">
    <input id="apName" maxlength="24" placeholder="Waypoint name (e.g. kitchen)" aria-label="New waypoint name">
    <button class="btn" id="apSaveBtn" type="button">Save waypoint here</button>
   </div>
   <div class="apList" id="apList"><div class="apEmpty">No waypoints yet</div></div>`;
  const $ = id => document.getElementById(id);
  let last = null;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const toastMsg = m => (window.toast ? window.toast(m) : alert(m));
  async function send(path, body) {
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Atlas-Wifi': '1' }, body: JSON.stringify(body) });
      const d = await r.json().catch(() => ({}));
      toastMsg(d.message || ('request ' + r.status));
      return d;
    } catch (e) { toastMsg('CONTROL LINK LOST'); return {}; }
  }
  function render(d) {
    last = d;
    const a = d.autonomy || {}, st = $('apState');
    const on = a.armed === true;
    st.textContent = !d.policy_fresh ? 'MODE UNKNOWN' : on ? 'MODE: AUTONOMOUS' : 'MODE: MANUAL (remote only)';
    $('apOn').classList.toggle('apSel', on); $('apOff').classList.toggle('apSel', d.policy_fresh && !on);
    $('apOn').setAttribute('aria-pressed', String(on)); $('apOff').setAttribute('aria-pressed', String(!on));
    st.className = 'apState ' + (!d.policy_fresh ? 'bad' : on ? 'ok' : 'warn');
    const blockers = a.arm_blockers || [];
    $('apWhy').textContent = !d.policy_fresh ? 'No fresh state from the mux.' : on
      ? (d.stop_latched ? 'E-STOP latched: release it with the remote, then press Go.' : 'Nav2 may drive. Keep the remote in hand; B stops and switches back to Manual.')
      : (blockers.length ? 'Autonomous blocked: ' + blockers.join(' • ') : 'Ready: enter the PIN and press Autonomous mode.');
    $('apOn').disabled = !d.policy_fresh || on || blockers.length > 0;
    $('apOff').disabled = false;
    const canGo = on && d.stop_latched === false;
    $('apList').innerHTML = (d.places || []).map(p => `
      <div class="apPlace${p.current_map ? '' : ' old'}">
       <div><b>${esc(p.name)}</b><small>${p.x.toFixed(2)}, ${p.y.toFixed(2)}${p.current_map ? '' : ' • other map'}</small></div>
       <button class="btn" data-go="${esc(p.name)}" ${canGo && p.current_map ? '' : 'disabled'} title="${canGo ? 'Navigate here' : 'Needs Autonomous mode and E-STOP released'}">Go</button>
       <button class="btn ghost" data-del="${esc(p.name)}">Delete</button>
      </div>`).join('') || '<div class="apEmpty">No waypoints yet</div>';
  }
  async function poll() {
    if (document.hidden) return;
    try { render(await fetch('/api/autonomy', { cache: 'no-store' }).then(r => r.json())); }
    catch (e) { render({ policy_fresh: false, places: (last && last.places) || [] }); }
  }
  $('apOn').onclick = async () => {
    if (!confirm('Switch to AUTONOMOUS mode?\n\nNav2 may then drive the rover after you release the E-STOP. Keep the remote in hand.')) return;
    await send('/api/autonomy', { action: 'on', pin: $('apPin').value }); $('apPin').value = ''; poll();
  };
  $('apOff').onclick = async () => { await send('/api/autonomy', { action: 'off' }); poll(); };
  $('apSaveBtn').onclick = async () => {
    const name = $('apName').value.trim();
    if (!name) { toastMsg('Type a waypoint name first'); return; }
    await send('/api/places', { action: 'save', name }); $('apName').value = ''; setTimeout(poll, 1200);
  };
  $('apList').onclick = async e => {
    const go = e.target.closest('[data-go]'), del = e.target.closest('[data-del]');
    if (go && !go.disabled) {
      if (!confirm('Drive autonomously to "' + go.dataset.go + '"?\n\nB on the remote stops immediately.')) return;
      await send('/api/places', { action: 'go', name: go.dataset.go });
    } else if (del) {
      if (!confirm('Delete waypoint "' + del.dataset.del + '"?')) return;
      await send('/api/places', { action: 'delete', name: del.dataset.del }); setTimeout(poll, 1200);
    }
  };
  setInterval(poll, 1000); poll();
})();
