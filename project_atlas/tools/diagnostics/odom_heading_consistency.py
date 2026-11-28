#!/usr/bin/env python3
"""Offline: is EKF translation consistent with EKF heading? (read-only, no ROS graph)

For LiDAR scan pairs (0.2-0.8 s apart) during motion, compare the direction of travel relative to
the start heading ("sideslip" beta = atan2(lateral, forward) - dyaw/2) for:
  icp     LiDAR scan-to-scan ICP (independent of wheels and map)
  ekf     recorded /odom      (production EKF: gyro yaw, wheel X/Y pose fused)
  wheel   recorded /yahboom/odom (commanded-steering yaw model)
ATLAS steers with symmetric counter-steering and the driver publishes vy = 0, so true sideslip is
small. If ekf beta is large while icp beta is small, the EKF translation is following a heading
other than its own yaw. AMCL's DifferentialMotionModel turns such lateral motion into rot1/rot2.
Usage: odom_heading_consistency.py BAG [BAG...]  ->  JSON on stdout
"""
import json, math, sys
import numpy as np
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from encoder_scale_by_speed import rows, icp, yaw_q, wrap   # same ICP as the scale tool
import glob, sqlite3


def series(db, topics, name):
    return np.array([(ts, m.pose.pose.position.x, m.pose.pose.position.y, yaw_q(m.pose.pose.orientation))
                     for ts, m in rows(db, topics, name)])


def at(arr, t):
    x = float(np.interp(t, arr[:, 0], arr[:, 1])); y = float(np.interp(t, arr[:, 0], arr[:, 2]))
    h = float(np.interp(t, arr[:, 0], np.unwrap(arr[:, 3])))
    return x, y, h


def body_motion(arr, t0, t1):
    x0, y0, h0 = at(arr, t0); x1, y1, h1 = at(arr, t1)
    c, s = math.cos(h0), math.sin(h0)
    return c * (x1 - x0) + s * (y1 - y0), -s * (x1 - x0) + c * (y1 - y0), h1 - h0


def beta(fwd, lat, dyaw):
    # direction of travel relative to the mean heading over the pair; reverse motion is folded so
    # that driving backwards straight gives 0, not 180 degrees
    sgn = 1.0 if fwd >= 0 else -1.0
    return math.degrees(wrap(math.atan2(sgn * lat, abs(fwd)) - sgn * dyaw / 2))


def analyse(bag):
    db = sqlite3.connect(glob.glob(bag + '/*.db3')[0])
    topics = {n: (i, t) for i, n, t in db.execute('select id,name,type from topics')}
    lb = (0.0, 0.0, 0.0)
    for _, m in rows(db, topics, '/tf_static'):
        for tr in m.transforms:
            if tr.child_frame_id.strip('/') in ('laser_frame', 'laser'):
                t = tr.transform; lb = (t.translation.x, t.translation.y, yaw_q(t.rotation))
    scans = []
    for ts, m in rows(db, topics, '/scan'):
        r = np.asarray(m.ranges, float); a = m.angle_min + np.arange(len(r)) * m.angle_increment
        ok = np.isfinite(r) & (r > 0.3) & (r < 8.0)
        pl = np.c_[r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok])]
        c, s = math.cos(lb[2]), math.sin(lb[2])
        scans.append((ts, pl @ np.array([[c, s], [-s, c]]) + lb[:2]))
    ekf, wheel = series(db, topics, '/odom'), series(db, topics, '/yahboom/odom')
    out = []
    for i in range(len(scans) - 3):
        (t0, a), (t1, b) = scans[i], scans[i + 3]
        if not 0.2 < t1 - t0 <= 0.8 or len(a) < 80 or len(b) < 80:
            continue
        ef, el, ey = body_motion(ekf, t0, t1)
        wf, wl, wy = body_motion(wheel, t0, t1)
        if max(abs(ef), abs(wf)) < 0.04:
            continue
        r = icp(b, a, (ef, el, ey))
        if r is None or r[4] < 0.6 or r[3] > 0.05 or abs(r[0]) < 0.04:
            continue
        rec = dict(t=t0, dt=t1 - t0, icp=(r[0], r[1], r[2]), ekf=(ef, el, ey), wheel=(wf, wl, wy))
        rec['beta'] = {k: beta(*rec[k]) for k in ('icp', 'ekf', 'wheel') if abs(rec[k][0]) > 0.02}
        out.append(rec)
    return out


def stats(v, big=10.0):
    v = np.asarray(v, float)
    if not len(v):
        return None
    a = np.abs(v)
    return dict(n=len(v), median_signed=round(float(np.median(v)), 2), median_abs=round(float(np.median(a)), 2),
                p90_abs=round(float(np.percentile(a, 90)), 2), share_abs_over=round(float((a > big).mean()), 3))


def summarise(recs):
    res = {}
    for k in ('icp', 'ekf', 'wheel'):
        res['sideslip_' + k] = stats([r['beta'][k] for r in recs if k in r['beta']])
    # heading errors vs ICP over the same pair
    both = [r for r in recs if 'ekf' in r['beta'] and 'icp' in r['beta']]
    res['beta_ekf_minus_icp'] = stats([r['beta']['ekf'] - r['beta']['icp'] for r in both])
    bothw = [r for r in recs if 'wheel' in r['beta'] and 'icp' in r['beta']]
    res['beta_wheel_minus_icp'] = stats([r['beta']['wheel'] - r['beta']['icp'] for r in bothw])
    turning = [r for r in both if abs(math.degrees(r['icp'][2])) > 3]
    straight = [r for r in both if abs(math.degrees(r['icp'][2])) <= 3]
    res['beta_ekf_minus_icp_straight'] = stats([r['beta']['ekf'] - r['beta']['icp'] for r in straight])
    res['beta_ekf_minus_icp_turning'] = stats([r['beta']['ekf'] - r['beta']['icp'] for r in turning])
    res['dyaw_err_ekf'] = stats([math.degrees(r['ekf'][2] - r['icp'][2]) for r in recs])
    res['dyaw_err_wheel'] = stats([math.degrees(r['wheel'][2] - r['icp'][2]) for r in recs])
    # lateral position error per pair (cm), the quantity AMCL's motion model consumes
    res['lateral_err_ekf_cm'] = stats([100 * (r['ekf'][1] - r['icp'][1]) for r in recs], big=2.0)
    res['lateral_err_wheel_cm'] = stats([100 * (r['wheel'][1] - r['icp'][1]) for r in recs], big=2.0)
    return res


if __name__ == '__main__':
    allr, out = [], {'bags': {}}
    for bag in sys.argv[1:]:
        recs = analyse(bag); allr += recs
        out['bags'][bag.rstrip('/').split('/')[-1]] = dict(pairs=len(recs), **summarise(recs))
    out['all'] = dict(pairs=len(allr), **summarise(allr))
    print(json.dumps(out, indent=1))
