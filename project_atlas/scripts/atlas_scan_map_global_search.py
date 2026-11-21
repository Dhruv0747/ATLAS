#!/usr/bin/env python3
"""Read-only global scan-to-map search and startup verdict for a saved bag.

Answers "where on the saved map does this parked LiDAR scan fit?" without
AMCL, odometry or any saved pose, using atlas_localization_verify_core.
Per-beam median ranges over the chosen parked window are searched over every
free cell and heading; distinct hypotheses (>= 1 m apart) are refined and
scored on held-out beams. The verdict is VERIFIED only for a unique,
well-fitting place; otherwise UNKNOWN.

``--pose name,x,y,yaw_deg`` scores extra poses (e.g. the AMCL pose and saved
named places). ``--claimed x,y,yaw_deg`` checks agreement of one claimed pose
with the verdict. Nothing is published, seeded or moved.
"""
import argparse
import glob
import json
import math
from pathlib import Path
import sqlite3

from rosbags.typesys import Stores, get_typestore

import atlas_localization_verify_core as core

TS = get_typestore(Stores.ROS2_HUMBLE)


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def parked_scan(bag, start_s, duration_s):
    db = sqlite3.connect('file:' + glob.glob(str(Path(bag) / '*.db3'))[0] + '?mode=ro', uri=True)
    topics = {n: (i, t) for i, n, t in db.execute('SELECT id,name,type FROM topics')}

    def rows(name):
        i, t = topics[name]
        return [(r / 1e9, TS.deserialize_cdr(raw, t)) for r, raw in db.execute(
            'SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (i,))]
    laser = (0.0, 0.0, 0.0)
    for _, m in rows('/tf_static'):
        for tr in m.transforms:
            if tr.child_frame_id.strip('/') in ('laser_frame', 'laser'):
                t = tr.transform
                laser = (t.translation.x, t.translation.y, yaw_of(t.rotation))
    scans = rows('/scan')
    t0 = scans[0][0]
    use = [m for t, m in scans if start_s <= t - t0 <= start_s + duration_s]
    if not use:
        raise ValueError('no scans in window')
    return use[0], core.median_ranges([list(m.ranges) for m in use]), laser, len(use)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bag')
    ap.add_argument('map_yaml')
    ap.add_argument('output')
    ap.add_argument('--start', type=float, default=0.0, help='seconds from first scan')
    ap.add_argument('--duration', type=float, default=10.0)
    ap.add_argument('--pose', action='append', default=[], help='name,x,y,yaw_deg')
    ap.add_argument('--claimed', help='x,y,yaw_deg checked against the verdict')
    a = ap.parse_args()
    policy = core.VerifyPolicy()
    m = core.load_map(a.map_yaml)
    first, ranges, laser, count = parked_scan(a.bag, a.start, a.duration)
    allp, held = core.endpoints(first.angle_min, first.angle_increment, ranges, laser, policy)
    hyps = core.global_search(m, allp, held, policy)
    claimed = None
    if a.claimed:
        x, y, yd = (float(v) for v in a.claimed.split(','))
        claimed = (x, y, math.radians(yd))
    verdict = core.decide(hyps, len(allp), claimed, policy)
    named = {}
    for spec in a.pose:
        name, x, y, yd = spec.split(',')
        x, y, t = float(x), float(y), math.radians(float(yd))
        named[name] = {'x': x, 'y': y, 'yaw_deg': float(yd),
                       'fit_all': round(core.fit(m, allp, x, y, t, policy.tolerance_m), 3),
                       'fit_heldout': round(core.fit(m, held, x, y, t, policy.tolerance_m), 3)}
    out = {'bag': Path(a.bag).name, 'window_s': [a.start, a.start + a.duration], 'scans_used': count,
           'endpoints': len(allp), 'heldout_endpoints': len(held), 'policy': policy.__dict__,
           'verdict': verdict.as_dict(), 'named_poses': named, 'navigation_authorized': False}
    Path(a.output).write_text(json.dumps(out, indent=1))
    print(json.dumps({'verdict': out['verdict'], 'named_poses': named}, indent=1))


if __name__ == '__main__':
    main()
