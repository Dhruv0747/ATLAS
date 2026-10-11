#!/usr/bin/env python3
"""Offline: separate a constant encoder SCALE error from speed-dependent LOST DISTANCE.

For scan pairs ~0.3-0.5 s apart while moving straight, LiDAR scan-to-scan ICP (independent of
wheels and map) gives the true forward motion. Over the same interval this tool also integrates:
  raw_mN    raw /yahboom/encoder/mN counts x sign / CPR x wheel circumference (no consensus),
  wheel     /yahboom/odom (after yahboom_base's 3-of-4 consensus estimator),
  ekf       /odom.
All series use the bag RECEIVE timestamp (Int32 encoder messages have no header), so the
timebase is common. Results are binned by ICP speed.

Results are binned twice, by ICP speed and by raw-encoder speed. Binning on one noisy estimate
biases the ratio (regression to the mean): ICP-binned fast bins collect ICP over-estimates and
read low, encoder-binned slow bins collect encoder under-reads and read low. Trust a speed trend
only if it appears in BOTH binnings.
  raw/ICP flat across speed      -> constant scale error (CPR / wheel size / gearing) or constant slip
  raw/ICP falling with speed     -> counts physically missed (slip or encoder/firmware loss)
  wheel/raw below 1, worse with speed -> distance dropped by the consensus estimator
Read-only; no ROS graph. Usage: encoder_scale_by_speed.py ENCODER_CALIBRATION.yaml BAG [BAG...]
"""
import glob
import json
import math
import sqlite3
import sys

import numpy as np
import yaml
from rosbags.typesys import Stores, get_typestore
from scipy.spatial import cKDTree

TS = get_typestore(Stores.ROS2_HUMBLE)
BINS = ((0.03, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.45), (0.45, 1.0))


def yaw_q(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def rows(db, topics, name):
    if name not in topics:
        return []
    i, t = topics[name]
    return [(ts * 1e-9, TS.deserialize_cdr(raw, t)) for ts, raw in
            db.execute('select timestamp,data from messages where topic_id=? order by timestamp', (i,))]


def icp(src, dst, init, iters=30):
    """Point-to-point ICP (as atlas_odometry_icp_scale_check.py): T(src) ~ dst -> (dx, dy, dyaw, rmse, inliers)."""
    tree = cKDTree(dst)
    x, y, th = init
    for _ in range(iters):
        c, s = math.cos(th), math.sin(th)
        p = src @ np.array([[c, s], [-s, c]]) + [x, y]
        d, idx = tree.query(p)
        m = d < 0.3
        if m.sum() < 30:
            return None
        a, b = src[m], dst[idx[m]]
        ma, mb = a.mean(0), b.mean(0)
        H = (a - ma).T @ (b - mb)
        th = math.atan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1])
        c, s = math.cos(th), math.sin(th)
        x, y = mb - np.array([[c, -s], [s, c]]) @ ma
    c, s = math.cos(th), math.sin(th)
    d, _ = tree.query(src @ np.array([[c, s], [-s, c]]) + [x, y])
    m = d < 0.1
    return x, y, th, float(np.sqrt(np.mean(d[m] ** 2))) if m.any() else 9.0, float(m.mean())


def analyse(bag, cal):
    db = sqlite3.connect(glob.glob(bag + '/*.db3')[0])
    topics = {n: (i, t) for i, n, t in db.execute('select id,name,type from topics')}
    lb = (0.0, 0.0, 0.0)
    for _, m in rows(db, topics, '/tf_static'):
        for tr in m.transforms:
            if tr.child_frame_id.strip('/') in ('laser_frame', 'laser'):
                t = tr.transform
                lb = (t.translation.x, t.translation.y, yaw_q(t.rotation))
    scans = []
    for ts, m in rows(db, topics, '/scan'):
        r = np.asarray(m.ranges, float)
        a = m.angle_min + np.arange(len(r)) * m.angle_increment
        ok = np.isfinite(r) & (r > 0.3) & (r < 8.0)
        pl = np.c_[r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok])]
        c, s = math.cos(lb[2]), math.sin(lb[2])
        scans.append((ts, pl @ np.array([[c, s], [-s, c]]) + lb[:2]))

    def pose_series(name):
        return np.array([(ts, m.pose.pose.position.x, m.pose.pose.position.y, yaw_q(m.pose.pose.orientation))
                         for ts, m in rows(db, topics, name)])
    odom, wheel = pose_series('/odom'), pose_series('/yahboom/odom')
    circ = cal['wheel_circumference_m']
    enc = {}
    for k in ('m1', 'm2', 'm3', 'm4'):
        series = np.array([(ts, m.data) for ts, m in rows(db, topics, f'/yahboom/encoder/{k}')], float)
        if len(series):
            mc = cal['motors'][k]
            enc[k] = (series, mc['encoder_sign'] * circ / mc['counts_per_revolution'])

    def interp(arr, t, col):
        return float(np.interp(t, arr[:, 0], arr[:, col]))

    def forward(arr, t0, t1):
        x0, y0, h0 = (interp(arr, t0, i) for i in (1, 2, 3))
        x1, y1 = interp(arr, t1, 1), interp(arr, t1, 2)
        return math.cos(h0) * (x1 - x0) + math.sin(h0) * (y1 - y0)

    pairs = []
    k = 3
    for i in range(len(scans) - k):
        (t0, a), (t1, b) = scans[i], scans[i + k]
        if not 0.2 < t1 - t0 <= 0.8 or len(a) < 80 or len(b) < 80:
            continue
        raw = {n: (interp(s, t1, 1) - interp(s, t0, 1)) * scale for n, (s, scale) in enc.items()}
        moving_raw = any(abs(v) > 0.02 for n, v in raw.items() if n != 'm3')
        o = forward(odom, t0, t1) if len(odom) else 0.0
        if not moving_raw and abs(o) < 0.02:
            continue      # parked: ICP adds nothing (gate uses raw counts too, so EKF loss cannot hide motion)
        init_fwd = max([abs(v) for n, v in raw.items() if n != 'm3'] + [abs(o)]) * (1 if o >= 0 else -1)
        r = icp(b, a, (init_fwd, 0.0, 0.0))
        if r is None or r[4] < 0.6 or r[3] > 0.05 or abs(math.degrees(r[2])) > 3:
            continue      # keep good, nearly straight pairs only
        rec = {'dt': t1 - t0, 'icp': r[0], 'ekf': o, 'wheel': forward(wheel, t0, t1) if len(wheel) else None}
        rec.update({'raw_' + n: v for n, v in raw.items()})
        pairs.append(rec)
    return pairs


def ratio(sel, key):
    sel = [p for p in sel if p.get(key) is not None]
    den = sum(p['icp'] ** 2 for p in sel)
    return None if not sel or den == 0 else round(sum(p[key] * p['icp'] for p in sel) / den, 3)


def raw_median(p):
    return float(np.median([p[k] for k in ('raw_m1', 'raw_m2', 'raw_m4') if k in p]))


def summarise(pairs, by='icp'):
    speed = (lambda p: p['icp'] / p['dt']) if by == 'icp' else (lambda p: raw_median(p) / p['dt'])
    out = {}
    for lo, hi in BINS:
        sel = [p for p in pairs if p['icp'] > 0 and lo <= speed(p) < hi]
        if len(sel) < 5:
            continue
        row = {'n': len(sel), 'raw_median_over_icp': ratio(
            [dict(icp=p['icp'], r=raw_median(p)) for p in sel], 'r')}
        for key in ('raw_m1', 'raw_m2', 'raw_m4', 'raw_m3', 'wheel', 'ekf'):
            row[key + '_over_icp'] = ratio(sel, key)
        raw_med = [raw_median(p) for p in sel]
        kept = [p['wheel'] / m for p, m in zip(sel, raw_med) if p['wheel'] is not None and abs(m) > 0.02]
        row['wheel_over_raw_median'] = round(float(np.median(kept)), 3) if kept else None
        out[f'{lo:.2f}-{hi:.2f} m/s'] = row
    return out


def main(cal_path, bags):
    cal = yaml.safe_load(open(cal_path))['encoder_calibration']
    every = []
    result = {'calibration': {k: cal['motors'][k]['counts_per_revolution'] for k in cal['motors']},
              'wheel_circumference_m': cal['wheel_circumference_m'], 'bags': {}}
    for bag in bags:
        pairs = analyse(bag, cal)
        every += pairs
        result['bags'][bag.rstrip('/').split('/')[-1]] = {'pairs': len(pairs), 'by_speed': summarise(pairs)}
    result['all_bags'] = {'pairs': len(every), 'by_icp_speed': summarise(every),
                          'by_encoder_speed': summarise(every, by='raw')}
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
