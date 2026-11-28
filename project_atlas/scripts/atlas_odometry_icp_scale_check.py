#!/usr/bin/env python3
"""Offline: compare wheel/EKF odometry and gyro against scan-to-scan ICP.

Usage: atlas_odometry_icp_scale_check.py BAG OUTPUT.json

For scan pairs ~0.4 s apart while moving, estimate rigid motion of base_link
by ICP (LiDAR only, independent of odometry and map), and compare with:
  /odom (EKF, authoritative), /yahboom/odom (raw wheel), gyro integration
  (/imu/data, /im10a/imu/bias_corrected_candidate).
Also estimates the time offset between /odom header stamps and /scan header
stamps by cross-correlating yaw rates.
Read-only; no ROS graph.
"""
import json, math, sqlite3, sys, glob
import numpy as np
from scipy.spatial import cKDTree
from rosbags.typesys import Stores, get_typestore

TS = get_typestore(Stores.ROS2_HUMBLE)


def yaw_q(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def load(bag):
    db = sqlite3.connect(glob.glob(bag + '/*.db3')[0])
    topics = {n: (i, t) for i, n, t in db.execute('select id,name,type from topics')}

    def rows(name):
        if name not in topics:
            return []
        i, t = topics[name]
        return [TS.deserialize_cdr(raw, t) for (raw,) in
                db.execute('select data from messages where topic_id=? order by timestamp', (i,))]
    return rows


def stamp(h):
    return h.stamp.sec + h.stamp.nanosec * 1e-9


def icp(src, dst, init, iters=30):
    """2D point-to-point ICP: find T with T(src) ~ dst. Returns (dx,dy,dyaw,rmse,inlier_frac)."""
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
        R = np.array([[c, -s], [s, c]])
        t = mb - R @ ma
        x, y = t
    c, s = math.cos(th), math.sin(th)
    p = src @ np.array([[c, s], [-s, c]]) + [x, y]
    d, _ = tree.query(p)
    m = d < 0.1
    return x, y, th, float(np.sqrt(np.mean(d[m] ** 2))) if m.any() else 9.0, float(m.mean())


def main(bag, out):
    rows = load(bag)
    lb = (0.0, 0.0, 0.0)
    for m in rows('/tf_static'):
        for tr in m.transforms:
            if tr.child_frame_id.strip('/') in ('laser_frame', 'laser'):
                t = tr.transform
                lb = (t.translation.x, t.translation.y, yaw_q(t.rotation))
    scans = []
    for m in rows('/scan'):
        r = np.asarray(m.ranges, float)
        a = m.angle_min + np.arange(len(r)) * m.angle_increment
        ok = np.isfinite(r) & (r > 0.3) & (r < 8.0)
        pl = np.c_[r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok])]
        c, s = math.cos(lb[2]), math.sin(lb[2])
        pb = pl @ np.array([[c, s], [-s, c]]) + lb[:2]   # base frame
        scans.append((stamp(m.header), pb))

    def series(name):
        out = []
        for m in rows(name):
            p = m.pose.pose
            out.append((stamp(m.header), p.position.x, p.position.y, yaw_q(p.orientation)))
        return np.array(out)
    odom, wheel = series('/odom'), series('/yahboom/odom')
    gyros = {}
    for name in ('/imu/data', '/im10a/imu/bias_corrected_candidate'):
        g = np.array([(stamp(m.header), m.angular_velocity.z) for m in rows(name)])
        if len(g):
            gyros[name] = g

    def pose_at(arr, t):
        i = np.searchsorted(arr[:, 0], t)
        i = min(max(i, 1), len(arr) - 1)
        a, b = arr[i - 1], arr[i]
        f = 0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
        return a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * wrap(b[3] - a[3])

    def rel(arr, t0, t1):
        x0, y0, h0 = pose_at(arr, t0)
        x1, y1, h1 = pose_at(arr, t1)
        dx, dy = x1 - x0, y1 - y0
        c, s = math.cos(h0), math.sin(h0)
        return c * dx + s * dy, -s * dx + c * dy, wrap(h1 - h0)

    def gyro_int(g, t0, t1):
        m = (g[:, 0] >= t0) & (g[:, 0] < t1)
        if m.sum() < 2:
            return None
        return float(g[m, 1].mean() * (t1 - t0))

    pairs = []
    k = 3
    for i in range(0, len(scans) - k):
        (t0, a), (t1, b) = scans[i], scans[i + k]
        if t1 - t0 > 0.8 or len(a) < 80 or len(b) < 80:
            continue
        o = rel(odom, t0, t1)
        if math.hypot(o[0], o[1]) < 0.02 and abs(o[2]) < math.radians(1.5):
            continue  # stationary pair: ICP adds nothing for motion-prior check
        # ICP finds T mapping later scan into earlier frame = motion of base from t0 to t1
        r = icp(b, a, o)
        if r is None or r[4] < 0.6:
            continue
        w = rel(wheel, t0, t1) if len(wheel) else (None,) * 3
        rec = {'t': round(t0 - scans[0][0], 2), 'dt': round(t1 - t0, 3),
               'icp': [round(r[0], 4), round(r[1], 4), round(math.degrees(r[2]), 3)],
               'icp_rmse': round(r[3], 4), 'icp_inliers': round(r[4], 3),
               'odom': [round(o[0], 4), round(o[1], 4), round(math.degrees(o[2]), 3)],
               'wheel': None if w[0] is None else [round(w[0], 4), round(w[1], 4), round(math.degrees(w[2]), 3)]}
        for name, g in gyros.items():
            v = gyro_int(g, t0, t1)
            rec[name] = None if v is None else round(math.degrees(v), 3)
        pairs.append(rec)

    # time offset: yaw rate from ICP (scan stamps) vs odom yaw rate (odom stamps)
    def lag_scan(arr):
        best = None
        good = [p for p in pairs if p['icp_rmse'] < 0.05]
        for lag in np.arange(-0.4, 0.41, 0.02):
            err = []
            for p in good:
                t0 = scans[0][0] + p['t']
                o = rel(arr, t0 + lag, t0 + lag + p['dt'])
                err.append((math.degrees(o[2]) - p['icp'][2]) ** 2 + (100 * (o[0] - p['icp'][0])) ** 2)
            e = float(np.mean(err)) if err else None
            if e is not None and (best is None or e < best[1]):
                best = (round(float(lag), 2), e)
        return best

    good = [p for p in pairs if p['icp_rmse'] < 0.05]

    def ratio(key, idx, min_abs):
        sel = [p for p in good if p[key] is not None and abs(p['icp'][idx]) >= min_abs]
        if not sel:
            return None
        num = sum(p[key][idx] * p['icp'][idx] for p in sel)
        den = sum(p['icp'][idx] ** 2 for p in sel)
        resid = [p[key][idx] - p['icp'][idx] for p in sel]
        return {'n': len(sel), 'scale_vs_icp': round(num / den, 3),
                'abs_err_median': round(float(np.median(np.abs(resid))), 4),
                'abs_err_p90': round(float(np.percentile(np.abs(resid), 90)), 4)}

    def gyro_ratio(name):
        sel = [p for p in good if p.get(name) is not None and abs(p['icp'][2]) >= 3]
        if not sel:
            return None
        num = sum(p[name] * p['icp'][2] for p in sel)
        den = sum(p['icp'][2] ** 2 for p in sel)
        return {'n': len(sel), 'scale_vs_icp': round(num / den, 3),
                'abs_err_median_deg': round(float(np.median([abs(p[name] - p['icp'][2]) for p in sel])), 3)}

    speed_bins = {}
    straight = [p for p in good if abs(p['icp'][2]) < 3]
    for lo, hi in ((0.03, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.45), (0.45, 1.0)):
        sel = [p for p in straight if lo <= p['icp'][0] / p['dt'] < hi]
        if len(sel) >= 5:
            den = sum(p['icp'][0] ** 2 for p in sel)
            speed_bins[f'{lo:.2f}-{hi:.2f}'] = {
                'n': len(sel),
                'odom_over_icp': round(sum(p['odom'][0] * p['icp'][0] for p in sel) / den, 3),
                'wheel_over_icp': None if sel[0]['wheel'] is None else round(
                    sum(p['wheel'][0] * p['icp'][0] for p in sel) / den, 3)}
    summary = {
        'forward_scale_by_icp_speed_mps': speed_bins,
        'bag': bag.rstrip('/').split('/')[-1], 'laser_in_base': lb, 'navigation_authorized': False,
        'pairs_moving': len(pairs), 'pairs_good_icp': len(good),
        'forward_m': {'odom': ratio('odom', 0, 0.03), 'wheel': ratio('wheel', 0, 0.03)},
        'yaw_deg': {'odom': ratio('odom', 2, 3.0), 'wheel': ratio('wheel', 2, 3.0),
                    **{n: gyro_ratio(n) for n in gyros}},
        'lateral_m_odom_abs_err_median': None if not good else round(float(np.median([abs(p['odom'][1] - p['icp'][1]) for p in good])), 4),
        'best_time_offset_odom_minus_scan_s': lag_scan(odom),
        'best_time_offset_wheel_minus_scan_s': lag_scan(wheel) if len(wheel) else None,
    }
    json.dump({'summary': summary, 'pairs': pairs}, open(out, 'w'), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
