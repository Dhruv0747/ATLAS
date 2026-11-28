// Executed by tests/test_vision3d_stage32_preview.py under Node; prints JSON only.
const S = require('../web/v2/vision3d_state.js');
function frame(w, h, fn, enc, be) {
  const bpp = enc === '16UC1' ? 2 : 4, buf = new ArrayBuffer(w * h * bpp), dv = new DataView(buf);
  for (let v = 0; v < h; v++) for (let u = 0; u < w; u++) { const z = fn(u, v); if (bpp === 2) dv.setUint16((v * w + u) * 2, z, !be); else dv.setFloat32((v * w + u) * 4, z, !be); }
  return { buf, hdr: { 'X-Width': String(w), 'X-Height': String(h), 'X-Encoding': enc, 'X-Step': String(w * bpp), 'X-Bigendian': be ? '1' : '0' } };
}
const out = {};
let f = frame(160, 120, (u, v) => (u === 0 ? 0 : 2000), '16UC1', false);
let p = S.previewPoints(f.buf, f.hdr, 6000);
const xs = p.points.map(q => q[0]), zs = p.points.map(q => q[2]);
out.wall = { n: p.points.length, stride: p.stride, invalid: p.invalid, zmin: Math.min(...zs), zmax: Math.max(...zs), xmin: Math.min(...xs), xmax: Math.max(...xs), calibrated: p.calibrated, label: p.label, k: p.k };
f = frame(160, 120, (u, v) => 1.5, '32FC1', true); p = S.previewPoints(f.buf, f.hdr, 6000); out.float_be = { n: p.points.length, z: p.points[0][2] };
f = frame(4, 2, () => 65535, '16UC1', false); p = S.previewPoints(f.buf, f.hdr, 6000); out.allinvalid = { n: p.points.length, invalid: p.invalid };
out.errors = [];
for (const [b, h] of [[new ArrayBuffer(8), { 'X-Width': '2', 'X-Height': '2', 'X-Encoding': 'mono8', 'X-Step': '2' }],
                      [new ArrayBuffer(7), { 'X-Width': '2', 'X-Height': '2', 'X-Encoding': '16UC1', 'X-Step': '4' }]]) {
  try { S.previewPoints(b, h, 6000); out.errors.push('accepted'); } catch (e) { out.errors.push(e.message); }
}
f = frame(640, 480, () => 3000, '16UC1', false); p = S.previewPoints(f.buf, f.hdr, 99999); out.cap = { n: p.points.length };
console.log(JSON.stringify(out));
