"""Stage32 guided calibration (offline maths). OpenCV + NumPy; no device, ROS or file capture.

Workflow (each live step needs owner approval):
  1. IR-only viewer session: the owner shows a rigid, flat checkerboard in varied poses. Only CORNER COORDINATES are kept
     (CornerSet.add); images are never saved.
  2. calibrate() -> CANDIDATE intrinsics for the IR camera at its native resolution, with training RMS and held-out
     reprojection error. A candidate is NOT a validated calibration.
  3. derive_resolution() -> depth-resolution candidate (explicit, documented pixel-centre scaling; still unvalidated).
  4. Physical validation: flat matte target at tape-measured distances (depth statistics + plane fit). attach_validation()
     marks the document validated only when every distance passes the documented limits.
Only then does atlas_vision3d_geometry.calibration_state() report VALIDATED and allow metric XYZ.
"""
import math

import numpy as np

MIN_VIEWS = 12
MIN_HOLDOUT = 3
MAX_TRAIN_RMS_PX = 0.5
MAX_HOLDOUT_RMS_PX = 0.8
MIN_COVERAGE = 0.6
COVERAGE_GRID = 8


def _cv():
    import cv2
    return cv2


class CornerSet:
    """Keeps detected checkerboard corners only (never images)."""

    def __init__(self, pattern, width, height):
        if not (isinstance(pattern, tuple) and len(pattern) == 2 and min(pattern) >= 3):
            raise ValueError('pattern = (inner corners per row, per column), each >= 3')
        self.pattern, self.size, self.views, self.rejected = pattern, (width, height), [], 0
        self.cells = set()

    def add(self, gray, despeckle=0):
        """despeckle: odd Gaussian kernel (e.g. 5) applied before detection. The Astra's IR projector cannot be switched off
        on this unit (laser-enable property unsupported, A4), so its dot pattern overlays the board in IR images."""
        cv2 = _cv()
        if gray.dtype != np.uint8 or gray.shape != (self.size[1], self.size[0]):
            raise ValueError('expected native 8-bit image at the declared resolution')
        if despeckle:
            if despeckle % 2 == 0 or not 3 <= despeckle <= 15:
                raise ValueError('despeckle must be an odd kernel 3..15')
            gray = cv2.GaussianBlur(gray, (despeckle, despeckle), 0)
        found, corners = cv2.findChessboardCorners(gray, self.pattern, cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not found:
            self.rejected += 1
            return False
        corners = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1), (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 1e-3))
        self.views.append(corners.reshape(-1, 2).astype(np.float32))
        for x, y in self.views[-1]:
            self.cells.add((min(COVERAGE_GRID - 1, int(x / self.size[0] * COVERAGE_GRID)), min(COVERAGE_GRID - 1, int(y / self.size[1] * COVERAGE_GRID))))
        return True

    def coverage(self):
        return len(self.cells) / float(COVERAGE_GRID * COVERAGE_GRID)


def board_points(pattern, square_m):
    cols, rows = pattern
    return np.array([[c * square_m, r * square_m, 0.0] for r in range(rows) for c in range(cols)], np.float32)


def calibrate(corner_set, square_m, device_serial, frame_id, holdout=MIN_HOLDOUT):
    """Return a CANDIDATE calibration document plus quality metrics. Raises if the data cannot support one."""
    cv2 = _cv()
    if not (math.isfinite(square_m) and 0.005 <= square_m <= 0.2):
        raise ValueError('measured square size (metres) required')
    n = len(corner_set.views)
    if n < MIN_VIEWS + holdout:
        raise ValueError('need at least %d accepted views (%d training + %d held out), have %d' % (MIN_VIEWS + holdout, MIN_VIEWS, holdout, n))
    obj = board_points(corner_set.pattern, square_m)
    hold = list(range(0, n, max(1, n // holdout)))[:holdout]           # spread held-out views through the session
    train = [i for i in range(n) if i not in hold]
    rms, k, d, _, _ = cv2.calibrateCamera([obj] * len(train), [corner_set.views[i] for i in train], corner_set.size, None, None)
    d = d.reshape(-1)[:5]
    errs = []
    for i in hold:
        ok, r, t = cv2.solvePnP(obj, corner_set.views[i], k, d)
        if not ok:
            raise ValueError('held-out view could not be posed')
        proj, _ = cv2.projectPoints(obj, r, t, k, d)
        errs.append(float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - corner_set.views[i]) ** 2, axis=1)))))
    holdout_rms = float(np.sqrt(np.mean(np.square(errs))))
    quality = {'views_total': n, 'views_training': len(train), 'views_holdout': len(hold), 'rejected_frames': corner_set.rejected,
               'train_rms_px': float(rms), 'holdout_rms_px': holdout_rms, 'coverage': corner_set.coverage()}
    problems = [m for ok, m in ((rms <= MAX_TRAIN_RMS_PX, 'training RMS %.3f px > %.1f' % (rms, MAX_TRAIN_RMS_PX)),
                                (holdout_rms <= MAX_HOLDOUT_RMS_PX, 'held-out RMS %.3f px > %.1f' % (holdout_rms, MAX_HOLDOUT_RMS_PX)),
                                (quality['coverage'] >= MIN_COVERAGE, 'image coverage %.2f < %.2f' % (quality['coverage'], MIN_COVERAGE))) if not ok]
    doc = {'status': 'CANDIDATE' if not problems else 'REJECTED', 'problems': problems, 'source': 'measured_target',
           'device_serial': device_serial, 'width': corner_set.size[0], 'height': corner_set.size[1], 'frame_id': frame_id,
           'distortion_model': 'plumb_bob', 'k': [float(x) for x in k.reshape(-1)], 'd': [float(x) for x in d],
           'square_m': square_m, 'pattern': list(corner_set.pattern), 'quality': quality,
           'independently_validated': False, 'validation_evidence': None}
    return doc


def derive_resolution(doc, width, height, frame_id, offset_px=(0.0, 0.0)):
    """Explicit pixel-centre scaling to another resolution of the SAME optical path (e.g. 640x480 IR -> 160x120 depth).
    offset_px is a measured IR-to-depth pixel shift (if any) at the target resolution. Result stays unvalidated."""
    sx, sy = width / doc['width'], height / doc['height']
    if abs(sx - sy) > 1e-9:
        raise ValueError('non-uniform scaling; aspect ratio differs')
    k = list(doc['k'])
    k[0], k[4] = k[0] * sx, k[4] * sy
    k[2], k[5] = (k[2] + 0.5) * sx - 0.5 + offset_px[0], (k[5] + 0.5) * sy - 0.5 + offset_px[1]
    out = dict(doc, width=width, height=height, frame_id=frame_id, k=k, status='CANDIDATE',
               derived_from={'width': doc['width'], 'height': doc['height'], 'frame_id': doc['frame_id'], 'offset_px': list(offset_px)},
               independently_validated=False, validation_evidence=None)
    return out


def distance_limit_m(distance_m):
    """Documented acceptance limit for the median axial error at one measured distance: max(10 mm, 1 %)."""
    return max(0.010, 0.01 * distance_m)


MAX_REFERENCE_OFFSET_M = 0.025   # tape is measured from the Astra front face; the depth origin is inside the housing
MAX_SCALE_ERROR = 0.01


def fit_depth_offset(distance_tests):
    """Least-squares median_m = scale * reference_m + offset over >= 3 owner-measured distances.
    offset absorbs the unknown front-face-to-depth-origin datum (and any constant bias; they cannot be separated)."""
    pts = [(t['reference_m'], t['median_m']) for t in distance_tests]
    if len({round(r, 2) for r, _ in pts}) < 3:
        raise ValueError('need at least 3 distinct measured distances to fit scale and offset')
    n = len(pts); mx = sum(r for r, _ in pts) / n; my = sum(m for _, m in pts) / n
    sxx = sum((r - mx) ** 2 for r, _ in pts); sxy = sum((r - mx) * (m - my) for r, m in pts)
    scale = sxy / sxx; offset = my - scale * mx
    return {'scale': scale, 'offset_m': offset, 'residuals_m': [m - (scale * r + offset) for r, m in pts]}


def attach_validation(doc, distance_tests, plane_tests, front_face_reference=False):
    """distance_tests: [{'reference_m', 'median_m', 'invalid_percent'}] from depth_statistics on owner-measured targets.
    plane_tests: [{'rms_m', 'distance_m', 'reference_m'}] from plane_fit on the calibrated cloud of the same targets.
    Validated only if >= 2 distinct distances pass every limit; otherwise the document stays a candidate."""
    if doc.get('status') != 'CANDIDATE':
        raise ValueError('only a CANDIDATE calibration can be validated')
    results, distances = [], set()
    model = None
    if front_face_reference:
        model = fit_depth_offset(distance_tests)
        ok = abs(model['offset_m']) <= MAX_REFERENCE_OFFSET_M and abs(model['scale'] - 1) <= MAX_SCALE_ERROR
        results.append({'kind': 'depth_model', **model, 'limits': {'offset_m': MAX_REFERENCE_OFFSET_M, 'scale': MAX_SCALE_ERROR}, 'pass': ok})
    for t in distance_tests:
        err = t['median_m'] - t['reference_m'] - (model['offset_m'] if model else 0.0)
        ok = abs(err) <= distance_limit_m(t['reference_m']) and t['invalid_percent'] <= 10
        results.append({'kind': 'axial_distance', **t, 'error_m': err, 'limit_m': distance_limit_m(t['reference_m']), 'pass': ok})
        if ok:
            distances.add(round(t['reference_m'], 2))
    for t in plane_tests:
        ref = t['reference_m'] + (model['offset_m'] if model else 0.0)
        ok = t['rms_m'] <= max(0.005, 0.005 * t['reference_m']) and abs(t['distance_m'] - ref) <= distance_limit_m(t['reference_m'])
        results.append({'kind': 'plane_fit', **t, 'pass': ok})
    passed = len(distances) >= 2 and results and all(r['pass'] for r in results) and any(r['kind'] == 'plane_fit' for r in results)
    out = dict(doc, validation_results=results)
    if model:
        out['depth_reference_offset_m'] = model['offset_m']   # documented datum offset; depth data are NOT corrected by it
    if passed:
        out.update(status='VALIDATED', independently_validated=True, validation_evidence='owner-measured targets; see validation_results')
    return out
