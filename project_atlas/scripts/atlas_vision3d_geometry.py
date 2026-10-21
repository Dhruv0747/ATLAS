"""Stage32 metric geometry for the Astra viewer: validated-calibration gate, back-projection, PointCloud2 layout.

Pure Python (no ROS, OpenCV or device access). Nothing here can create a metric point unless a calibration document
for the exact device, resolution and optical frame passes tools/vision3d/calibration_validation.py AND carries an
independent physical validation record. A nominal or field-of-view matrix is never accepted.

Optical-frame convention (REP 103/104): X right, Y down, Z forward, metres.
"""
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vision3d'))
import calibration_validation as CV   # noqa: E402

CALIBRATION_DIR = ROOT / 'config/astra_calibration'
DEPTH_CALIBRATION = CALIBRATION_DIR / 'depth_160x120.json'
DEPTH_FRAME = 'astra_depth_optical_frame'
DEPTH_SIZE = (160, 120)
MAX_POINTS = 6000
MAX_RANGE_M = 8.0          # beyond the Astra Pro's documented working range; documented filter, not tuning
PC2_FLOAT32 = 7


def calibration_state(manifest, path=None):
    """{'state': 'VALIDATED'|'NOT VALIDATED', 'reason', 'calibration'?}. Never raises."""
    path = Path(path or DEPTH_CALIBRATION)
    try:
        serial = (manifest or {}).get('device_serial')
        if not path.exists():
            return {'state': 'NOT VALIDATED', 'reason': 'No camera calibration file yet. Factory calibration reads as NaN; '
                                                         'a guided checkerboard calibration and physical distance checks are needed.'}
        raw = path.read_bytes()
        if len(raw) > 16384:
            raise ValueError('calibration file too large')
        doc = json.loads(raw)
        CV.validate_calibration(doc, serial, DEPTH_SIZE[0], DEPTH_SIZE[1], DEPTH_FRAME)
        return {'state': 'VALIDATED', 'reason': 'Calibration file passed document checks and carries a physical validation record.',
                'calibration': doc, 'file': str(path)}
    except Exception as e:   # any problem keeps metric geometry off
        return {'state': 'NOT VALIDATED', 'reason': 'Calibration rejected: ' + str(e)}


def undistort(u, v, k, d, iterations=8):
    """Pixel -> normalized (x, y) for plumb_bob (k1, k2, p1, p2, k3) by fixed-point inversion."""
    fx, fy, cx, cy = k[0], k[4], k[2], k[5]
    xd, yd = (u - cx) / fx, (v - cy) / fy
    if not any(d):
        return xd, yd
    k1, k2, p1, p2, k3 = d
    x, y = xd, yd
    for _ in range(iterations):
        r2 = x * x + y * y
        radial = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
        dx = 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
        dy = p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
        x, y = (xd - dx) / radial, (yd - dy) / radial
    return x, y


def _depth_reader(m):
    if m.encoding == '16UC1':
        fmt, bpp, scale = ('>' if m.is_bigendian else '<') + 'H', 2, 0.001
    elif m.encoding == '32FC1':
        fmt, bpp, scale = ('>' if m.is_bigendian else '<') + 'f', 4, 1.0
    else:
        raise ValueError('depth must be 16UC1 millimetres or 32FC1 metres')
    if m.step < m.width * bpp or len(m.data) != m.step * m.height:
        raise ValueError('invalid depth buffer/stride')

    def read(u, v):
        raw = struct.unpack_from(fmt, m.data, v * m.step + u * bpp)[0]
        if m.encoding == '16UC1' and raw in (0, 65535):
            return None
        z = raw * scale
        return z if math.isfinite(z) and 0 < z <= MAX_RANGE_M else None
    return read


_RAYS = {}


def _rays(calibration, width, height, stride):
    """Undistorted (x, y) per sampled pixel, computed once per calibration/stride (Stage32 profiling: iterative
    undistortion per frame cost ~52 ms CPU on the Jetson; the table makes each cloud a multiply)."""
    key = (tuple(calibration['k']), tuple(calibration['d']), width, height, stride)
    rays = _RAYS.get(key)
    if rays is None:
        k, d = calibration['k'], calibration['d']
        rays = [(u, v) + undistort(u, v, k, d) for v in range(0, height, stride) for u in range(0, width, stride)]
        _RAYS.clear()                     # one calibration at a time; bounded memory
        _RAYS[key] = rays
    return rays


def backproject(m, calibration, limit=MAX_POINTS):
    """Depth image + validated calibration -> [[x, y, z], ...] metres in the depth optical frame (bounded)."""
    if (m.width, m.height) != (calibration['width'], calibration['height']):
        raise ValueError('depth resolution does not match calibration; no implicit scaling')
    if m.header.frame_id != calibration['frame_id']:
        raise ValueError('depth frame does not match calibration frame')
    read = _depth_reader(m)
    limit = max(1, min(MAX_POINTS, int(limit)))
    stride = max(1, math.ceil(math.sqrt(m.width * m.height / limit)))
    points, invalid = [], 0
    for u, v, x, y in _rays(calibration, m.width, m.height, stride):
        z = read(u, v)
        if z is None:
            invalid += 1
            continue
        points.append([x * z, y * z, z])
    return points[:limit], {'stride': stride, 'invalid_samples': invalid, 'points': min(len(points), limit),
                            'source_pixels': m.width * m.height}


def pointcloud2_fields(points):
    """PointCloud2 layout for XYZ float32 (little endian, dense, unorganized)."""
    data = b''.join(struct.pack('<3f', *p) for p in points)
    return {'height': 1, 'width': len(points), 'is_bigendian': False, 'point_step': 12, 'row_step': 12 * len(points),
            'is_dense': True, 'fields': [('x', 0), ('y', 4), ('z', 8)], 'datatype': PC2_FLOAT32, 'data': data}


def plane_fit(points):
    """Least-squares plane through points: returns unit normal, signed distance from origin, RMS residual (m)."""
    n = len(points)
    if n < 3:
        raise ValueError('need at least 3 points')
    c = [sum(p[i] for p in points) / n for i in range(3)]
    q = [[0.0] * 3 for _ in range(3)]
    for p in points:
        d = [p[i] - c[i] for i in range(3)]
        for i in range(3):
            for j in range(3):
                q[i][j] += d[i] * d[j]
    # smallest eigenvector of the 3x3 covariance by inverse power iteration on (Q + eps I)
    eps = 1e-9 * (q[0][0] + q[1][1] + q[2][2] + 1e-12)
    a = [[q[i][j] + (eps if i == j else 0) for j in range(3)] for i in range(3)]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    inv = [[(a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3] - a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]) / det
            for j in range(3)] for i in range(3)]
    v = [0.3, 0.5, 0.8]
    for _ in range(60):
        w = [sum(inv[i][j] * v[j] for j in range(3)) for i in range(3)]
        s = math.sqrt(sum(x * x for x in w)); v = [x / s for x in w]
    if v[2] < 0:
        v = [-x for x in v]
    dist = sum(v[i] * c[i] for i in range(3))
    rms = math.sqrt(sum((sum(v[i] * p[i] for i in range(3)) - dist) ** 2 for p in points) / n)
    return {'normal': v, 'distance_m': dist, 'rms_m': rms, 'points': n,
            'tilt_from_optical_axis_deg': math.degrees(math.acos(max(-1.0, min(1.0, v[2]))))}
