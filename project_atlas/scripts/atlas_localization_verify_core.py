"""Pure startup-localization verification: where does a parked scan fit?

Background (2026-10-10 Hall cold start): after every boot the seeder put AMCL
at the saved Dhruv Room pose without looking at the LiDAR. With ATLAS parked
in the Hall, AMCL's whole cloud sat ~6 m from the truth, collapsed to one
particle under 1 Hz forced updates and the dashboard showed CONFIDENT at a
pose whose held-out scan fit was 0.54. The covariance cannot reveal this.

This module decides from the scan and the saved map alone:

- ``global_search``: score every free map cell (coarse grid) at every heading
  by the fraction of scan endpoints within ``tolerance`` of a mapped wall,
  refine the best distinct hypotheses and score them again on beams AMCL does
  not use (held-out).
- ``decide``: VERIFIED only when one hypothesis fits well AND clearly beats
  every other place at least ``separation_m`` away. Otherwise UNKNOWN.
  A saved or current pose is accepted only if it agrees with that unique
  hypothesis; it is never trusted on its own.

Evidence for the thresholds (docs/audits/ATLAS_HALL_COLDSTART_LOCALIZATION_2026-10-10.md):
11 parked windows (10 recorded on Oct 9, 1 live on Oct 10). The best
hypothesis matched the known room every time with held-out fit 0.975-1.000;
the best wrong place 1 m or more away scored 0.78-0.90, a margin of 0.10-0.19.

Nothing here publishes, seeds or moves anything.
"""
from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage

AMCL_BEAMS = 60


@dataclass(frozen=True)
class VerifyPolicy:
    tolerance_m: float = 0.15
    min_fit: float = 0.93          # best wrong place seen: 0.897; true places >= 0.975
    min_margin: float = 0.06       # observed margins 0.103-0.189
    separation_m: float = 1.0      # "different place"
    separation_deg: float = 30.0   # same spot, different heading is also a different hypothesis
    agree_m: float = 0.5           # saved/current pose agrees with the search
    agree_deg: float = 20.0
    min_endpoints: int = 120
    grid_m: float = 0.10
    yaw_step_deg: float = 3.0
    min_range_m: float = 0.3
    max_range_m: float = 8.0
    keep_per_heading: int = 40
    hypotheses: int = 5


@dataclass
class Verdict:
    state: str                                   # VERIFIED | UNKNOWN
    pose: Optional[Tuple[float, float, float]]   # x, y, yaw (rad) when VERIFIED
    reason: str
    best_fit: Optional[float] = None
    margin: Optional[float] = None
    hypotheses: List[dict] = field(default_factory=list)

    def as_dict(self):
        return {'state': self.state, 'reason': self.reason,
                'pose': None if self.pose is None else {
                    'x': round(self.pose[0], 3), 'y': round(self.pose[1], 3),
                    'yaw_deg': round(math.degrees(self.pose[2]), 1)},
                'best_fit': self.best_fit, 'margin': self.margin,
                'hypotheses': self.hypotheses}


def _read_pgm(path: Path):
    raw = Path(path).read_bytes()
    parts, i = [], 0
    while len(parts) < 4:
        while raw[i:i + 1].isspace():
            i += 1
        if raw[i:i + 1] == b'#':
            while raw[i:i + 1] not in (b'\n', b''):
                i += 1
            continue
        j = i
        while not raw[j:j + 1].isspace():
            j += 1
        parts.append(raw[i:j])
        i = j
    if parts[0] != b'P5' or int(parts[3]) > 255:
        raise ValueError('only 8-bit binary PGM maps are supported')
    w, h = int(parts[1]), int(parts[2])
    data = raw[i + 1:i + 1 + w * h]
    if len(data) != w * h:
        raise ValueError('truncated PGM')
    return w, h, np.frombuffer(data, dtype=np.uint8).reshape(h, w)


def load_map(yaml_path) -> dict:
    """Exact saved map -> occupied/free masks and wall-distance field (map rows bottom-up)."""
    meta = {}
    for line in Path(yaml_path).read_text().splitlines():
        if ':' in line and not line.lstrip().startswith('#'):
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip()
    w, h, pix = _read_pgm(Path(yaml_path).with_name(meta['image']))
    pix = pix[::-1]
    res = float(meta['resolution'])
    origin = [float(v) for v in meta['origin'].strip('[]').split(',')[:2]]
    p = pix / 255.0 if int(meta.get('negate', 0)) else (255 - pix) / 255.0
    occupied = p > float(meta['occupied_thresh'])
    free = p < float(meta['free_thresh'])
    if not occupied.any():
        raise ValueError('map has no occupied cells')
    return {'res': res, 'origin': origin, 'occupied': occupied, 'free': free,
            'dist': ndimage.distance_transform_edt(~occupied) * res, 'w': w, 'h': h}


def endpoints(angle_min: float, angle_increment: float, ranges: Sequence[float],
              laser_in_base: Tuple[float, float, float], policy: VerifyPolicy = VerifyPolicy()):
    """Base-frame endpoints (all usable beams, held-out beams) from one range vector."""
    r = np.array([v if v is not None and math.isfinite(v) else np.nan for v in ranges], float)
    idx = np.arange(len(r))
    ang = angle_min + idx * angle_increment + laser_in_base[2]
    ok = np.isfinite(r) & (r >= policy.min_range_m) & (r <= policy.max_range_m)
    step = max(1, (len(r) - 1) // (AMCL_BEAMS - 1))
    pts = np.c_[laser_in_base[0] + r * np.cos(ang), laser_in_base[1] + r * np.sin(ang)]
    return pts[ok], pts[ok & (idx % step != 0)]


def median_ranges(range_rows: Sequence[Sequence[float]]):
    """Per-beam median over parked scans (suppresses single-scan dropouts)."""
    arr = np.array([[v if v is not None and math.isfinite(v) else np.nan for v in row]
                    for row in range_rows], float)
    with np.errstate(all='ignore'):
        out = np.nanmedian(arr, axis=0) if np.isfinite(arr).any(axis=0).any() else arr[0]
    return [float(v) for v in out]


def fit(m: dict, pts: np.ndarray, x: float, y: float, yaw: float, tol: float) -> float:
    if len(pts) == 0:
        return 0.0
    c, s = math.cos(yaw), math.sin(yaw)
    wx = x + c * pts[:, 0] - s * pts[:, 1]
    wy = y + s * pts[:, 0] + c * pts[:, 1]
    ix = np.floor((wx - m['origin'][0]) / m['res']).astype(int)
    iy = np.floor((wy - m['origin'][1]) / m['res']).astype(int)
    inside = (ix >= 0) & (ix < m['w']) & (iy >= 0) & (iy < m['h'])
    d = np.full(len(pts), 99.0)
    d[inside] = m['dist'][iy[inside], ix[inside]]
    return float(np.mean(d <= tol))


def _fit_many(m, pts, xs, ys, yaw, tol):
    c, s = math.cos(yaw), math.sin(yaw)
    rx = c * pts[:, 0] - s * pts[:, 1]
    ry = s * pts[:, 0] + c * pts[:, 1]
    ix = np.floor((xs[:, None] + rx[None, :] - m['origin'][0]) / m['res']).astype(int)
    iy = np.floor((ys[:, None] + ry[None, :] - m['origin'][1]) / m['res']).astype(int)
    inside = (ix >= 0) & (ix < m['w']) & (iy >= 0) & (iy < m['h'])
    d = np.where(inside, m['dist'][np.clip(iy, 0, m['h'] - 1), np.clip(ix, 0, m['w'] - 1)], 99.0)
    return np.mean(d <= tol, axis=1)


def _same(h, x, y, yaw, policy):
    dyaw = abs(math.atan2(math.sin(yaw - h['yaw']), math.cos(yaw - h['yaw'])))
    return math.hypot(x - h['x'], y - h['y']) < policy.separation_m and dyaw < math.radians(policy.separation_deg)


def global_search(m: dict, all_pts: np.ndarray, heldout_pts: np.ndarray,
                  policy: VerifyPolicy = VerifyPolicy()) -> List[dict]:
    """Distinct pose hypotheses (>= separation_m apart or >= separation_deg
    rotated), best held-out fit first. Uses no prior pose."""
    cand = m['free'] & (m['dist'] >= 0.15)
    step = max(1, int(round(policy.grid_m / m['res'])))
    iy, ix = np.nonzero(cand)
    keep = (iy % step == 0) & (ix % step == 0)
    xs = m['origin'][0] + (ix[keep] + 0.5) * m['res']
    ys = m['origin'][1] + (iy[keep] + 0.5) * m['res']
    if len(xs) == 0:
        return []
    sub = all_pts[::max(1, len(all_pts) // 120)]
    coarse = []
    for yaw in np.radians(np.arange(-180.0, 180.0, policy.yaw_step_deg)):
        f = _fit_many(m, sub, xs, ys, yaw, policy.tolerance_m)
        for i in np.argsort(f)[-policy.keep_per_heading:]:
            coarse.append((float(f[i]), float(xs[i]), float(ys[i]), float(yaw)))
    coarse.sort(reverse=True)
    tol = policy.tolerance_m
    hyps = []
    for _, x0, y0, t0 in coarse:
        if any(_same(h, x0, y0, t0, policy) for h in hyps):
            continue
        bx, by, bt = x0, y0, t0
        bf = fit(m, all_pts, bx, by, bt, tol)
        for dxy, dth in ((0.06, math.radians(2.0)), (0.02, math.radians(0.5))):
            improved = True
            while improved:
                improved = False
                for dx in (-dxy, 0.0, dxy):
                    for dy in (-dxy, 0.0, dxy):
                        for dt in (-dth, 0.0, dth):
                            f = fit(m, all_pts, bx + dx, by + dy, bt + dt, tol)
                            if f > bf + 1e-9:
                                bx, by, bt, bf, improved = bx + dx, by + dy, bt + dt, f, True
        bt = math.atan2(math.sin(bt), math.cos(bt))
        if any(_same(h, bx, by, bt, policy) for h in hyps):
            continue
        hyps.append({'x': bx, 'y': by, 'yaw': bt, 'fit_all': round(bf, 3),
                     'fit_heldout': round(fit(m, heldout_pts, bx, by, bt, tol), 3)})
        if len(hyps) >= policy.hypotheses:
            break
    hyps.sort(key=lambda h: -h['fit_heldout'])
    return hyps


def decide(hyps: List[dict], endpoints_used: int,
           claimed: Optional[Tuple[float, float, float]] = None,
           policy: VerifyPolicy = VerifyPolicy()) -> Verdict:
    """VERIFIED only for a unique, well-fitting place; ``claimed`` must agree with it."""
    public = [{'x': round(h['x'], 3), 'y': round(h['y'], 3), 'yaw_deg': round(math.degrees(h['yaw']), 1),
               'fit_heldout': h['fit_heldout']} for h in hyps]
    if endpoints_used < policy.min_endpoints:
        return Verdict('UNKNOWN', None, f'too few LiDAR returns ({endpoints_used})', hypotheses=public)
    if not hyps:
        return Verdict('UNKNOWN', None, 'no candidate pose on the saved map', hypotheses=public)
    best = hyps[0]
    margin = None if len(hyps) < 2 else round(best['fit_heldout'] - hyps[1]['fit_heldout'], 3)
    if best['fit_heldout'] < policy.min_fit:
        return Verdict('UNKNOWN', None,
                       f"scan does not match the saved map well enough anywhere "
                       f"(best {best['fit_heldout']:.2f} < {policy.min_fit:.2f})",
                       best['fit_heldout'], margin, public)
    if margin is not None and margin < policy.min_margin:
        return Verdict('UNKNOWN', None,
                       f"ambiguous: two places fit almost equally ({best['fit_heldout']:.2f} vs "
                       f"{hyps[1]['fit_heldout']:.2f})", best['fit_heldout'], margin, public)
    pose = (best['x'], best['y'], best['yaw'])
    if claimed is not None:
        d = math.hypot(claimed[0] - pose[0], claimed[1] - pose[1])
        dyaw = abs(math.degrees(math.atan2(math.sin(claimed[2] - pose[2]), math.cos(claimed[2] - pose[2]))))
        if d > policy.agree_m or dyaw > policy.agree_deg:
            return Verdict('UNKNOWN', None,
                           f'claimed pose disagrees with the LiDAR by {d:.2f} m / {dyaw:.0f} deg',
                           best['fit_heldout'], margin, public)
    return Verdict('VERIFIED', pose, 'unique LiDAR match on the saved map', best['fit_heldout'], margin, public)
