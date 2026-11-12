#!/usr/bin/env python3
"""Offline, read-only: wheel (/yahboom/odom) and EKF (/odom) forward distance vs LiDAR scan-pair ICP distance.

Same method as tools/diagnostics/encoder_scale_by_speed.py (2026-10-11), for bags that have no raw
/yahboom/encoder/mN topics: scan pairs 3 scans apart, kept only when ICP is clean (inliers >= 60 %,
|yaw| < 3 deg = near-straight). Over the same receipt-time interval, |vx| of each odometry source is
integrated. Ratios binned by ICP speed AND by wheel speed (trust a trend only if both agree).
Usage: python3 wheel_vs_lidar_scale.py BAG [START_UNIX END_UNIX]
"""
import math
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, '/tmp')
import analyze_drive_bag as A  # noqa: E402

BINS = ((0.03, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.45), (0.45, 1.0))


def pts(s):
    r = np.array(s.ranges, float); a = s.angle_min + np.arange(len(r)) * s.angle_increment
    ok = np.isfinite(r) & (r > 0.15) & (r < 6.0)
    return np.c_[r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok])]


def icp(P, Q, it=40):
    th = tx = ty = 0.0; tree = cKDTree(Q)
    for k in range(it):
        c, s = math.cos(th), math.sin(th); Pt = P @ np.array([[c, s], [-s, c]]) + [tx, ty]
        dist, idx = tree.query(Pt); m = dist < (0.5 if k < 10 else 0.10)
        if m.sum() < 60: return None
        Aa, Bb = P[m], Q[idx[m]]; ca, cb = Aa.mean(0), Bb.mean(0); H = (Aa - ca).T @ (Bb - cb)
        th = math.atan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1]); c, s = math.cos(th), math.sin(th)
        tx, ty = cb - ca @ np.array([[c, s], [-s, c]])
    return th, tx, ty, float(m.mean())


def integ(t, v, a, b):
    m = (t >= a) & (t <= b)
    if m.sum() < 2: return None
    tt = np.r_[a, t[m], b]; vv = np.r_[v[m][0], v[m], v[m][-1]]
    return float(np.sum(np.abs(vv[:-1]) * np.diff(tt)))


bag = sys.argv[1]
lo, hi = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (-1e18, 1e18)
d = A.read_bag(bag, ['/scan', '/yahboom/odom', '/odom'])
ser = {k: (np.array([t for t, _ in d[k]]), np.array([m.twist.twist.linear.x for _, m in d[k]]))
       for k in ('/yahboom/odom', '/odom')}
scans = [(t, pts(m)) for t, m in d['/scan'] if lo <= t <= hi]
rows = []
for i in range(0, len(scans) - 3, 2):
    (ta, Pa), (tb, Pb) = scans[i], scans[i + 3]
    if not (0.2 <= tb - ta <= 0.8): continue
    r = icp(Pb, Pa)
    if r is None: continue
    th, tx, ty, inl = r; dl = math.hypot(tx, ty)
    if inl < 0.6 or abs(math.degrees(th)) > 3 or dl < 0.01: continue
    w = integ(*ser['/yahboom/odom'], ta, tb); e = integ(*ser['/odom'], ta, tb)
    if w is None or e is None: continue
    rows.append((dl / (tb - ta), w / (tb - ta), dl, w, e))
R = np.array(rows)
print(f'bag {bag.rstrip("/").split("/")[-1]}: {len(R)} clean straight scan pairs')
if not len(R): sys.exit()
print(f'  TOTAL over pairs: LiDAR {R[:,2].sum():.2f} m | wheel {R[:,3].sum():.2f} m ({R[:,3].sum()/R[:,2].sum():.2f}x) | '
      f'EKF {R[:,4].sum():.2f} m ({R[:,4].sum()/R[:,2].sum():.2f}x)')
for col, name in ((0, 'ICP speed'), (1, 'wheel speed')):
    print(f'  binned by {name}:   bin m/s     n   wheel/LiDAR median   EKF/LiDAR median')
    for a, b in BINS:
        m = (R[:, col] >= a) & (R[:, col] < b)
        if m.sum() < 5: continue
        print(f'                     {a:.2f}-{b:.2f} {m.sum():5d}   {np.median(R[m,3]/R[m,2]):10.2f}   {np.median(R[m,4]/R[m,2]):16.2f}')
