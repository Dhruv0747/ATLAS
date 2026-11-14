/* ATLAS flight-style instruments for the IMU detail view (2026-11-14, owner request: "like a plane gyro").
 * Read-only drawing of live telemetry. Four instruments:
 *   1. Attitude indicator  - roll + pitch (artificial horizon)
 *   2. Heading indicator   - compass rose from IMU yaw (aircraft style: turning right increases the number),
 *                            with the commanded drive direction from the front steering angle
 *   3. Turn indicator      - yaw rate from IM10A gyro Z (deg/s), left/right
 *   4. Steering (top view) - front and rear wheel angles of the 4-wheel steering
 * Conventions: ROS yaw / gyro Z are positive-left (CCW). Steering servos: 90 = centre, higher = wheels point left.
 * Pitch is drawn as positive = nose up; confirm on the rover by lifting the front (horizon must move down).
 */
(function () {
  'use strict';
  const D2R = Math.PI / 180;
  const C = {
    sky: '#1d6fb8', sky2: '#0d3f6e', ground: '#7a4a1e', ground2: '#4a2c10', line: '#f4f7fb',
    bezel: '#0b1622', ring: 'rgba(140,190,235,.55)', amber: '#f2b33d', cyan: '#22b8f0', green: '#34e58b',
    red: '#ff4655', dim: 'rgba(220,235,250,.55)', text: '#e7f0f8'
  };
  const isNum = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));

  function prep(cv) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2), css = cv.clientWidth || 220;
    if (cv.width !== Math.round(css * dpr)) { cv.width = Math.round(css * dpr); cv.height = Math.round(css * dpr); }
    const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const s = css, cx = s / 2, cy = s / 2, R = s / 2 - 6;
    g.clearRect(0, 0, s, s);
    return { g, s, cx, cy, R };
  }
  function bezel(g, cx, cy, R) {
    g.beginPath(); g.arc(cx, cy, R + 4, 0, Math.PI * 2); g.fillStyle = C.bezel; g.fill();
    g.lineWidth = 2; g.strokeStyle = C.ring; g.stroke();
  }
  function label(g, text, x, y, size, color, align) {
    g.font = `600 ${size}px system-ui, sans-serif`; g.fillStyle = color || C.text;
    g.textAlign = align || 'center'; g.textBaseline = 'middle'; g.fillText(text, x, y);
  }
  function noData(g, cx, cy, R, what) {
    g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fillStyle = '#16212d'; g.fill();
    label(g, 'NO DATA', cx, cy - 6, 14, C.red); label(g, what, cx, cy + 12, 10, C.dim);
  }

  // 1. Attitude indicator --------------------------------------------------------------------------------------
  function attitude(cv, roll, pitch) {
    const { g, cx, cy, R } = prep(cv); bezel(g, cx, cy, R);
    if (!isNum(roll) || !isNum(pitch)) { noData(g, cx, cy, R, 'roll / pitch'); return { text: '--' }; }
    const rl = Number(roll), pt = Number(pitch), pxPerDeg = R / 30;
    g.save(); g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.clip();
    g.translate(cx, cy); g.rotate(-rl * D2R);
    const off = Math.max(-R * 1.4, Math.min(R * 1.4, pt * pxPerDeg));
    let gr = g.createLinearGradient(0, -2 * R, 0, off); gr.addColorStop(0, C.sky2); gr.addColorStop(1, C.sky);
    g.fillStyle = gr; g.fillRect(-2 * R, -3 * R, 4 * R, 3 * R + off);
    gr = g.createLinearGradient(0, off, 0, 2 * R); gr.addColorStop(0, C.ground); gr.addColorStop(1, C.ground2);
    g.fillStyle = gr; g.fillRect(-2 * R, off, 4 * R, 3 * R);
    g.strokeStyle = C.line; g.lineWidth = 2; g.beginPath(); g.moveTo(-2 * R, off); g.lineTo(2 * R, off); g.stroke();
    g.lineWidth = 1.3;                                   // pitch ladder every 5 deg
    for (let d = -30; d <= 30; d += 5) {
      if (!d) continue;
      const y = off - d * pxPerDeg, half = d % 10 ? R * 0.12 : R * 0.24;
      g.beginPath(); g.moveTo(-half, y); g.lineTo(half, y); g.stroke();
      if (!(d % 10) && R > 70) { label(g, String(Math.abs(d)), -half - 10, y, 9, C.line); label(g, String(Math.abs(d)), half + 10, y, 9, C.line); }
    }
    g.restore();
    // roll scale (fixed) and roll pointer (moves with roll)
    g.save(); g.translate(cx, cy); g.strokeStyle = C.line; g.lineWidth = 1.5;
    for (const a of [-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60]) {
      const t = (a - 90) * D2R, len = a % 30 ? 6 : 11;
      g.beginPath(); g.moveTo(Math.cos(t) * R, Math.sin(t) * R); g.lineTo(Math.cos(t) * (R - len), Math.sin(t) * (R - len)); g.stroke();
    }
    g.rotate(-rl * D2R); g.fillStyle = C.amber;
    g.beginPath(); g.moveTo(0, -R + 13); g.lineTo(-6, -R + 23); g.lineTo(6, -R + 23); g.closePath(); g.fill();
    g.restore();
    // fixed rover symbol (amber "W")
    g.strokeStyle = C.amber; g.lineWidth = 4; g.lineCap = 'round';
    g.beginPath(); g.moveTo(cx - R * 0.55, cy); g.lineTo(cx - R * 0.2, cy); g.lineTo(cx - R * 0.1, cy + R * 0.1);
    g.moveTo(cx + R * 0.55, cy); g.lineTo(cx + R * 0.2, cy); g.lineTo(cx + R * 0.1, cy + R * 0.1); g.stroke();
    g.fillStyle = C.amber; g.beginPath(); g.arc(cx, cy, 3.5, 0, Math.PI * 2); g.fill(); g.lineCap = 'butt';
    const warn = Math.abs(rl) > 15 || Math.abs(pt) > 15;
    return { text: `Roll ${rl >= 0 ? '+' : ''}${rl.toFixed(1)}° · Pitch ${pt >= 0 ? '+' : ''}${pt.toFixed(1)}°`, warn };
  }

  // 2. Heading indicator ---------------------------------------------------------------------------------------
  function heading(cv, yawDeg, frontSteer) {
    const { g, cx, cy, R } = prep(cv); bezel(g, cx, cy, R);
    if (!isNum(yawDeg)) { noData(g, cx, cy, R, 'IMU yaw'); return { text: '--' }; }
    const hdg = ((-Number(yawDeg)) % 360 + 360) % 360;        // aircraft style: right turn -> number grows
    g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fillStyle = '#0f1b28'; g.fill();
    g.save(); g.translate(cx, cy); g.rotate(-hdg * D2R);       // rotate the card, lubber line stays on top
    g.strokeStyle = C.line;
    for (let a = 0; a < 360; a += 5) {
      const t = (a - 90) * D2R, len = a % 30 === 0 ? 12 : a % 10 === 0 ? 8 : 4;
      g.lineWidth = a % 30 === 0 ? 2 : 1;
      g.beginPath(); g.moveTo(Math.cos(t) * R, Math.sin(t) * R); g.lineTo(Math.cos(t) * (R - len), Math.sin(t) * (R - len)); g.stroke();
    }
    const names = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' };
    const big = Math.max(10, R * 0.15), small = Math.max(8, R * 0.1);
    for (let a = 0; a < 360; a += (R > 80 ? 30 : 90)) {
      const t = (a - 90) * D2R, r = R - big - 8;
      g.save(); g.translate(Math.cos(t) * r, Math.sin(t) * r); g.rotate(a * D2R);
      label(g, names[a] || String(a / 10), 0, 0, names[a] ? big : small, names[a] === 'N' ? C.red : C.text); g.restore();
    }
    g.restore();
    // drive direction from the front steering (servo 90 = straight; higher = left)
    if (isNum(frontSteer)) {
      const steer = Number(frontSteer) - 90, t = (-steer - 90) * D2R;
      g.strokeStyle = C.green; g.fillStyle = C.green; g.lineWidth = 3;
      g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(t) * R * 0.62, cy + Math.sin(t) * R * 0.62); g.stroke();
      g.save(); g.translate(cx + Math.cos(t) * R * 0.66, cy + Math.sin(t) * R * 0.66); g.rotate(t + Math.PI / 2);
      g.beginPath(); g.moveTo(0, -8); g.lineTo(-6, 4); g.lineTo(6, 4); g.closePath(); g.fill(); g.restore();
    }
    // rover symbol + lubber line
    g.fillStyle = C.amber; g.beginPath(); g.moveTo(cx, cy - 14); g.lineTo(cx - 9, cy + 10); g.lineTo(cx, cy + 5); g.lineTo(cx + 9, cy + 10); g.closePath(); g.fill();
    g.beginPath(); g.moveTo(cx, cy - R + 1); g.lineTo(cx - 7, cy - R - 9 + 12); g.lineTo(cx + 7, cy - R - 9 + 12); g.closePath(); g.fill();
    const st = isNum(frontSteer) ? Number(frontSteer) - 90 : null;
    return { text: `HDG ${String(Math.round(hdg) % 360).padStart(3, '0')}°` + (st === null ? '' : ` · drive ${Math.abs(st) < 1 ? 'straight' : Math.abs(st).toFixed(0) + '° ' + (st > 0 ? 'left' : 'right')}`) };
  }

  // 3. Turn indicator ------------------------------------------------------------------------------------------
  function turn(cv, gzRadS, speed) {
    const { g, cx, cy, R } = prep(cv); bezel(g, cx, cy, R);
    if (!isNum(gzRadS)) { noData(g, cx, cy, R, 'gyro Z'); return { text: '--' }; }
    const rate = Number(gzRadS) / D2R, FULL = 45;               // deg/s, positive = left
    g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fillStyle = '#0f1b28'; g.fill();
    g.save(); g.translate(cx, cy); g.strokeStyle = C.line;
    for (const a of [-45, -30, -15, 0, 15, 30, 45]) {           // marks at 15 deg/s steps (needle tilt 1:1 up to 45)
      const t = (90 + a) * D2R; g.lineWidth = a ? 2 : 3;
      g.beginPath(); g.moveTo(Math.cos(t) * R, Math.sin(t) * R); g.lineTo(Math.cos(t) * (R - (a % 30 ? 8 : 13)), Math.sin(t) * (R - (a % 30 ? 8 : 13))); g.stroke();
    }
    label(g, 'L', -R * 0.62, -R * 0.35, Math.max(11, R * 0.16), C.text); label(g, 'R', R * 0.62, -R * 0.35, Math.max(11, R * 0.16), C.text);
    const tilt = Math.max(-FULL, Math.min(FULL, rate));
    g.rotate(-tilt * D2R);                                       // left turn tilts the symbol left
    g.strokeStyle = Math.abs(rate) > 30 ? C.red : C.amber; g.lineWidth = 4; g.lineCap = 'round';
    g.beginPath(); g.moveTo(-R * 0.6, 0); g.lineTo(R * 0.6, 0); g.stroke();
    g.fillStyle = g.strokeStyle; g.beginPath(); g.arc(0, 0, 7, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.moveTo(0, -7); g.lineTo(0, -R * 0.28); g.stroke(); g.lineCap = 'butt';
    g.restore();
    return { text: `${Math.abs(rate).toFixed(1)}°/s ${Math.abs(rate) < 0.5 ? 'straight' : rate > 0 ? 'left' : 'right'}` +
      (isNum(speed) ? ` · ${Math.abs(Number(speed)) < 0.005 ? '0' : (Number(speed) * 100).toFixed(0)} cm/s` : ''), warn: Math.abs(rate) > 30 };
  }

  // 4. Steering top view ---------------------------------------------------------------------------------------
  function steering(cv, frontSteer, rearSteer) {
    const { g, s, cx, cy, R } = prep(cv); bezel(g, cx, cy, R);
    if (!isNum(frontSteer) && !isNum(rearSteer)) { noData(g, cx, cy, R, 'steering servos'); return { text: '--' }; }
    g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fillStyle = '#0f1b28'; g.fill();
    const bw = R * 0.5, bl = R * 1.05;                            // body
    g.fillStyle = 'rgba(120,170,215,.18)'; g.strokeStyle = C.ring; g.lineWidth = 2;
    g.beginPath(); g.rect(cx - bw / 2, cy - bl / 2, bw, bl); g.fill(); g.stroke();
    g.fillStyle = C.amber; g.beginPath(); g.moveTo(cx, cy - bl / 2 - 10); g.lineTo(cx - 7, cy - bl / 2 - 1); g.lineTo(cx + 7, cy - bl / 2 - 1); g.closePath(); g.fill();
    const wheel = (x, y, deg, color) => {
      g.save(); g.translate(x, y); g.rotate(-deg * D2R); g.fillStyle = color;
      g.fillRect(-R * 0.06, -R * 0.15, R * 0.12, R * 0.3); g.restore();
    };
    const f = isNum(frontSteer) ? Number(frontSteer) - 90 : null, r = isNum(rearSteer) ? Number(rearSteer) - 90 : null;
    const fy = cy - bl / 2 + R * 0.17, ry = cy + bl / 2 - R * 0.17, wx = bw / 2 + R * 0.11;
    if (f !== null) { wheel(cx - wx, fy, f, C.green); wheel(cx + wx, fy, f, C.green); }
    if (r !== null) { wheel(cx - wx, ry, r, C.cyan); wheel(cx + wx, ry, r, C.cyan); }
    const txt = v => v === null ? '--' : `${Math.abs(v).toFixed(0)}° ${Math.abs(v) < 1 ? '' : v > 0 ? 'L' : 'R'}`;
    const mode = f === null || r === null || (Math.abs(f) < 1 && Math.abs(r) < 1) ? 'straight'
      : Math.sign(f) === -Math.sign(r) ? '4WS turn' : 'crab';
    void s;
    return { text: `Front ${txt(f)} · Rear ${txt(r)} · ${mode}` };
  }

  function draw(r, val) {
    const box = document.getElementById('flightInstruments');
    if (!box || !r) return;
    const full = val(r, 'imu_full', {}) || {}, odom = val(r, 'odom', {}) || {};
    const q = id => box.querySelector(`[data-fi="${id}"]`);
    const out = {
      attitude: attitude(q('attitude'), val(r, 'imu_roll'), val(r, 'imu_pitch')),
      heading: heading(q('heading'), val(r, 'imu_yaw'), val(r, 'front_steer')),
      turn: turn(q('turn'), full.gz, odom.vx),
      steering: steering(q('steering'), val(r, 'front_steer'), val(r, 'rear_steer'))
    };
    for (const [k, v] of Object.entries(out)) {
      const e = box.querySelector(`[data-fv="${k}"]`);
      if (e && v) { e.textContent = v.text; e.classList.toggle('warn', !!v.warn); }
    }
  }

  const HTML = `<div id="flightInstruments" class="fiGrid">
    <figure><canvas data-fi="attitude" aria-label="Attitude indicator: roll and pitch"></canvas><div class="fiVal" data-fv="attitude">--</div><figcaption>ATTITUDE · roll / pitch</figcaption></figure>
    <figure><canvas data-fi="heading" aria-label="Heading indicator with drive direction"></canvas><div class="fiVal" data-fv="heading">--</div><figcaption>HEADING · <span style="color:#34e58b">drive direction</span></figcaption></figure>
    <figure><canvas data-fi="turn" aria-label="Turn rate indicator"></canvas><div class="fiVal" data-fv="turn">--</div><figcaption>TURN RATE · gyro Z</figcaption></figure>
    <figure><canvas data-fi="steering" aria-label="Steering angles, top view"></canvas><div class="fiVal" data-fv="steering">--</div><figcaption>STEERING · 4WS top view</figcaption></figure>
  </div>`;
  window.AtlasFlightInstruments = { HTML, draw };
})();
