"""Stage32 A5 tool (PREPARED, NOT RUN without owner approval): IR checkerboard capture for depth-camera intrinsics.

How it respects the existing safety model:
  * It is the viewing page: one headless Chromium page on the Vision Lab, with a 60-s heartbeat pre-check before Start
    (as in stage32_ir_acceptance.py). Raw IR frames are fetched by THAT page (page.evaluate fetch), so no second client
    keeps the 4-s viewer lease alive; if the page stalls, the camera stops exactly as designed.
  * ONE IR-only Start per run (max 60 s, the runtime's own limit). No mode change, emitter change, recording or retry.
  * Images are never written to disk. Each frame is despeckled, searched for the checkerboard and discarded; only corner
    coordinates (CornerSet.views) and counts are kept.
Afterwards: calibrate() -> CANDIDATE (or REJECTED) document for the 640x480 IR camera; derive_resolution() -> 160x120
depth candidate. Neither is validated or installed by this tool.

usage: python3 stage32_ir_checkerboard_capture.py OUT_PREFIX --cols 9 --rows 6 --square-mm <MEASURED> [--every 1.0]
--square-mm is the owner's MEASURED square size of the physical print (9 squares across / 9), never the design value.
Printed targets: A4 landscape 25 mm design (250 x 175 mm pattern) or A3 landscape 35 mm design (350 x 245 mm).
"""
import argparse, asyncio, base64, json, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import checkerboard_calibration as CB   # noqa: E402

BASE = 'http://192.168.1.15:8088'
SERIAL = '17122120830'
FETCH_RAW = '''async () => { const r = await fetch('/api/vision3d/raw?kind=ir', { cache: 'no-store' }); if (!r.ok) return null;
  const b = new Uint8Array(await r.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode.apply(null, b.subarray(i, i + 32768));
  return { w: +r.headers.get('X-Width'), h: +r.headers.get('X-Height'), enc: r.headers.get('X-Encoding'), step: +r.headers.get('X-Step'),
           stamp: r.headers.get('X-Source-Stamp'), b64: btoa(s) }; }'''


DESIGN_SQUARES_MM = (25.0, 35.0)   # the two generated targets (make_checkerboard_pdf.py); used only for a plausibility check


def check_square(square_mm):
    """Refuse impossible values; warn when the measurement is not near either printed design (wrong target or scaled print)."""
    if not 5.0 <= square_mm <= 100.0:
        raise ValueError('square size %.2f mm is not a plausible measured value' % square_mm)
    near = [d for d in DESIGN_SQUARES_MM if abs(square_mm - d) / d <= 0.03]
    return None if near else ('measured %.2f mm is more than 3%% from both printed designs (25 / 35 mm): check the print scale '
                              '(Actual size) and that the measurement spans 9 squares' % square_mm)


def frame_to_gray(meta):
    """Native mono8 IR bytes -> numpy (h, w) uint8. Anything else is refused (no conversion from other streams)."""
    import numpy as np
    if not meta or meta.get('enc') != 'mono8':
        raise ValueError('expected native mono8 IR')
    raw = base64.b64decode(meta['b64'])
    w, h, step = meta['w'], meta['h'], meta['step']
    if step < w or len(raw) != step * h:
        raise ValueError('IR frame size mismatch')
    return np.frombuffer(raw, np.uint8).reshape(h, step)[:, :w].copy()


def process(corner_set, meta, last_stamp, despeckle=5):
    """Returns (accepted: bool|None, stamp). None = same frame as before (not counted)."""
    if meta['stamp'] == last_stamp:
        return None, last_stamp
    gray = frame_to_gray(meta)
    ok = corner_set.add(gray, despeckle=despeckle)
    del gray   # image discarded immediately; only corners stay in corner_set
    return ok, meta['stamp']


def merge_views(corner_set, previous):
    import numpy as np
    if tuple(previous['pattern']) != corner_set.pattern:
        raise ValueError('pattern differs from the earlier session')
    for v in previous['views']:
        arr = np.array(v, np.float32); corner_set.views.append(arr)
        for x, y in arr:
            corner_set.cells.add((min(CB.COVERAGE_GRID - 1, int(x / 640 * CB.COVERAGE_GRID)), min(CB.COVERAGE_GRID - 1, int(y / 480 * CB.COVERAGE_GRID))))


def summarize(corner_set, square_m, prefix):
    doc = None
    try:
        doc = CB.calibrate(corner_set, square_m, SERIAL, 'astra_ir_optical_frame')
    except ValueError as e:
        doc = {'status': 'NOT ENOUGH DATA', 'reason': str(e)}
    out = {'corners_only': True, 'pattern': list(corner_set.pattern), 'square_m': square_m, 'accepted_views': len(corner_set.views),
           'rejected_frames': corner_set.rejected, 'coverage': corner_set.coverage(), 'ir_candidate': doc,
           'views': [v.tolist() for v in corner_set.views]}
    if doc.get('status') == 'CANDIDATE':
        out['depth_candidate_160x120'] = CB.derive_resolution(doc, 160, 120, 'astra_depth_optical_frame')
        out['note'] = ('depth_candidate assumes zero IR-to-depth pixel offset; the offset must be measured (needs a working '
                       'IR+Depth mode) before physical validation and installation.')
    Path(prefix + '_calibration_candidate.json').write_text(json.dumps(out, indent=1))
    return out


async def run(a):
    from playwright.async_api import async_playwright
    import stage32_ir_acceptance as ACC   # same passive observer / heartbeat statistics
    cs = CB.CornerSet((a.cols, a.rows), 640, 480); log = []
    if a.merge:   # combine corner sets from earlier approved sessions (each session is limited to 60 s)
        merge_views(cs, json.loads(Path(a.merge).read_text()))
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={'width': 1440, 'height': 900})
        await ctx.add_init_script(ACC.OBSERVER); pg = await ctx.new_page()
        await pg.goto(a.base + '/v2/vision3d'); await pg.wait_for_timeout(60000)
        pre = await pg.evaluate(ACC.STATS, 0)
        if not (pre['visibility'] == 'visible' and pre['gap_max_ms'] and pre['gap_max_ms'] <= 1500 and pre['drift_span_ms'] is not None and pre['drift_span_ms'] <= 1300):
            print(json.dumps({'precheck': pre, 'result': 'PRECHECK FAILED: Start not clicked'})); await b.close(); return
        await pg.click('#vlModes label[data-mode="ir"]'); await pg.click('#startViewer'); t0 = time.time(); last = None; seen_active = False
        while time.time() - t0 < 75:
            await pg.wait_for_timeout(int(a.every * 1000)); row = await pg.evaluate(ACC.DOM); st = (row.get('rt') or {}).get('state')
            seen_active = seen_active or st == 'ACTIVE'
            if seen_active and st not in ('ACTIVE', None): break
            if row.get('ir') and row['ir']['state'] == 'ACTIVE':
                meta = await pg.evaluate(FETCH_RAW)
                if meta:
                    ok, last = process(cs, meta, last)
                    if ok is not None:
                        log.append({'t': round(time.time() - t0, 1), 'accepted': ok, 'views': len(cs.views), 'coverage': round(cs.coverage(), 2)})
                        print('t=%5.1f board %s  views=%d coverage=%.2f' % (log[-1]['t'], 'FOUND' if ok else '-', len(cs.views), cs.coverage()), flush=True)
        await pg.click('#pause'); await pg.wait_for_timeout(2000); await b.close()
    out = summarize(cs, a.square_mm / 1000.0, a.out)
    print(json.dumps({k: v for k, v in out.items() if k != 'views'}, indent=1, default=str))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('--cols', type=int, default=9); ap.add_argument('--rows', type=int, default=6)
    ap.add_argument('--square-mm', type=float, required=True); ap.add_argument('--every', type=float, default=1.0); ap.add_argument('--base', default=BASE); ap.add_argument('--merge')
    a = ap.parse_args(); warn = check_square(a.square_mm)
    if warn:
        print('WARNING:', warn)
    asyncio.run(run(a))
