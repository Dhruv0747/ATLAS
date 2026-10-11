/* ATLAS Glass UI V2 shell: layout helpers and read-only status chips.
 * Adds no new control actions. The dock E-STOP sends exactly the same request as the
 * drive-pad E-STOP ({action:'e_stop'} via the existing post()). Status chips are display-only
 * and never authorize motion. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode: keep in memory */ } }
  };

  // ---- visibility-aware camera / radar (used by V2 patches P1/P2 in command.js) ----
  const visible = { camera: true, radar: true };
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(entries => {
      for (const e of entries) visible[e.target.dataset.pane] = e.isIntersecting;
    }, { rootMargin: '160px' });
    document.querySelectorAll('[data-pane]').forEach(el => io.observe(el));
  }
  const detailOpen = kind => {
    const m = $('sensorModal');
    // activeDetail is a top-level binding in command.js (shared global scope).
    return !!m && m.classList.contains('open') && typeof activeDetail !== 'undefined' && activeDetail === kind;
  };
  let saver = store.get('atlasV2Saver') === '1', tick = 0;
  function cameraWanted(force) {
    if (!(visible.camera || detailOpen('camera'))) return false;
    if (force || !saver) return true;
    tick = (tick + 1) % 3;           // data saver: ~2.7 frames/s instead of ~8
    return tick === 0;
  }
  const radarWanted = () => visible.radar || detailOpen('radar');
  window.atlasV2 = { cameraWanted, radarWanted, visible };

  // ---- preferences ----
  const saverBtn = $('v2CamRate'), liteBtn = $('v2Lite');
  const paint = () => {
    if (saverBtn) saverBtn.setAttribute('aria-pressed', String(saver));
    if (liteBtn) liteBtn.setAttribute('aria-pressed', String(document.documentElement.classList.contains('lite')));
  };
  if (saverBtn) saverBtn.addEventListener('click', () => { saver = !saver; store.set('atlasV2Saver', saver ? '1' : '0'); paint(); });
  if (liteBtn) liteBtn.addEventListener('click', () => {
    const on = document.documentElement.classList.toggle('lite'); store.set('atlasV2Lite', on ? '1' : '0'); paint();
  });
  paint();

  // ---- dock E-STOP: same handler as the drive-pad E-STOP (cancel local drive, then e_stop) ----
  const estop = $('v2Estop');
  // Fire on pointerdown: while another finger holds a drive button, a second-finger tap produces no
  // click on touch screens. Keyboard activation (click with detail 0) still works.
  const fireEstop = () => {
    if (typeof window.atlasEstop === 'function') window.atlasEstop();   // cancels local drive repeat first
    else if (typeof post === 'function') post({ action: 'e_stop' });
  };
  if (estop) {
    estop.addEventListener('pointerdown', e => { e.preventDefault(); fireEstop(); });
    estop.addEventListener('click', e => { if (e.detail === 0) fireEstop(); });
  }

  // ---- read-only status chips ----
  const setChip = (el, text, cls, title) => {
    if (!el) return;
    el.textContent = text;
    el.className = 'chip ' + (cls || '');
    if (title !== undefined) el.title = title;
  };
  let mapOk = 0, mapBusy = false, lastMap = null;
  async function pollMap() {
    if (document.hidden || mapBusy) return;
    mapBusy = true;
    try {
      const ctl = 'AbortController' in window ? new AbortController() : null;
      const t = ctl ? setTimeout(() => ctl.abort(), 2500) : 0;
      const r = await fetch('/api/map', { cache: 'no-store', signal: ctl ? ctl.signal : undefined });
      clearTimeout(t);
      if (!r.ok) throw new Error(r.status);
      lastMap = await r.json(); mapOk = Date.now();
    } catch (e) { /* shown as connection delayed below */ }
    finally { mapBusy = false; render(); }
  }
  // Mirrors liveStatus() in the Live map page (same order, thresholds and colours), so the chip is never
  // more optimistic than the map. Display only: it never authorizes motion.
  const age = it => it && it.age != null && isFinite(Number(it.age)) ? Number(it.age) : Infinity;
  function locChip() {
    const el = $('v2Loc'), s = lastMap;
    if (!mapOk || Date.now() - mapOk > 5000 || !s) return setChip(el, 'Connection delayed', 'fail', 'No fresh reply from ATLAS. Rover state unknown.');
    const cItem = s.localization_check, c = cItem && cItem.value && age(cItem) < 5 ? cItem.value : null;
    const vItem = s.start_verdict && s.start_verdict.value, v = vItem && vItem.current_boot ? vItem : null;
    const poseLive = age(s.pose) < 2, why = (c && c.reason) || '';
    const checked = !!c && c.state === 'VERIFIED' && c.check_age_s != null && c.check_age_s <= 60;
    if (c && c.state === 'LOST') return setChip(el, 'Localization lost', 'fail', why);
    if (v && v.state === 'UNKNOWN') return setChip(el, 'Localization unknown', 'fail', 'LiDAR did not confirm the start pose.');
    if (!poseLive) return setChip(el, 'Pose delayed', 'warn', 'Rover pose is not fresh on ATLAS.');
    if (checked) return setChip(el, 'Localization verified', 'ok', why);
    if (!c) return setChip(el, 'Localization not verified', 'warn', 'The LiDAR localization check is not reporting.');
    switch (c.state) {
      case 'MOVING_UNVERIFIED': return setChip(el, 'Moving · not verified', 'warn', why);
      case 'INPUT_STALE': return setChip(el, 'Localization unknown · stale data', 'fail', why);
      case 'PARKED_SETTLING': case 'VERIFYING': return setChip(el, 'Checking with LiDAR', 'warn', why);
      case 'DEGRADED': return setChip(el, 'Localization degraded', 'warn', why);
      default: return setChip(el, 'Localization not confirmed', 'warn', why);
    }
  }
  // latestStatus (command.js) is replaced by a new object on every successful /api/status poll.
  // If it stops changing, the link is down and the last motion/latch values must not be shown as current.
  let seenStatus = null, seenAt = 0;
  const freshStatus = () => {
    const d = typeof latestStatus !== 'undefined' ? latestStatus : null;
    if (d !== seenStatus) { seenStatus = d; seenAt = Date.now(); }
    return d && Date.now() - seenAt < 5000 ? d : null;
  };
  function motionText() {
    const d = freshStatus(), r = d && d.ros, o = r && r.odom;
    if (!d) return ['Motion unknown', 'fail', 'No fresh status from ATLAS. Rover state unknown.'];
    if (!o || !(o.age < 2) || !o.value) return ['Motion unknown', 'warn', 'Odometry is not fresh.'];
    const vx = Math.abs(Number(o.value.vx) || 0), wz = Math.abs(Number(o.value.wz) || 0);
    return vx > 0.01 || wz > 0.02 ? ['Moving', 'info', `vx ${vx.toFixed(2)} m/s · turn ${wz.toFixed(2)} rad/s`] : ['Stopped', 'ok', 'Odometry reports zero speed.'];
  }
  function latchChip() {
    const el = $('v2Latch'), d = freshStatus();
    let p = null;
    try { p = JSON.parse(d && d.ros && d.ros.control_policy && d.ros.control_policy.value); } catch (e) { p = null; }
    if (!el) return;
    if (p && p.stop_latched) { el.hidden = false; setChip(el, 'Drive stop latched', 'warn', String(p.stop_reason || '')); }
    else el.hidden = true;
  }
  function render() {
    locChip();
    const [t, c, title] = motionText();
    setChip($('v2Motion'), t, c, title); setChip($('v2DockMotion'), t, c, title);
    latchChip();
  }
  setInterval(pollMap, 2000); setInterval(render, 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) pollMap(); });
  pollMap();
})();
