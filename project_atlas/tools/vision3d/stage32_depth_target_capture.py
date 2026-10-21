"""Stage32 A5 tool (PREPARED, NOT RUN without owner approval): depth samples of ONE owner-measured flat target.

One Depth-only Vision Lab session (max 60 s) through a heartbeat-checked viewing page, exactly like the IR acceptance.
The page itself asks the existing read-only pixel route for a fixed grid inside a central region (no images are fetched
or stored: each answer is one scalar depth for one pixel of the frame the page is displaying). Output per run:
  {reference_m (owner tape, Astra front face), samples [[u, v, z_m|None], ...], depth_statistics summary}
Afterwards `validate(candidate, runs)` back-projects the samples with the CANDIDATE intrinsics (offline), fits the plane,
and calls attach_validation(front_face_reference=True). Nothing is installed; the result is reviewed first.

usage: python3 stage32_depth_target_capture.py OUT_PREFIX --reference-m 1.004 [--grid 9] [--roi 0.3]
"""
import argparse, asyncio, json, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / 'scripts'))
import checkerboard_calibration as CB   # noqa: E402

BASE = 'http://192.168.1.15:8088'
W, H = 160, 120
SAMPLE = '''async (pts) => { const img = document.getElementById('depthImage'); if (!img.getAttribute('src')) return null;
  // the page keeps the stamp of the depth frame it displays; pixel answers must refer to that exact frame
  const stamp = window.__atlasDepthStamp || null; if (!stamp) return null; const out = [];
  for (const [u, v] of pts) { const r = await fetch(`/api/vision3d/pixel?u=${u}&v=${v}&stamp=${encodeURIComponent(stamp)}`, { cache: 'no-store' });
    if (!r.ok) { out.push([u, v, null]); continue; } const m = await r.json(); out.push([u, v, m.valid ? m.depth_z_m : null]); }
  return { stamp, out }; }'''
# vision3d.js keeps imageStamps in a closure; this init script mirrors the displayed frame's stamp from the response header
STAMP_TAP = '''(() => { const orig = window.fetch.bind(window); window.fetch = async (u, o) => { const r = await orig(u, o);
  if (String(u).includes('/api/vision3d/frame?kind=depth') && r.ok) window.__atlasDepthStamp = r.headers.get('X-Source-Stamp'); return r; }; })()'''


def grid(n=9, roi=0.3):
    """n x n pixels spread over the central `roi` fraction of the 160x120 depth image."""
    x0, x1 = W * (0.5 - roi / 2), W * (0.5 + roi / 2); y0, y1 = H * (0.5 - roi / 2), H * (0.5 + roi / 2)
    return [[int(round(x0 + (x1 - x0) * i / (n - 1))), int(round(y0 + (y1 - y0) * j / (n - 1)))] for j in range(n) for i in range(n)]


def summarize(samples, reference_m):
    z = [s[2] for s in samples if s[2] is not None and 0 < s[2] < 8]
    if not z:
        raise ValueError('no valid depth in the target region')
    med = statistics.median(z)
    return {'reference_m': reference_m, 'samples': len(samples), 'valid': len(z), 'median_m': med, 'signed_error_m': med - reference_m,
            'median_absolute_error_m': statistics.median(abs(v - reference_m) for v in z), 'iqr_m': (statistics.quantiles(z, n=4)[2] - statistics.quantiles(z, n=4)[0]) if len(z) >= 4 else None,
            'invalid_percent': 100.0 * (len(samples) - len(z)) / len(samples)}


def validate(candidate, runs):
    """candidate: 160x120 depth CANDIDATE doc; runs: [{'summary':..., 'samples': [...]}]. Offline only."""
    import atlas_vision3d_geometry as G
    distance_tests, plane_tests = [], []
    for r in runs:
        s = r['summary']; distance_tests.append({'reference_m': s['reference_m'], 'median_m': s['median_m'], 'invalid_percent': s['invalid_percent']})
        pts = []
        for u, v, z in r['samples']:
            if z is None:
                continue
            x, y = G.undistort(u, v, candidate['k'], candidate['d']); pts.append([x * z, y * z, z])
        if len(pts) >= 20:
            f = G.plane_fit(pts); plane_tests.append({'rms_m': f['rms_m'], 'distance_m': f['distance_m'], 'reference_m': s['reference_m'],
                                                      'tilt_deg': f['tilt_from_optical_axis_deg']})
    return CB.attach_validation(candidate, distance_tests, plane_tests, front_face_reference=len({round(t['reference_m'], 2) for t in distance_tests}) >= 3)


async def run(a):
    from playwright.async_api import async_playwright
    import stage32_ir_acceptance as ACC
    pts = grid(a.grid, a.roi); samples = []
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        await ctx.add_init_script(ACC.OBSERVER); await ctx.add_init_script(STAMP_TAP); pg = await ctx.new_page()
        await pg.goto(a.base + '/v2/vision3d'); await pg.wait_for_timeout(60000)
        pre = await pg.evaluate(ACC.STATS, 0)
        if not (pre['visibility'] == 'visible' and pre['gap_max_ms'] and pre['gap_max_ms'] <= 1500 and pre['drift_span_ms'] is not None and pre['drift_span_ms'] <= 1300):
            print(json.dumps({'precheck': pre, 'result': 'PRECHECK FAILED: Start not clicked'})); await b.close(); return
        await pg.click('#vlModes label[data-mode="depth"]'); await pg.click('#startViewer'); t0 = time.time(); seen_active = False
        while time.time() - t0 < 75:
            await pg.wait_for_timeout(1000); row = await pg.evaluate(ACC.DOM); st = (row.get('rt') or {}).get('state')
            seen_active = seen_active or st == 'ACTIVE'
            if seen_active and st not in ('ACTIVE', None): break
            got = await pg.evaluate(SAMPLE, pts)
            if got: samples.extend(got['out'])
        await pg.click('#pause'); await pg.wait_for_timeout(2000); await b.close()
    out = {'reference_m': a.reference_m, 'grid': a.grid, 'roi': a.roi, 'samples': samples, 'summary': summarize(samples, a.reference_m), 'images_kept': False}
    Path(a.out + '_depth_target.json').write_text(json.dumps(out)); print(json.dumps(out['summary'], indent=1))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('--reference-m', type=float, required=True)
    ap.add_argument('--grid', type=int, default=9); ap.add_argument('--roi', type=float, default=0.3); ap.add_argument('--base', default=BASE)
    asyncio.run(run(ap.parse_args()))
