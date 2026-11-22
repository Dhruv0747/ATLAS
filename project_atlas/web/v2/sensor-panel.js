/* ATLAS "What ATLAS sees" — every sensor in one place (2026-11-22 owner request "add kar do").
 * Read-only: polls /api/status once a second (only while the page is visible) and the IMX708 latest frame every 2 s.
 * Each tile says whether the Nav2 LiDAR safety gate uses that sensor. No commands, no settings. */
(function () {
  'use strict';
  const css = `
  #sensorPanel{margin:10px 0;padding:12px;border:1px solid #2a5770;border-radius:12px;background:#0b1c29!important;color:#e7f5ff!important}
  #sensorPanel *{color:inherit}#sensorPanel h2{margin:0 0 8px;font-size:18px;color:#fff!important}
  #sensorPanel .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
  #sensorPanel .t{border:1px solid #2a5770;border-radius:10px;padding:10px;background:#0e2536!important}
  #sensorPanel .t b{display:block;font-size:15px;color:#fff!important}
  #sensorPanel .v{font-size:20px;font-weight:700;margin:4px 0}
  #sensorPanel .s{font-size:13px;color:#aec6d9!important;white-space:pre-line;overflow-wrap:anywhere}
  #sensorPanel .gate{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;margin-top:6px}
  #sensorPanel .gate.yes{background:#124d2f!important;color:#8dffc0!important}#sensorPanel .gate.no{background:#33404a!important;color:#c7d3dc!important}
  #sensorPanel .stale{color:#ff8a94!important;font-weight:700}#sensorPanel .warn{color:#ffcf74!important}
  #sensorPanel img{width:100%;border-radius:8px;display:block;margin-top:6px;background:#000}`;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  const host = document.getElementById('gate');
  if (!host) return;
  const panel = document.createElement('section'); panel.id = 'sensorPanel'; panel.setAttribute('aria-live', 'polite');
  panel.innerHTML = '<h2>All sensors</h2><div class="grid" id="sensorGrid">Waiting for ATLAS…</div>';
  host.after(panel);

  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const item = (r, k) => (r && r[k]) || null;
  const val = (r, k, d) => { const i = item(r, k); return i && i.value != null ? i.value : d; };
  const age = (r, k) => { const i = item(r, k); return i && typeof i.age === 'number' ? i.age : null; };
  const json = v => { if (typeof v !== 'string') return v; try { return JSON.parse(v); } catch (e) { return null; } };
  const num = (v, d = 2) => (typeof v === 'number' && isFinite(v)) ? v.toFixed(d) : '--';
  const fresh = (r, k, lim = 3) => { const a = age(r, k); return a == null ? '<span class="stale">NO DATA</span>' : a > lim ? `<span class="stale">STALE ${a.toFixed(0)} s</span>` : `live · ${a.toFixed(1)} s`; };
  const tile = (name, value, sub, gate, extra = '') =>
    `<div class="t"><b>${name}</b><div class="v">${value}</div><div class="s">${sub}</div>${extra}<span class="gate ${gate ? 'yes' : 'no'}">${gate ? 'USED BY SAFETY GATE' : 'NOT USED BY SAFETY GATE'}</span></div>`;
  const mm = v => (typeof v === 'number' && v > 0) ? (v / 1000).toFixed(2) + ' m' : '--';

  let camUrl = null;
  function render(d) {
    const r = d.ros || {};
    const li = val(r, 'lidar', {}) || {};
    const q = val(r, 'amcl_quality', {}) || {};
    const od = val(r, 'odom', {}) || {};
    const enc = json(val(r, 'encoder_health', null)) || {};
    const cam = val(r, 'camera_info', {}) || {};
    const gx = window.__atlasGate || {};
    const gpsFix = val(r, 'gps_fix', {}) || {};
    const gpsRx = String(val(r, 'gps_receiver_status', '') || '');
    const fixed = gpsFix.status != null && gpsFix.status >= 0;
    const radarZone = val(r, 'radar_zone', '--');
    const tiles = [
      tile('LiDAR (RPLIDAR)', `${li.points || 0}/${li.total || 0} points`, `nearest ${num(li.nearest_m)} m\n${fresh(r, 'lidar')}`, true),
      tile('Astra depth camera', gx.astra_fresh ? `${(gx.astra_obstacles || []).length} obstacle directions` : '<span class="warn">no fresh coverage</span>',
        `blue dots on the ring view = what the depth camera sees as obstacles\n${gx.astra_fresh ? 'live' : 'coverage stale or not running'}`, true),
      tile('Ultrasonic front / rear', `${mm(val(r, 'us_front'))} / ${mm(val(r, 'us_rear'))}`, `${esc(val(r, 'us_status', ''))}\n${fresh(r, 'us_front')}`, true),
      tile('Ultrasonic left / right', `${mm(val(r, 'us_left'))} / ${mm(val(r, 'us_right'))}`, `measured mounts not set up yet, so the gate ignores these\n${fresh(r, 'us_left')}`, false),
      tile('Location (AMCL on map)', q.xy_std_m != null ? `±${num(q.xy_std_m, 3)} m` : '<span class="warn">invalid</span>',
        `heading ±${num(q.yaw_std_deg, 1)}°${q.uncertain ? ' · UNCERTAIN' : ''}\ngate trusts the map only below ±0.15 m\n${fresh(r, 'amcl_quality')}`, true),
      tile('Radar (RD-03D)', `${val(r, 'radar_count', 0)} target(s)`, `nearest ${mm(val(r, 'radar_dist'))} · ${esc(radarZone)}\nx ${num(val(r, 'radar_x'), 0)} mm, y ${num(val(r, 'radar_y'), 0)} mm (radar's own frame)\n${fresh(r, 'radar_dist')}`, false),
      tile('IMU (compass + tilt)', `${num(val(r, 'imu_heading'), 0)}°`, `roll ${num(val(r, 'imu_roll'), 1)}° · pitch ${num(val(r, 'imu_pitch'), 1)}°\n${fresh(r, 'imu_heading')}`, false),
      tile('Wheels + encoders', `${num(od.vx, 2)} m/s`, `turn ${num(od.wz, 2)} rad/s\nencoders ${esc(enc.state || '--')}${(enc.excluded_encoders || []).length ? ' · excluded M' + enc.excluded_encoders.join(',M') : ''}\n${fresh(r, 'odom')}`, false),
      tile('GPS (Hiwonder V1)', fixed ? 'FIX' : '<span class="warn">no fix</span>',
        `${num(val(r, 'gps_sats'), 0)} satellites · HDOP ${num(val(r, 'gps_hdop'), 1)}${fixed ? `\n${num(gpsFix.lat, 6)}, ${num(gpsFix.lon, 6)}` : ''}\n${/NO_FIX/.test(gpsRx) ? 'indoors: needs open sky' : ''}\n${fresh(r, 'gps_hdop', 5)}`, false),
      tile('Front camera (IMX708)', cam.streaming ? 'streaming' : '<span class="warn">not streaming</span>', `${esc(cam.ai || '')}\n${fresh(r, 'camera_info')}`, false,
        camUrl ? `<img id="spCam" alt="Latest IMX708 frame" src="${camUrl}">` : '<div class="s" id="spCamWait">waiting for a frame…</div>'),
    ];
    document.getElementById('sensorGrid').innerHTML = tiles.join('');
  }

  let busy = false;
  async function poll() {
    if (document.hidden || busy) return; busy = true;
    try { const r = await fetch('/api/status', { cache: 'no-store', signal: AbortSignal.timeout(2500) }); render(await r.json()); }
    catch (e) { document.getElementById('sensorGrid').innerHTML = '<span class="stale">Lost contact with ATLAS</span>'; }
    finally { busy = false; }
  }
  function refreshCam() {
    if (document.hidden) return;
    const pre = new Image(); const url = '/camera.jpg?latest=' + Date.now();
    pre.onload = () => { camUrl = url; const img = document.getElementById('spCam'); if (img) img.src = url; else { const w = document.getElementById('spCamWait'); if (w) w.outerHTML = `<img id="spCam" alt="Latest IMX708 frame" src="${url}">`; } };
    pre.src = url;
  }
  setInterval(poll, 1000); setInterval(refreshCam, 2000); poll(); refreshCam();
})();
