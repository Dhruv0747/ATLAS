#!/usr/bin/env python3
"""Offline: EKF drift while parked, recorded vs native A/B (read-only).
A stop = recorded wheel odometry position unchanged (< 2 mm) for at least MIN_S seconds.
Reports how far each variant's /odom moved during each stop. B has no wheel position input, so a
stop where the wheel driver reports < 3 agreeing encoders (zero velocity at 1000x covariance) could
let B coast; this checks that on real stops.
  ekf_ab_stops.py BAG A.csv B.csv
"""
import glob, json, math, sqlite3, sys
import numpy as np
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from ekf_ab_compare import bag_series, load_csv, at
from encoder_scale_by_speed import rows
MIN_S = 3.0

def main(bag, a, b):
    db = sqlite3.connect(glob.glob(bag + '/*.db3')[0])
    topics = {n: (i, t) for i, n, t in db.execute('select id,name,type from topics')}
    w = bag_series(db, topics, '/yahboom/odom')
    src = [(ts, m.data) for ts, m in rows(db, topics, '/yahboom/odom_source')]
    S = {'recorded': bag_series(db, topics, '/odom'), 'A': load_csv(a), 'B': load_csv(b)}
    lo = max(s[0, 0] for s in S.values()); hi = min(s[-1, 0] for s in S.values())
    stops, i = [], 0
    while i < len(w):
        j = i
        while j + 1 < len(w) and math.hypot(w[j + 1, 1] - w[i, 1], w[j + 1, 2] - w[i, 2]) < 0.002:
            j += 1
        if w[j, 0] - w[i, 0] >= MIN_S and lo < w[i, 0] + 0.5 and w[j, 0] < hi:
            stops.append((w[i, 0] + 0.5, w[j, 0]))   # skip the first 0.5 s (deceleration settling)
        i = j + 1
    out = []
    for t0, t1 in stops:
        r = {'t0': round(t0 - w[0, 0], 1), 'dur_s': round(t1 - t0, 1),
             'low_consensus_share': round(float(np.mean([('of4' in s and not s.endswith('4of4')) or 'unavailable' in s
                                                         for ts, s in src if t0 <= ts <= t1] or [0])), 2)}
        for k, s in S.items():
            x0, y0, h0 = at(s, t0); x1, y1, h1 = at(s, t1)
            r[k + '_cm'] = round(100 * math.hypot(x1 - x0, y1 - y0), 2); r[k + '_deg'] = round(math.degrees(h1 - h0), 2)
        out.append(r)
    summary = {k: dict(max_cm=max([o[k + '_cm'] for o in out] or [0]), median_cm=float(np.median([o[k + '_cm'] for o in out])) if out else 0)
               for k in S}
    print(json.dumps({'stops': len(out), 'summary': summary, 'detail': out}, indent=1))

if __name__ == '__main__':
    main(*sys.argv[1:4])
