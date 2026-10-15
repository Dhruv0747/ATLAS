#!/usr/bin/env python3
"""Offline: compare EKF variants against LiDAR scan-to-scan ICP on one recorded drive (read-only).

  ekf_ab_compare.py BAG native_A.csv native_B.csv  ->  JSON on stdout

Series compared on the same scan pairs (bag receive time, see ekf_ab_replay.sh):
  recorded  /odom recorded on the rover (production EKF, live state)
  A         native replay of the production EKF config (cold start)
  B         native replay of Candidate B (wheel X/Y pose removed; Vx, Vy=0, gyro yaw kept)
  wheel     recorded /yahboom/odom

1. Fidelity: native A against the recorded EKF, per pair. A relative A/B is only meaningful if
   native A reproduces the recorded EKF's *relative* motion. Absolute agreement is not needed and
   is not expected from a cold start.
2. Per pair (about 0.4 s): forward, lateral and heading errors against ICP, and sideslip.
3. Chains of consecutive non-overlapping ICP pairs (about 1-1.5 m): end-point position error in the
   chain's start frame. This is the drift AMCL has to absorb between scan corrections.
Optional: ATLAS_LASER_YAW_CORR_DEG=<deg> rotates the recorded laser mount yaw before ICP, to test the
hypothesis that the constant LiDAR travel-direction offset is a mount-yaw error. Estimate it from OTHER
drives (leave-one-out); never from the drive being scored.
ICP is an independent relative-motion proxy, not ground truth; constant offsets common to all
variants (wheel distance scale, LiDAR/travel-direction offset) are reported, not removed.
"""
import glob, json, math, os, sqlite3, sys
import numpy as np
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from encoder_scale_by_speed import rows, icp, yaw_q, wrap


def load_csv(path):
    a = np.genfromtxt(path, delimiter=',', names=True)
    return np.c_[a['t'], a['x'], a['y'], a['yaw']] if a.size > 1 else None


def bag_series(db, topics, name):
    return np.array([(ts, m.pose.pose.position.x, m.pose.pose.position.y, yaw_q(m.pose.pose.orientation))
                     for ts, m in rows(db, topics, name)])


def at(arr, t):
    return (float(np.interp(t, arr[:, 0], arr[:, 1])), float(np.interp(t, arr[:, 0], arr[:, 2])),
            float(np.interp(t, arr[:, 0], np.unwrap(arr[:, 3]))))


def rel(arr, t0, t1):
    """Motion from t0 to t1 expressed in the t0 body frame: (forward, lateral, dyaw)."""
    x0, y0, h0 = at(arr, t0); x1, y1, h1 = at(arr, t1)
    c, s = math.cos(h0), math.sin(h0)
    return c * (x1 - x0) + s * (y1 - y0), -s * (x1 - x0) + c * (y1 - y0), h1 - h0


def compose(a, b):
    x, y, h = a; bx, by, bh = b
    return x + math.cos(h) * bx - math.sin(h) * by, y + math.sin(h) * bx + math.cos(h) * by, h + bh


def sideslip(m):
    f, l, d = m
    s = 1.0 if f >= 0 else -1.0
    return math.degrees(wrap(math.atan2(s * l, abs(f)) - s * d / 2))


def stats(v, big):
    v = np.asarray(v, float)
    if not len(v):
        return None
    a = np.abs(v)
    return dict(n=len(v), median=round(float(np.median(v)), 3), median_abs=round(float(np.median(a)), 3),
                p90_abs=round(float(np.percentile(a, 90)), 3), share_over=round(float((a > big).mean()), 3))


def main(bag, a_csv, b_csv):
    db = sqlite3.connect(glob.glob(bag + '/*.db3')[0])
    topics = {n: (i, t) for i, n, t in db.execute('select id,name,type from topics')}
    lb = (0.0, 0.0, 0.0)
    for _, m in rows(db, topics, '/tf_static'):
        for tr in m.transforms:
            if tr.child_frame_id.strip('/') in ('laser_frame', 'laser'):
                t = tr.transform; lb = (t.translation.x, t.translation.y, yaw_q(t.rotation))
    corr = math.radians(float(os.environ.get('ATLAS_LASER_YAW_CORR_DEG', '0')))
    lb = (lb[0], lb[1], lb[2] + corr)
    scans = []
    for ts, m in rows(db, topics, '/scan'):
        r = np.asarray(m.ranges, float); ang = m.angle_min + np.arange(len(r)) * m.angle_increment
        ok = np.isfinite(r) & (r > 0.3) & (r < 8.0)
        pl = np.c_[r[ok] * np.cos(ang[ok]), r[ok] * np.sin(ang[ok])]
        c, s = math.cos(lb[2]), math.sin(lb[2])
        scans.append((ts, pl @ np.array([[c, s], [-s, c]]) + lb[:2]))
    series = {'recorded': bag_series(db, topics, '/odom'), 'wheel': bag_series(db, topics, '/yahboom/odom'),
              'A': load_csv(a_csv), 'B': load_csv(b_csv)}
    lo = max(s[0, 0] for s in series.values()); hi = min(s[-1, 0] for s in series.values())

    pairs = {}
    for i in range(len(scans) - 3):
        (t0, a), (t1, b) = scans[i], scans[i + 3]
        if not (lo < t0 and t1 < hi and 0.2 < t1 - t0 <= 0.8 and len(a) >= 80 and len(b) >= 80):
            continue
        mot = {k: rel(v, t0, t1) for k, v in series.items()}
        if max(abs(mot['recorded'][0]), abs(mot['wheel'][0])) < 0.04:
            continue
        r = icp(b, a, mot['recorded'])
        if r is None or r[4] < 0.6 or r[3] > 0.05 or abs(r[0]) < 0.04:
            continue
        pairs[i] = dict(t0=t0, icp=(r[0], r[1], r[2]), **mot)

    out = {'pairs': len(pairs), 'laser_yaw_correction_deg': math.degrees(corr)}
    # 1. fidelity of the native replay (relative motion only)
    out['fidelity_A_vs_recorded'] = {
        'forward_cm': stats([100 * (p['A'][0] - p['recorded'][0]) for p in pairs.values()], 1.0),
        'lateral_cm': stats([100 * (p['A'][1] - p['recorded'][1]) for p in pairs.values()], 1.0),
        'dyaw_deg': stats([math.degrees(p['A'][2] - p['recorded'][2]) for p in pairs.values()], 1.0),
        'sideslip_deg': stats([sideslip(p['A']) - sideslip(p['recorded']) for p in pairs.values()], 3.0)}
    # 2. per-pair errors against ICP
    for k in ('recorded', 'A', 'B', 'wheel'):
        out['pair_' + k] = {
            'forward_err_cm': stats([100 * (p[k][0] - p['icp'][0]) for p in pairs.values()], 2.0),
            'lateral_err_cm': stats([100 * (p[k][1] - p['icp'][1]) for p in pairs.values()], 2.0),
            'dyaw_err_deg': stats([math.degrees(p[k][2] - p['icp'][2]) for p in pairs.values()], 3.0),
            'sideslip_minus_icp_deg': stats([sideslip(p[k]) - sideslip(p['icp']) for p in pairs.values()], 10.0)}
    # 3. chains of consecutive non-overlapping pairs i, i+3, i+6, ...
    chains = {k: [] for k in ('recorded', 'A', 'B', 'wheel')}
    L = 10
    for i in sorted(pairs):
        idx = [i + 3 * j for j in range(L)]
        if not all(j in pairs for j in idx):
            continue
        ref = (0.0, 0.0, 0.0)
        for j in idx:
            ref = compose(ref, pairs[j]['icp'])
        if math.hypot(ref[0], ref[1]) < 0.5:
            continue
        t0, t1 = pairs[idx[0]]['t0'], scans[idx[-1] + 3][0]
        for k in chains:
            m = rel(series[k], t0, t1)
            chains[k].append((100 * math.hypot(m[0] - ref[0], m[1] - ref[1]), 100 * (m[1] - ref[1]),
                              math.degrees(m[2] - ref[2]), math.hypot(ref[0], ref[1])))
    out['chain_len_pairs'] = L
    for k, c in chains.items():
        out['chain_' + k] = None if not c else {
            'n': len(c), 'mean_length_m': round(float(np.mean([x[3] for x in c])), 2),
            'endpoint_err_cm': stats([x[0] for x in c], 20.0),
            'lateral_err_cm': stats([x[1] for x in c], 10.0),
            'dyaw_err_deg': stats([x[2] for x in c], 5.0)}
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:4])
