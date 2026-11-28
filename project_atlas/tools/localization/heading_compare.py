#!/usr/bin/env python3
"""Offline heading comparison for a recorded drive (read-only). LiDAR keyframe-ICP heading (validated drift
0.009 deg/s while still) is the reference; compares IM10A raw/corrected gyro, Yahboom gyro, wheels and the EKF.
Usage: python3 heading_compare.py BAG_DIR"""
import math, sys
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0, '/tmp')
import analyze_drive_bag as A

bag = sys.argv[1]
topics = ['/scan', '/odom', '/yahboom/odom', '/imu/data', '/im10a/imu/bias_corrected_candidate', '/im10a/imu/unvalidated', '/set_pose', '/amcl_pose']
d = A.read_bag(bag, topics)
t0 = d['/odom'][0][0]


def pts(s):
    r = np.array(s.ranges, float); a = s.angle_min + np.arange(len(r)) * s.angle_increment
    ok = np.isfinite(r) & (r > 0.15) & (r < 6.0); return np.c_[r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok])]


def icp(P, Q, th=0.0, tx=0.0, ty=0.0, it=40):
    tree = cKDTree(Q)
    for k in range(it):
        c, s = math.cos(th), math.sin(th); Pt = P @ np.array([[c, s], [-s, c]]) + [tx, ty]
        dist, idx = tree.query(Pt); m = dist < (0.5 if k < 10 else 0.15)
        if m.sum() < 40: return None
        Aa, Bb = P[m], Q[idx[m]]; ca, cb = Aa.mean(0), Bb.mean(0); H = (Aa - ca).T @ (Bb - cb)
        th = math.atan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1]); c, s = math.cos(th), math.sin(th)
        tx, ty = cb - ca @ np.array([[c, s], [-s, c]])
    return th, tx, ty, float(m.mean())


scans = [(t - t0, pts(m)) for t, m in d['/scan']][::2]
kP, kh, rel = scans[0][1], 0.0, (0.0, 0.0, 0.0); heads = [(scans[0][0], 0.0)]; fails = 0
for t, P in scans[1:]:
    r = icp(P, kP, *rel)
    if r is None: fails += 1; continue
    # icp(P=current, Q=keyframe) returns the rotation mapping CURRENT-frame points into the KEYFRAME frame, which is
    # the rover's own rotation since the keyframe (+ = left). 2026-11-12: an earlier version subtracted it (sign bug).
    th, tx, ty, inl = r; rel = (th, tx, ty); h = kh + math.degrees(th); heads.append((t, h))
    if abs(math.degrees(th)) > 25 or inl < 0.6 or math.hypot(tx, ty) > 0.6: kP, kh, rel = P, h, (0.0, 0.0, 0.0)
L = np.array(heads)


def gyro(topic):
    v = d[topic]
    if not v: return None
    t = np.array([x - t0 for x, _ in v]); w = np.array([m.angular_velocity.z for _, m in v])
    return t, np.degrees(np.concatenate([[0], np.cumsum(w[1:] * np.diff(t))])), np.degrees(w)


def twist(topic):
    v = d[topic]; t = np.array([x - t0 for x, _ in v]); w = np.array([m.twist.twist.angular.z for _, m in v])
    return t, np.degrees(np.concatenate([[0], np.cumsum(w[1:] * np.diff(t))])), np.degrees(w)


src = {'IM10A corrected (EKF input)': gyro('/im10a/imu/bias_corrected_candidate'),
       'IM10A raw': gyro('/im10a/imu/unvalidated'), 'Yahboom gyro': gyro('/imu/data'),
       'wheels': twist('/yahboom/odom'), 'EKF turn rate': twist('/odom')}
te = np.array([x - t0 for x, _ in d['/odom']]); ey = np.degrees(np.unwrap([A.yaw_of(m.pose.pose.orientation) for _, m in d['/odom']]))
print(f'drive {te[-1]:.0f} s; LiDAR keyframe ICP failures {fails}; /set_pose messages {len(d["/set_pose"])}')
for k, v in src.items():
    print(f'  {k:28s}: ' + ('NOT RECORDED' if v is None else f'{len(v[0])} samples'))
# rate comparison: LiDAR heading rate vs each source on a 0.5 s grid while turning
g = np.arange(max(L[0, 0], 1), L[-1, 0] - 1, 0.5)
lr = np.gradient(np.interp(g, L[:, 0], L[:, 1]), g)       # deg/s
turn = np.abs(lr) > 8
print(f'turning samples (LiDAR rate > 8 deg/s): {turn.sum()} of {len(g)}')
print('turn-rate agreement with the LiDAR while turning:')
for k, v in src.items():
    if v is None: continue
    x = np.interp(g, v[0], v[2])
    c = np.corrcoef(x[turn], lr[turn])[0, 1]; s = np.dot(x[turn], lr[turn]) / np.dot(lr[turn], lr[turn])
    print(f'  {k:28s}: correlation {c:+.2f}, scale {s:+.2f}  (+1.00/+1.00 = perfect)')
print('heading change per stretch (deg):')
edges = np.linspace(L[0, 0] + 1, L[-1, 0] - 1, 5)
for a, b in list(zip(edges, edges[1:])) + [(edges[0], edges[-1])]:
    row = f'  t {a:4.0f}->{b:4.0f}s  LiDAR {np.interp(b, L[:,0], L[:,1]) - np.interp(a, L[:,0], L[:,1]):+7.1f}'
    for k, v in src.items():
        if v is not None: row += f' | {k.split(" (")[0]} {np.interp(b, v[0], v[1]) - np.interp(a, v[0], v[1]):+7.1f}'
    row += f' | EKF heading {np.interp(b, te, ey) - np.interp(a, te, ey):+7.1f}'
    if d['/amcl_pose']:
        ta = np.array([x - t0 for x, _ in d['/amcl_pose']]); ya = np.degrees(np.unwrap([A.yaw_of(m.pose.pose.orientation) for _, m in d['/amcl_pose']]))
        row += f' | AMCL {np.interp(b, ta, ya) - np.interp(a, ta, ya):+7.1f}'
    print(row)
