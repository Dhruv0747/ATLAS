#!/usr/bin/env python3
"""Live adapter for the Stage32 guided Astra calibration (owner-attended, rover stationary).

Uses ONLY the existing bounded viewer (POST /api/vision3d/viewer start/stop, which runs the stationary admission
guard) and its read-only raw IR/depth routes on 127.0.0.1:8088. No camera driver, ROS, servo or motor access.
Images are never written: capture keeps checkerboard CORNER COORDINATES only; validation keeps scalar statistics.

  capture   IR sessions; owner shows the printed board in varied poses. Then checkerboard_calibration.calibrate()
            -> 640x480 IR candidate -> derive_resolution() -> 160x120 depth candidate (status CANDIDATE).
  measure   One owner-measured flat target distance: depth_statistics + plane_fit using the candidate intrinsics.
  finalize  attach_validation(). Writes depth_160x120.validated-candidate.json only if every limit passes.
  install   Separate owner-approved step: copies the validated document to config/astra_calibration/depth_160x120.json.

State: ~/.local/share/atlas/calibration/ (private). Nothing becomes active until `install`.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / 'scripts'))
import checkerboard_calibration as CB      # noqa: E402
import calibration_validation as CV        # noqa: E402

API = 'http://127.0.0.1:8088/api/vision3d/'
STATE = Path.home() / '.local/share/atlas/calibration'
CAL_DIR = ROOT / 'config/astra_calibration'
IR_FRAME, DEPTH_FRAME = 'astra_ir_optical_frame', 'astra_depth_optical_frame'
DEPTH_W, DEPTH_H = 160, 120
SESSION_S = 50          # viewer sessions are capped at 60 s including startup


def say(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def serial():
    m = json.loads((ROOT / 'config/vision3d_live.json').read_text())
    s = m.get('device_serial') or (m.get('identity') or {}).get('device_serial')
    if not s: raise SystemExit('device serial missing from vision3d_live.json')
    return s


def viewer(action, mode=None):
    if action != 'stop':
        import subprocess
        if subprocess.run(['systemctl', '--user', 'is-active', 'atlas-foxglove'], capture_output=True, text=True).stdout.strip() != 'active':
            raise SystemExit('atlas-foxglove (camera frame bridge) is off. Start it first: systemctl --user start atlas-foxglove')
    body = json.dumps({'action': 'stop'} if action == 'stop' else {'action': 'start', 'mode': mode}).encode()
    req = urllib.request.Request(API + 'viewer', data=body, method='POST', headers={
        'Content-Type': 'application/json', 'X-Atlas-Vision3D': '1', 'Origin': 'http://127.0.0.1:8088'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b'{}') | {'http': e.code}


def state():
    with urllib.request.urlopen(API + 'status', timeout=3) as r: return json.loads(r.read())['runtime']['state']


def wait_active(timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = state()
        if s == 'ACTIVE': return True
        if s not in ('CHECKING', 'STARTING', 'OFF'): raise SystemExit('viewer refused: ' + s + ' (rover must be stationary, E-STOP latched, CPU<75%)')
        time.sleep(1)
    raise SystemExit('viewer did not become ACTIVE')


def raw(kind):
    with urllib.request.urlopen(API + 'raw?kind=' + kind, timeout=3) as r:
        h = {k.lower(): v for k, v in r.headers.items()}
        return r.read(), int(h['x-width']), int(h['x-height']), h['x-encoding'], int(h['x-step']), h['x-frame']


def ir_gray(data, w, h, enc, step):
    import numpy as np
    if enc == 'mono8':
        a = np.frombuffer(data, np.uint8).reshape(h, step)[:, :w].astype(np.float32)
    elif enc in ('mono16', '16UC1'):
        a = np.frombuffer(data, '<u2').reshape(h, step // 2)[:, :w].astype(np.float32)
    else:
        raise ValueError('unexpected IR encoding ' + enc)
    # Live Astra IR is dark (mean ~25/255 indoors): linear contrast stretch for corner finding only (never stored).
    lo, hi = np.percentile(a, 1), np.percentile(a, 99.5)
    a = np.clip((a - lo) * (255.0 / max(hi - lo, 1.0)), 0, 255)
    return np.ascontiguousarray(a, dtype=np.uint8)


def add_sb(cs, gray, pattern):
    """CornerSet.add equivalent using findChessboardCornersSB; same view/coverage bookkeeping."""
    import cv2
    import numpy as np
    found, corners = cv2.findChessboardCornersSB(gray, pattern, cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not found:
        cs.rejected += 1
        return False
    pts = corners.reshape(-1, 2).astype(np.float32)
    if pts.shape[0] != pattern[0] * pattern[1]:
        cs.rejected += 1
        return False
    cs.views.append(pts)
    for x, y in pts:
        cs.cells.add((min(CB.COVERAGE_GRID - 1, int(x / cs.size[0] * CB.COVERAGE_GRID)),
                      min(CB.COVERAGE_GRID - 1, int(y / cs.size[1] * CB.COVERAGE_GRID))))
    return True


def capture(a):
    import numpy as np, cv2
    os.nice(10)   # stay below the camera session's CPU guard
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    pattern = tuple(int(x) for x in a.pattern.lower().split('x'))
    cs, frame_id, size = None, None, None
    last_accept, last_hint, deadline = 0.0, 0.0, time.monotonic() + a.minutes * 60
    say('Hold the board still in each pose for ~1 s, then move it. Need %d distinct views.' % a.views)
    try:
        while len(cs.views if cs else []) < a.views and time.monotonic() < deadline:
            # 'ir'-only mode publishes no IR frames to the web service (observed 2026-11-05); rgb_ir does (640x480 mono8).
            viewer('stop'); time.sleep(1); viewer('start', 'rgb_ir'); wait_active()
            session_end = time.monotonic() + SESSION_S
            say('IR session live. Show the board now.')
            while time.monotonic() < session_end and len(cs.views if cs else []) < a.views:
                try: data, w, h, enc, step, fr = raw('ir')
                except Exception: time.sleep(.3); continue
                if cs is None:
                    cs, frame_id, size = CB.CornerSet(pattern, w, h), fr, (w, h)
                    say('IR stream %dx%d %s frame=%s' % (w, h, enc, fr))
                if (w, h) != size or fr != frame_id: raise SystemExit('IR resolution/frame changed mid-capture')
                g = ir_gray(data, w, h, enc, step)
                before = len(cs.views)
                # Cheap half-size FAST_CHECK first: a full-resolution search with no board in view costs enough CPU to
                # trip the camera's 75 % resource guard (observed 76.5 % on 2026-11-05, sessions stopped after ~5 s).
                # 2026-11-06: on this Astra's IR image the classic detector found the board in 0/15 frames while
                # OpenCV's sector-based detector (findChessboardCornersSB, sub-pixel accurate) found it in 12/15.
                # Cheap half-size SB pre-check first (CPU guard), then full-size SB corners. Quality gates in
                # checkerboard_calibration.calibrate() are unchanged.
                small = cv2.resize(g, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
                likely, _ = cv2.findChessboardCornersSB(small, pattern, cv2.CALIB_CB_NORMALIZE_IMAGE)
                if likely and time.monotonic() - last_accept >= 1.2 and add_sb(cs, g, pattern):
                    new = cs.views[-1]
                    if before and min(float(np.mean(np.linalg.norm(new - v, axis=1))) for v in cs.views[:-1]) < a.min_shift_px:
                        cs.views.pop()          # too similar to an earlier pose; corners only, nothing else kept
                    else:
                        last_accept = time.monotonic()
                        say('accepted view %d/%d  coverage %.0f%%' % (len(cs.views), a.views, 100 * cs.coverage()))
                elif not likely and time.monotonic() - last_hint > 8:
                    last_hint = time.monotonic(); say('...no board seen yet (IR brightness %.0f)' % float(g.mean()))
                time.sleep(.8)
    finally:
        viewer('stop')
    if not cs or len(cs.views) < CB.MIN_VIEWS + CB.MIN_HOLDOUT:
        raise SystemExit('only %d views; need >= %d. Run capture again.' % (len(cs.views) if cs else 0, CB.MIN_VIEWS + CB.MIN_HOLDOUT))
    (STATE / 'corners.json').write_text(json.dumps({'pattern': list(pattern), 'size': list(size), 'frame_id': frame_id,
                                                    'views': [v.tolist() for v in cs.views]}))
    doc = CB.calibrate(cs, a.square_mm / 1000.0, serial(), frame_id)
    q = doc.get('quality', {})
    say('IR calibration: status=%s train_rms=%.3f px holdout_rms=%.3f px coverage=%.0f%% problems=%s' % (
        doc['status'], q.get('train_rms_px', float('nan')), q.get('holdout_rms_px', float('nan')),
        100 * q.get('coverage', 0), doc.get('problems')))
    (STATE / 'ir_candidate.json').write_text(json.dumps(doc, indent=2))
    if doc['status'] != 'CANDIDATE': raise SystemExit('calibration rejected; recapture with more varied/tilted poses')
    dep = CB.derive_resolution(doc, DEPTH_W, DEPTH_H, DEPTH_FRAME)
    (STATE / 'depth_candidate.json').write_text(json.dumps(dep, indent=2))
    (STATE / 'measurements.json').unlink(missing_ok=True)
    say('Depth candidate saved (NOT active). Next: measure at >= 2 distances.')


def measure(a):
    import numpy as np, cv2
    import atlas_vision3d_geometry as G
    dep = json.loads((STATE / 'depth_candidate.json').read_text())
    frames = []
    try:
        viewer('stop'); time.sleep(1); viewer('start', 'depth'); wait_active()
        end = time.monotonic() + 20
        while len(frames) < a.frames and time.monotonic() < end:
            data, w, h, enc, step, fr = raw('depth')
            if (w, h, fr) != (DEPTH_W, DEPTH_H, DEPTH_FRAME): raise SystemExit('depth stream %dx%d %s does not match candidate' % (w, h, fr))
            if enc != '16UC1': raise SystemExit('expected 16UC1 depth in millimetres, got ' + enc)
            frames.append(np.frombuffer(data, '<u2').reshape(h, step // 2)[:, :w].astype(float))
            time.sleep(.4)
    finally:
        viewer('stop')
    cx, cy, hw, hh = DEPTH_W // 2, DEPTH_H // 2, a.roi_w // 2, a.roi_h // 2
    roi = (cx - hw, cy - hh, cx + hw, cy + hh)
    stats = CV.depth_statistics([f.tolist() for f in frames], a.distance_m, 0.001, roi)
    k = np.array(dep['k'], float).reshape(3, 3); d = np.array(dep['d'], float)
    pts = []
    med = np.median(np.stack(frames), axis=0)
    uv = np.array([[u, v] for v in range(roi[1], roi[3]) for u in range(roi[0], roi[2])], np.float32).reshape(-1, 1, 2)
    xy = cv2.undistortPoints(uv, k, d).reshape(-1, 2)
    for (x, y), (u, v) in zip(xy, uv.reshape(-1, 2).astype(int)):
        z = med[v, u] * 0.001
        if z > 0 and math.isfinite(z): pts.append([x * z, y * z, z])
    plane = G.plane_fit(pts)
    rec = {'reference_m': a.distance_m, 'median_m': stats['median_m'], 'invalid_percent': stats['invalid_percent'],
           'plane_rms_m': plane['rms_m'], 'plane_distance_m': plane['distance_m'], 'tilt_deg': plane['tilt_from_optical_axis_deg'],
           'frames': stats['frames'], 'roi': list(roi)}
    m = json.loads((STATE / 'measurements.json').read_text()) if (STATE / 'measurements.json').exists() else []
    m = [x for x in m if round(x['reference_m'], 3) != round(a.distance_m, 3)] + [rec]
    (STATE / 'measurements.json').write_text(json.dumps(m, indent=2))
    lim = CB.distance_limit_m(a.distance_m)
    say('at %.3f m: depth median %.3f m (error %+.1f mm, limit +/-%.1f mm), invalid %.1f%%, plane RMS %.1f mm, tilt %.1f deg' % (
        a.distance_m, stats['median_m'], 1000 * (stats['median_m'] - a.distance_m), 1000 * lim, stats['invalid_percent'],
        1000 * plane['rms_m'], plane['tilt_from_optical_axis_deg']))
    if plane['tilt_from_optical_axis_deg'] > 10: say('WARNING: target tilted >10 deg; face it straight at the camera and re-measure.')


def finalize(a):
    dep = json.loads((STATE / 'depth_candidate.json').read_text())
    m = json.loads((STATE / 'measurements.json').read_text())
    dist = [{'reference_m': x['reference_m'], 'median_m': x['median_m'], 'invalid_percent': x['invalid_percent']} for x in m]
    plane = [{'rms_m': x['plane_rms_m'], 'distance_m': x['plane_distance_m'], 'reference_m': x['reference_m']} for x in m]
    out = CB.attach_validation(dep, dist, plane)
    for r in out['validation_results']:
        say('%-14s ref %.3f m  %s' % (r['kind'], r['reference_m'], 'PASS' if r['pass'] else 'FAIL'))
    say('RESULT:', out['status'])
    if out['status'] != 'VALIDATED': raise SystemExit('not validated; nothing written for installation')
    CV.validate_calibration(out, serial(), DEPTH_W, DEPTH_H, DEPTH_FRAME)
    (STATE / 'depth_160x120.validated-candidate.json').write_text(json.dumps(out, indent=2))
    say('Validated document ready (NOT active). Owner approval needed for: install')


def install(a):
    src = STATE / 'depth_160x120.validated-candidate.json'
    doc = json.loads(src.read_text())
    CV.validate_calibration(doc, serial(), DEPTH_W, DEPTH_H, DEPTH_FRAME)
    CAL_DIR.mkdir(exist_ok=True)
    dst = CAL_DIR / 'depth_160x120.json'
    if dst.exists(): dst.rename(dst.with_name('depth_160x120.before-%s.json' % time.strftime('%Y%m%d-%H%M%S')))
    tmp = dst.with_suffix('.tmp'); tmp.write_text(json.dumps(doc, indent=2)); os.chmod(tmp, 0o644); tmp.rename(dst)
    say('Installed', dst)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='cmd', required=True)
    c = s.add_parser('capture'); c.add_argument('--square-mm', type=float, required=True); c.add_argument('--pattern', default='9x6')
    c.add_argument('--views', type=int, default=22); c.add_argument('--minutes', type=float, default=6); c.add_argument('--min-shift-px', type=float, default=25)
    m = s.add_parser('measure'); m.add_argument('--distance-m', type=float, required=True); m.add_argument('--frames', type=int, default=12)
    m.add_argument('--roi-w', type=int, default=40); m.add_argument('--roi-h', type=int, default=30)
    s.add_parser('finalize'); s.add_parser('install')
    a = p.parse_args()
    {'capture': capture, 'measure': measure, 'finalize': finalize, 'install': install}[a.cmd](a)
