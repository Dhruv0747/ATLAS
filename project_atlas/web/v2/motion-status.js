/* ATLAS Glass UI V2 motion chip classification. Display only: it never authorizes motion and
 * changes no control, E-STOP, command-gating or encoder-consensus behavior.
 *
 * Why this exists (Stage 25, 2026-10-15): the chip used to say "Stopped - Odometry reports zero
 * speed" from /odom velocity alone. When three-of-four encoder consensus fails closed (encoder
 * faults), /odom stays at zero while the wheels are visibly counting, so the chip showed Stopped
 * on a moving rover. Fresh per-wheel count evidence now overrides a zero odometry reading.
 * It can only turn "Stopped" into a warning; it never turns a Moving reading into Stopped. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AtlasMotion = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const ODOM_FRESH_S = 2;       // same freshness bound the chip always used for /odom
  const HEALTH_FRESH_S = 3;     // matches the dashboard's recent(...,3) test for encoder_health
  const COUNT_WINDOW_S = 0.6;   // a wheel that counted this recently is turning (or being pushed)
  const MIN_WHEELS = 2;         // one flickering channel at rest must not raise the warning

  function parseHealth(r) {
    const h = r && r.encoder_health;
    if (!h || !(h.age < HEALTH_FRESH_S) || typeof h.value !== 'string') return null;
    try { return JSON.parse(h.value); } catch (e) { return null; }
  }

  // Number of wheels whose raw count changed within COUNT_WINDOW_S; 0 when the evidence is not fresh.
  function wheelsCounting(r) {
    const h = parseHealth(r);
    if (!h || h.packet_fresh !== true || !Array.isArray(h.last_change_age_s)) return 0;
    return h.last_change_age_s.filter(a => Number.isFinite(Number(a)) && Number(a) >= 0 && Number(a) < COUNT_WINDOW_S).length;
  }

  // d: the latest /api/status object, or null when the link is stale. Returns [text, tone, title].
  function classify(d) {
    const r = d && d.ros, o = r && r.odom;
    if (!d) return ['Motion unknown', 'fail', 'No fresh status from ATLAS. Rover state unknown.'];
    if (!o || !(o.age < ODOM_FRESH_S) || !o.value) return ['Motion unknown', 'warn', 'Odometry is not fresh.'];
    const vx = Math.abs(Number(o.value.vx) || 0), wz = Math.abs(Number(o.value.wz) || 0);
    if (vx > 0.01 || wz > 0.02) return ['Moving', 'info', `vx ${vx.toFixed(2)} m/s · turn ${wz.toFixed(2)} rad/s`];
    const n = wheelsCounting(r);
    if (n >= MIN_WHEELS) {
      return ['Moving · odometry not tracking', 'warn',
        `${n} wheels counted in the last ${COUNT_WINDOW_S} s but odometry reports zero speed. ` +
        'Encoder consensus is probably failing closed; do not trust the position until the encoders are checked.'];
    }
    return ['Stopped', 'ok', 'Odometry reports zero speed.'];
  }

  return { classify, wheelsCounting, COUNT_WINDOW_S, MIN_WHEELS };
});
