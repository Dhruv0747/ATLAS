/* ATLAS USB power health (2026-11-21 owner request): which USB hub lost power, and when.
 * Data: GET /api/usb_power (scripts/atlas_usb_power_monitor.py). Read-only; polls only while the
 * "Power and environment" drawer is open and the page is visible.
 * Per-device USB current is NOT measurable on ATLAS (no sensor per port). Each device line shows its
 * USB link health: 1 = up, 0.75 = re-enumerated, 0.5 = USB error, 0 = gone. A power sag on a hub shows
 * as dips on every device of that hub at the same moment. The top chart is the Jetson input rail (VDD_IN). */
(function () {
  'use strict';
  const root = document.getElementById('usbPower');
  if (!root) return;
  const drawer = document.getElementById('drawerPower');
  const css = `
  .usbp{display:grid;gap:10px}
  .usbp .usbpHead{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;justify-content:space-between}
  .usbp h3{margin:0;font-size:15px;letter-spacing:.04em}
  .usbp .usbpNote{font-size:12px;color:var(--mute,#8fa3b8)}
  .usbp .usbpBanner{padding:9px 12px;border-radius:10px;font-weight:700;font-size:14px}
  .usbp .ok{background:rgba(44,224,143,.12);color:#5dfcae;border:1px solid rgba(44,224,143,.35)}
  .usbp .bad{background:rgba(255,82,97,.14);color:#ff8a94;border:1px solid rgba(255,82,97,.45)}
  .usbp.light .ok{background:rgba(19,131,79,.10);color:#0d6b40;border-color:rgba(19,131,79,.45)}
  .usbp.light .bad{background:rgba(208,32,47,.08);color:#a8131f;border-color:rgba(208,32,47,.5)}
  .usbp.light .usbpNote{color:#41566b}
  .usbp .hub{border:1px solid var(--line,#1f3346);border-radius:12px;padding:8px 10px}
  .usbp .hub.bad{border-color:rgba(255,82,97,.6)}
  .usbp .hubTitle{display:flex;justify-content:space-between;gap:8px;font-size:13px;font-weight:700;margin-bottom:4px}
  .usbp .dev{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:8px;align-items:center;font-size:12px;margin:3px 0}
  .usbp .dev .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .usbp .dev .nm small{display:block;color:var(--mute,#8fa3b8)}
  .usbp canvas{width:100%;display:block}
  @media (max-width:560px){.usbp .dev{grid-template-columns:1fr}}`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // Light or dark dashboard theme: judge by the drawer's text colour (dark text = light theme).
  function isLight() {
    const m = getComputedStyle(root).color.match(/\d+/g);
    if (!m) return false;
    const [r, g, b] = m.map(Number);
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5;
  }
  let P = {};
  function palette() {
    P = isLight()
      ? { volt: '#0a72a8', amp: '#a86f00', ok: '#13834f', err: '#d0202f', warn: '#c26a00', text: '#41566b', fill: 'rgba(10,40,70,.06)' }
      : { volt: '#19cfff', amp: '#ffcc3d', ok: '#2ce08f', err: '#ff5261', warn: '#ffb03d', text: '#8fa3b8', fill: 'rgba(255,255,255,.04)' };
  }
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let busy = false, timer = null;

  function canvasFor(id, h) {
    let c = document.getElementById(id);
    if (!c) return null;
    const w = Math.max(200, Math.round(c.clientWidth || 300));
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const g = c.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    return { g, w, h };
  }

  // Smooth line through points with a light moving average (display only; raw values are in the API).
  function smooth(vals, k) {
    return vals.map((v, i) => {
      if (v == null) return null;
      let s = 0, n = 0;
      for (let j = Math.max(0, i - k); j <= Math.min(vals.length - 1, i + k); j++) if (vals[j] != null) { s += vals[j]; n++; }
      return n ? s / n : null;
    });
  }

  function line(g, xs, ys, color, width) {
    g.strokeStyle = color; g.lineWidth = width; g.lineJoin = 'round'; g.beginPath();
    let started = false, px = 0, py = 0;
    for (let i = 0; i < xs.length; i++) {
      if (ys[i] == null) { started = false; continue; }
      if (!started) { g.moveTo(xs[i], ys[i]); started = true; }
      else { const mx = (px + xs[i]) / 2, my = (py + ys[i]) / 2; g.quadraticCurveTo(px, py, mx, my); }
      px = xs[i]; py = ys[i];
    }
    if (started) g.lineTo(px, py);
    g.stroke();
  }

  function xScale(t, w, span, pad) { return t.map(v => pad + (w - pad - 4) * (1 + v / span)); }

  function drawRail(d) {
    const c = canvasFor('usbpRail', 120); if (!c) return;
    const { g, w, h } = c, pad = 44, span = d.window_s || 600;
    const v = d.vin_v || [], a = d.iin_a || [], xs = xScale(d.t || [], w, span, pad);
    const vv = v.filter(x => x != null), lo = Math.min(4.5, ...vv), hi = Math.max(5.2, ...vv);
    const aa = a.filter(x => x != null), amax = Math.max(3, ...aa);
    g.fillStyle = P.fill; g.fillRect(pad, 6, w - pad - 4, h - 22);
    g.strokeStyle = 'rgba(255,82,97,.5)'; g.setLineDash([4, 4]); g.beginPath();
    const y475 = 6 + (h - 22) * (1 - (4.75 - lo) / (hi - lo)); g.moveTo(pad, y475); g.lineTo(w - 4, y475); g.stroke(); g.setLineDash([]);
    g.fillStyle = P.text; g.font = '11px system-ui';
    g.fillText(hi.toFixed(2) + ' V', 2, 14); g.fillText(lo.toFixed(2) + ' V', 2, h - 18); g.fillText('4.75 V', 2, y475 + 4);
    g.fillText('-' + Math.round(span / 60) + ' min', pad, h - 3); g.fillText('now', w - 26, h - 3);
    line(g, xs, smooth(v, 2).map(x => x == null ? null : 6 + (h - 22) * (1 - (x - lo) / (hi - lo))), P.volt, 2.2);
    const c2 = canvasFor('usbpAmps', 64); if (!c2) return;
    const g2 = c2.g, h2 = c2.h, xs2 = xScale(d.t || [], c2.w, span, pad);
    g2.fillStyle = P.fill; g2.fillRect(pad, 4, c2.w - pad - 4, h2 - 8);
    g2.fillStyle = P.text; g2.font = '11px system-ui';
    g2.fillText(amax.toFixed(1) + ' A', 2, 14); g2.fillText('0 A', 2, h2 - 6);
    line(g2, xs2, smooth(a, 2).map(x => x == null ? null : 4 + (h2 - 8) * (1 - x / amax)), P.amp, 1.8);
  }

  function drawHealth(id, t, health, span) {
    const c = canvasFor(id, 26); if (!c) return;
    const { g, w, h } = c, xs = xScale(t, w, span, 0);
    g.fillStyle = P.fill; g.fillRect(0, 2, w, h - 4);
    for (let i = 0; i < health.length; i++) {            // red ticks under every fault second
      if (health[i] < 1) { g.fillStyle = health[i] === 0 ? P.err : P.warn; g.fillRect(xs[i] - 1.5, 2, 3, h - 4); }
    }
    line(g, xs, smooth(health, 0).map(x => x == null ? null : 3 + (h - 6) * (1 - x)), P.ok, 2);
  }

  function render(d) {
    const span = d.window_s || 600, hubs = d.hubs || {}, devs = d.devices || {};
    const suspect = d.suspect_hub, sh = suspect && hubs[suspect];
    const banner = sh
      ? `<div class="usbpBanner bad">⚠ Hub ${esc(suspect)}: ${sh.events_10min} USB fault${sh.events_10min === 1 ? '' : 's'} in the last 10 min — check this hub's power and cable first (${esc(sh.devices.map(p => devs[p].role).join(', '))})</div>`
      : '<div class="usbpBanner ok">No USB faults in the last 10 min on any hub</div>';
    const lastV = (d.vin_v || []).filter(x => x != null).slice(-1)[0], lastA = (d.iin_a || []).filter(x => x != null).slice(-1)[0];
    const order = Object.keys(hubs).sort((a, b) => (hubs[b].events_10min - hubs[a].events_10min) || a.localeCompare(b));
    palette();
    let html = `<div class="usbp ${isLight() ? 'light' : ''}"><div class="usbpHead"><h3>USB POWER HEALTH • last ${Math.round(span / 60)} min</h3>
      <span class="usbpNote">${esc(d.rail || 'Jetson rail sensor not found')} ${lastV != null ? `• ${lastV.toFixed(3)} V • ${lastA.toFixed(2)} A • ${(lastV * lastA).toFixed(1)} W` : ''}</span></div>
      ${banner}
      <div class="usbpNote"><span style="color:${P.volt}">━ Jetson VDD_IN volts (top)</span> &nbsp; <span style="color:${P.amp}">━ Jetson VDD_IN amps (below)</span> &nbsp; <span style="color:${P.err}">┄ 4.75 V</span></div>
      <canvas id="usbpRail" style="height:120px"></canvas><canvas id="usbpAmps" style="height:64px"></canvas>`;
    order.forEach((hub, hi) => {
      const h = hubs[hub];
      html += `<div class="hub ${h.events_10min ? 'bad' : ''}"><div class="hubTitle"><span>HUB ${esc(hub)} • ${esc(h.name)}</span>
        <span>${h.events_10min} faults / 10 min • ${h.events_1h} / 1 h • asks ${h.requested_ma} mA</span></div>`;
      h.devices.forEach((p, di) => {
        const dv = devs[p], le = dv.last_event;
        html += `<div class="dev"><div class="nm">${dv.present ? '' : '❌ '}${esc(dv.role)}<small>${esc(p)} ${esc((dv.ttys || []).join(' '))}${le ? ` • last ${esc(le.kind)} ${Math.round(le.age_s)} s ago` : ''}</small></div>
          <canvas id="usbpH${hi}_${di}" style="height:26px"></canvas></div>`;
      });
      html += '</div>';
    });
    html += `<div class="usbpNote">${esc(d.note || '')}</div></div>`;
    root.innerHTML = html;
    drawRail(d);
    order.forEach((hub, hi) => hubs[hub].devices.forEach((p, di) => drawHealth(`usbpH${hi}_${di}`, d.t || [], devs[p].health || [], span)));
  }

  async function poll() {
    if (busy || document.hidden || (drawer && !drawer.open)) return;
    busy = true;
    try {
      const r = await fetch('/api/usb_power', { cache: 'no-store' });
      const d = await r.json();
      if (!r.ok) throw Error(d.error || ('HTTP ' + r.status));
      render(d);
    } catch (e) {
      root.innerHTML = `<div class="usbp"><div class="usbpBanner bad">USB power health unavailable: ${esc(e.message)}</div></div>`;
    } finally { busy = false; }
  }

  function start() { if (!timer) timer = setInterval(poll, 2000); poll(); }
  if (drawer) drawer.addEventListener('toggle', () => { if (drawer.open) poll(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  start();
})();
