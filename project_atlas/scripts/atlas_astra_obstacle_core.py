"""Track A core: Astra depth image -> 2D obstacle ranges in base_link. Pure NumPy (OpenCV optional), no ROS.

Fail-safe rules (each covered by tests/test_track_a.py):
  * Startup refuses unless the mount is fully measured and physically plausible, and the calibration passes
    tools/vision3d/calibration_validation.py (owner-measured physical validation).
  * Invalid depth (0, NaN, +-inf, outside range) never becomes an obstacle or a free-space claim.
  * A frame is published only if it is fresh (age <= stale_s) and enough pixels are valid (min_valid_fraction).
    A blinded or covered camera produces NO scan, never an all-clear scan.
  * Bins without a return are +inf; Nav2 must use inf_is_valid:false, so "no return" never clears anything.
"""
import json
import math
from pathlib import Path

import numpy as np

MEASURED_MOUNT_KEYS = ('x_m', 'y_m', 'z_m', 'pitch_deg')
LIMITS = {'x_m': (-1.0, 1.0), 'y_m': (-0.5, 0.5), 'z_m': (0.05, 1.5), 'pitch_deg': (-45.0, 45.0),
          'yaw_deg': (-30.0, 30.0)}


class ConfigError(ValueError):
    pass


def validate_config(cfg):
    """Return a normalized config dict or raise ConfigError listing every problem."""
    problems = []
    m = dict(cfg.get('mount') or {})
    s = dict(cfg.get('obstacle_scan') or {})
    a = dict(cfg.get('astra') or {})
    for k in MEASURED_MOUNT_KEYS:
        if m.get(k) is None:
            problems.append(f'mount.{k} not measured')
    m.setdefault('yaw_deg', 0.0)
    for k, (lo, hi) in LIMITS.items():
        v = m.get(k)
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not lo <= v <= hi:
            problems.append(f'mount.{k}={v!r} outside plausible range [{lo}, {hi}]')
    if s.get('max_height_m') is None:
        problems.append('obstacle_scan.max_height_m not measured')

    def num(key, lo, hi):
        v = s.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not lo <= v <= hi:
            problems.append(f'obstacle_scan.{key}={v!r} outside [{lo}, {hi}]')
            return None
        return float(v)
    if s.get('max_height_m') is not None:
        num('max_height_m', 0.1, 2.0)
    num('min_height_m', 0.0, 0.3)
    num('range_min_m', 0.2, 1.0)
    num('range_max_m', 0.5, 5.0)
    num('angle_min_rad', -0.6, 0.0)
    num('angle_max_rad', 0.0, 0.6)
    num('angle_increment_rad', 0.001, 0.1)
    num('stale_s', 0.1, 2.0)
    num('min_valid_fraction', 0.0, 1.0)
    num('max_rate_hz', 1.0, 30.0)
    if not problems:
        if s['max_height_m'] <= s['min_height_m'] + 0.05:
            problems.append('obstacle_scan.max_height_m must exceed min_height_m by > 5 cm')
        if s['range_max_m'] <= s['range_min_m']:
            problems.append('obstacle_scan.range_max_m must exceed range_min_m')
        if s.get('target_frame') != 'base_link':
            problems.append('obstacle_scan.target_frame must be base_link')
    if (a.get('depth_width'), a.get('depth_height')) != (160, 120):
        problems.append('astra depth must be 160x120 (matches the validated calibration)')
    if problems:
        raise ConfigError('; '.join(problems))
    return {'mount': m, 'obstacle_scan': s, 'astra': a, 'bridge': cfg.get('bridge') or {}}


def load_validated_calibration(root):
    """Raise unless config/astra_calibration/depth_160x120.json passes the physical-validation gate."""
    import sys
    root = Path(root)
    sys.path.insert(0, str(root / 'tools/vision3d'))
    import calibration_validation as cv  # noqa: E402
    manifest = json.loads((root / 'config/vision3d_live.json').read_text())
    serial = manifest.get('device_serial') or (manifest.get('identity') or {}).get('device_serial')
    doc = json.loads((root / 'config/astra_calibration/depth_160x120.json').read_text())
    cv.validate_calibration(doc, serial, 160, 120, 'astra_depth_optical_frame')
    return doc


def pixel_rays(k, d, width, height):
    """(H*W, 2) normalized undistorted image coordinates (x/z, y/z) for every pixel centre."""
    k = np.asarray(k, dtype=np.float64).reshape(3, 3)
    u, v = np.meshgrid(np.arange(width, dtype=np.float64), np.arange(height, dtype=np.float64))
    pts = np.stack([u.ravel(), v.ravel()], axis=1)
    dist = np.asarray(d, dtype=np.float64)
    if np.any(dist != 0):
        try:
            import cv2
            return cv2.undistortPoints(pts.reshape(-1, 1, 2), k, dist).reshape(-1, 2)
        except ImportError:
            pass  # pinhole fallback; documented accuracy limit when OpenCV is absent
    return np.stack([(pts[:, 0] - k[0, 2]) / k[0, 0], (pts[:, 1] - k[1, 2]) / k[1, 1]], axis=1)


def optical_to_base(mount):
    """Rotation R and translation t mapping astra_depth_optical_frame points into base_link."""
    # optical (x right, y down, z forward) -> camera body (x forward, y left, z up)
    r_body_opt = np.array([[0.0, 0.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]])
    p = math.radians(mount['pitch_deg'])   # + = looking down = positive pitch about body y (REP-103)
    y = math.radians(mount.get('yaw_deg', 0.0))
    r_pitch = np.array([[math.cos(p), 0.0, math.sin(p)], [0.0, 1.0, 0.0], [-math.sin(p), 0.0, math.cos(p)]])
    r_yaw = np.array([[math.cos(y), -math.sin(y), 0.0], [math.sin(y), math.cos(y), 0.0], [0.0, 0.0, 1.0]])
    r = r_yaw @ r_pitch @ r_body_opt
    t = np.array([mount['x_m'], mount['y_m'], mount['z_m']], dtype=np.float64)
    return r, t


class ObstacleScanner:
    def __init__(self, cfg, calibration):
        self.cfg = validate_config(cfg)
        self.s = self.cfg['obstacle_scan']
        self.rays = pixel_rays(calibration['k'], calibration['d'], 160, 120)
        self.r, self.t = optical_to_base(self.cfg['mount'])
        self.amin, self.amax = float(self.s['angle_min_rad']), float(self.s['angle_max_rad'])
        self.inc = float(self.s['angle_increment_rad'])
        self.nbins = int(math.floor((self.amax - self.amin) / self.inc)) + 1

    def scan(self, depth, encoding='16UC1'):
        """depth: (120,160) array. Returns (ranges float32[nbins], stats dict). Never raises on bad pixels."""
        depth = np.asarray(depth)
        if depth.shape != (120, 160):
            raise ValueError('depth image must be 160x120')
        z = depth.astype(np.float64).ravel()
        if encoding == '16UC1':
            z = z * 0.001                      # millimetres -> metres
        elif encoding != '32FC1':
            raise ValueError('unsupported depth encoding ' + str(encoding))
        valid = np.isfinite(z) & (z > 0.0)
        valid_fraction = float(valid.mean())
        zv = z[valid]
        pts = np.empty((zv.size, 3))
        pts[:, 0] = self.rays[valid, 0] * zv
        pts[:, 1] = self.rays[valid, 1] * zv
        pts[:, 2] = zv
        base = pts @ self.r.T + self.t
        band = (base[:, 2] >= self.s['min_height_m']) & (base[:, 2] <= self.s['max_height_m'])
        rng = np.hypot(base[:, 0], base[:, 1])
        ang = np.arctan2(base[:, 1], base[:, 0])
        keep = band & (rng >= self.s['range_min_m']) & (rng <= self.s['range_max_m']) & \
            (ang >= self.amin) & (ang <= self.amax)
        ranges = np.full(self.nbins, np.inf, dtype=np.float32)
        if keep.any():
            idx = np.clip(((ang[keep] - self.amin) / self.inc).astype(np.int64), 0, self.nbins - 1)
            np.minimum.at(ranges, idx, rng[keep].astype(np.float32))
        return ranges, {'valid_fraction': valid_fraction, 'obstacle_points': int(keep.sum()),
                        'obstacle_bins': int(np.isfinite(ranges).sum())}

    def decide(self, stats, age_s):
        """'OK' (publish) or a reason not to publish. Age must be finite and within [0, stale_s]."""
        if not math.isfinite(age_s) or age_s < -0.05 or age_s > self.s['stale_s']:
            return 'STALE'
        if stats['valid_fraction'] < self.s['min_valid_fraction']:
            return 'BLINDED'
        return 'OK'
