#!/usr/bin/env python3
"""Offline: how long can all four raw encoder counts stay unchanged while ATLAS is MOVING?
Uses the exact per-update /atlas/encoder_update snapshots and LiDAR ICP as the independent motion
reference (rover moving = ICP translation >= 3 cm or rotation >= 1.5 deg over a ~0.4 s scan pair).
For each run of consecutive updates whose raw counts are all identical to the previous update,
records duration and whether the rover was moving according to ICP. The longest run while moving
is the minimum hold time a 'counts unchanged = stopped' rule needs.
  encoder_still_runs.py BAG [BAG...]
"""
import glob, json, math, sqlite3, sys
import numpy as np
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from encoder_scale_by_speed import rows, icp, yaw_q


def icp_motion(db, topics):
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
    out = []   # (t0, t1, moving?)
    for i in range(0, len(scans) - 3):
        (t0, a), (t1, b) = scans[i], scans[i + 3]
        if not 0.2 < t1 - t0 <= 0.8 or len(a) < 80 or len(b) < 80:
            continue
        r = icp(b, a, (0.0, 0.0, 0.0))
        if r is None or r[4] < 0.6 or r[3] > 0.05:
            continue
        out.append((t0, t1, math.hypot(r[0], r[1]) >= 0.03 or abs(math.degrees(r[2])) >= 1.5))
    return out


def main(bags):
    res = {}
    for bag in bags:
        db = sqlite3.connect(glob.glob(bag + '/*.db3')[0])
        topics = {n: (i, t) for i, n, t in db.execute('select id,name,type from topics')}
        snaps = [(ts, json.loads(m.data)) for ts, m in rows(db, topics, '/atlas/encoder_update')]
        if not snaps:
            res[bag.rstrip('/').split('/')[-1]] = 'no /atlas/encoder_update'; continue
        mot = icp_motion(db, topics)
        def moving(t):
            hits = [m for a, b, m in mot if a <= t <= b]
            return None if not hits else any(hits)
        runs, start, prev = [], None, None
        for ts, s in snaps:
            raw = tuple(s['raw_counts'])
            same = prev is not None and raw == prev and s.get('packet_fresh')
            if same and start is None:
                start = ts
            if not same and start is not None:
                runs.append((start, ts)); start = None
            prev = raw
        rec = []
        for a, b in runs:
            mv = [moving(t) for t in np.linspace(a, b, 5)]
            known = [m for m in mv if m is not None]
            rec.append((b - a, (any(known) if known else None)))
        mv_runs = sorted([d for d, m in rec if m], reverse=True)
        st_runs = [d for d, m in rec if m is False]
        dts = np.diff([ts for ts, _ in snaps])
        res[bag.rstrip('/').split('/')[-1]] = dict(
            updates=len(snaps), update_period_s_median=round(float(np.median(dts)), 3),
            unchanged_runs=len(rec), runs_while_moving=len(mv_runs),
            longest_unchanged_while_moving_s=round(mv_runs[0], 3) if mv_runs else None,
            p99_unchanged_while_moving_s=round(float(np.percentile(mv_runs, 99)), 3) if mv_runs else None,
            top5_while_moving_s=[round(x, 3) for x in mv_runs[:5]],
            runs_while_stationary=len(st_runs))
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main(sys.argv[1:])
