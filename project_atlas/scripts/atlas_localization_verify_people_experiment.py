#!/usr/bin/env python3
"""Offline stress test: does the start-pose verifier tolerate people moving?

Takes REAL parked scans from saved bags (3 s, as the seeder collects) and
inserts simulated people into them: each person is two legs (circles of
radius 0.06 m, 0.25 m apart) that block LiDAR beams. Walkers move at
0.6-1.4 m/s with a stepping gait; standers do not move. People are placed
only in mapped free space around the true pose. Then the full verifier
(global search + verdict) runs with each per-beam aggregation of the scans:

  median  per-beam median (deployed)
  p80     per-beam 80th percentile
  p90     per-beam 90th percentile

People can only make a range SHORTER, so a high percentile recovers the wall
behind a passer-by. The risk is spurious long returns; the clean windows
measure that.

Outcome per run: VERIFIED_RIGHT, VERIFIED_WRONG (the failure that must never
happen), or UNKNOWN. Read-only; nothing is published or seeded.
"""
import argparse
import glob
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
from rosbags.typesys import Stores, get_typestore

import atlas_localization_verify_core as core

TS = get_typestore(Stores.ROS2_HUMBLE)
LEG_R = 0.06
LEG_SPACING = 0.25
SCENARIOS = {
    'clean': {'walkers': 0, 'standers': 0},
    'one_walker': {'walkers': 1, 'standers': 0},
    'two_walkers': {'walkers': 2, 'standers': 0},
    'stander_and_walker': {'walkers': 1, 'standers': 1},
    'three_standing_close': {'walkers': 0, 'standers': 3, 'near': True},
}
AGGREGATES = ('median', 'p80', 'p90')


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def load_scans(bag, start_s, duration_s):
    db = sqlite3.connect('file:' + glob.glob(str(Path(bag) / '*.db3'))[0] + '?mode=ro', uri=True)
    topics = {n: (i, t) for i, n, t in db.execute('SELECT id,name,type FROM topics')}
    laser = (0.0, 0.0, 0.0)
    i, t = topics['/tf_static']
    for (raw,) in db.execute('SELECT data FROM messages WHERE topic_id=?', (i,)):
        for tr in TS.deserialize_cdr(raw, t).transforms:
            if tr.child_frame_id.strip('/') in ('laser_frame', 'laser'):
                tt = tr.transform
                laser = (tt.translation.x, tt.translation.y, yaw_of(tt.rotation))
    i, t = topics['/scan']
    rows = [(r / 1e9, TS.deserialize_cdr(raw, t)) for r, raw in db.execute(
        'SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (i,))]
    t0 = rows[0][0]
    use = [(ts - t0, m) for ts, m in rows if start_s <= ts - t0 <= start_s + duration_s]
    first = use[0][1]
    ranges = np.array([[v if math.isfinite(v) else np.nan for v in m.ranges] for _, m in use], float)
    times = np.array([ts for ts, _ in use]) - use[0][0]
    return first.angle_min, first.angle_increment, ranges, times, laser


def free_at(m, pose, bx, by, clearance=0.25):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    wx, wy = pose[0] + c * bx - s * by, pose[1] + s * bx + c * by
    ix = int((wx - m['origin'][0]) / m['res'])
    iy = int((wy - m['origin'][1]) / m['res'])
    return 0 <= ix < m['w'] and 0 <= iy < m['h'] and m['free'][iy, ix] and m['dist'][iy, ix] >= clearance


def make_people(rng, m, truth, scenario, duration):
    """List of functions t -> [(x, y) leg centres in base frame]."""
    people = []
    spec = SCENARIOS[scenario]
    for kind, count in (('walker', spec['walkers']), ('stander', spec['standers'])):
        for _ in range(count):
            for _attempt in range(500):
                lo, hi = (0.5, 1.5) if spec.get('near') else (0.6, 3.0)
                r, a = rng.uniform(lo, hi), rng.uniform(-math.pi, math.pi)
                x0, y0 = r * math.cos(a), r * math.sin(a)
                heading = rng.uniform(-math.pi, math.pi)
                speed = rng.uniform(0.6, 1.4) if kind == 'walker' else 0.0
                path = [(x0 + speed * tt * math.cos(heading), y0 + speed * tt * math.sin(heading))
                        for tt in np.linspace(0, duration, 8)]
                if all(free_at(m, truth, px, py) and math.hypot(px, py) > 0.45 for px, py in path):
                    break
            else:
                continue

            def legs(tt, x0=x0, y0=y0, h=heading, v=speed):
                cx, cy = x0 + v * tt * math.cos(h), y0 + v * tt * math.sin(h)
                swing = 0.15 * math.sin(2 * math.pi * 1.8 * tt) if v > 0 else 0.0
                nx, ny = -math.sin(h), math.cos(h)
                fx, fy = math.cos(h), math.sin(h)
                return [(cx + nx * LEG_SPACING / 2 + fx * swing, cy + ny * LEG_SPACING / 2 + fy * swing),
                        (cx - nx * LEG_SPACING / 2 - fx * swing, cy - ny * LEG_SPACING / 2 - fy * swing)]
            people.append(legs)
    return people


def occlude(ranges, times, angle_min, inc, laser, people):
    out = ranges.copy()
    n = ranges.shape[1]
    ang = angle_min + np.arange(n) * inc + laser[2]          # base-frame beam directions
    dx, dy = np.cos(ang), np.sin(ang)
    for k, tt in enumerate(times):
        for person in people:
            for cx, cy in person(tt):
                ox, oy = cx - laser[0], cy - laser[1]          # circle centre relative to laser
                b = ox * dx + oy * dy
                disc = b * b - (ox * ox + oy * oy - LEG_R * LEG_R)
                hit = (disc >= 0) & (b > 0)
                d = np.where(hit, b - np.sqrt(np.maximum(disc, 0)), np.inf)
                row = out[k]
                shorter = hit & ((~np.isfinite(row)) | (d < row))
                row[shorter] = d[shorter]
    return out


def aggregate(ranges, how):
    with np.errstate(all='ignore'):
        if how == 'median':
            return np.nanmedian(ranges, axis=0)
        return np.nanpercentile(ranges, {'p80': 80, 'p90': 90}[how], axis=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('map_yaml')
    ap.add_argument('windows', help='JSON list of {name,bag,start,truth:[x,y,yaw_deg]}')
    ap.add_argument('output')
    ap.add_argument('--seeds', type=int, default=2)
    ap.add_argument('--shard', default='0/1')
    ap.add_argument('--aggregates', default=','.join(AGGREGATES))
    a = ap.parse_args()
    shard, shards = (int(v) for v in a.shard.split('/'))
    m = core.load_map(a.map_yaml)
    policy = core.VerifyPolicy()
    jobs = []
    for w in json.loads(Path(a.windows).read_text()):
        for scenario in SCENARIOS:
            for seed in range(1 if scenario == 'clean' else a.seeds):
                for how in a.aggregates.split(','):
                    jobs.append((w, scenario, seed, how))
    results = []
    cache = {}
    for n, (w, scenario, seed, how) in enumerate(jobs):
        if n % shards != shard:
            continue
        if w['name'] not in cache:
            cache[w['name']] = load_scans(w['bag'], w['start'], 3.0)
        amin, inc, ranges, times, laser = cache[w['name']]
        truth = (w['truth'][0], w['truth'][1], math.radians(w['truth'][2]))
        rng = np.random.default_rng(1000 * seed + list(SCENARIOS).index(scenario))
        people = make_people(rng, m, truth, scenario, float(times[-1]))
        occluded = occlude(ranges, times, amin, inc, laser, people)
        agg = aggregate(occluded, how)
        allp, held = core.endpoints(amin, inc, [float(v) for v in agg], laser, policy)
        hyps = core.global_search(m, allp, held, policy)
        verdict = core.decide(hyps, len(allp), None, policy)
        truth_fit = core.fit(m, held, *truth, policy.tolerance_m)
        if verdict.state == 'VERIFIED':
            x, y, yaw = verdict.pose
            dyaw = abs(math.degrees(math.atan2(math.sin(yaw - truth[2]), math.cos(yaw - truth[2]))))
            right = math.hypot(x - truth[0], y - truth[1]) <= 0.5 and dyaw <= 20
            outcome = 'VERIFIED_RIGHT' if right else 'VERIFIED_WRONG'
        else:
            outcome = 'UNKNOWN'
        blocked = float(np.mean(np.isfinite(occluded) & (occluded < np.nan_to_num(ranges, nan=np.inf) - 0.05)))
        results.append({'window': w['name'], 'scenario': scenario, 'seed': seed, 'aggregate': how,
                        'people': len(people), 'beam_fraction_blocked': round(blocked, 3),
                        'scans': int(len(times)), 'outcome': outcome, 'reason': verdict.reason,
                        'best_fit': verdict.best_fit, 'margin': verdict.margin,
                        'fit_at_truth': round(truth_fit, 3), 'endpoints': len(allp),
                        'hypotheses': [{'fit_heldout': h['fit_heldout'],
                                        'is_truth': bool(math.hypot(h['x'] - truth[0], h['y'] - truth[1]) <= 0.5 and abs(math.degrees(math.atan2(math.sin(h['yaw'] - truth[2]), math.cos(h['yaw'] - truth[2])))) <= 20)}
                                       for h in hyps]})
        print(json.dumps(results[-1]), flush=True)
    Path(a.output).write_text(json.dumps(results, indent=1))


if __name__ == '__main__':
    main()
