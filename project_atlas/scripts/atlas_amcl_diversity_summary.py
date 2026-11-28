#!/usr/bin/env python3
"""Summarise atlas_amcl_diversity_experiment results with the handoff metrics.

Read-only. Reports, per policy: recovery to the reference region, AMCL jump
count, maximum jump, stopped-position stability (pose span over the last
30 s), heading error and held-out scan fit (odd original beam indices on
recorded scans, never used by AMCL's 60-beam subsample selection logic here).
The reference pose is a retrospective same-bag scan fit, not ground truth.
No ROS node, publisher, service or actuator is created.
"""
import argparse
import json
import math
from pathlib import Path
import sqlite3

import numpy as np

SUPPORT_RADIUS_M = 0.5
SUPPORT_YAW_DEG = 20.0
# Held-out evaluation windows (bag offsets, s) from the competing-pose report.
HELD_OUT = {0: (110, 118), 1: (270, 278), 2: (450, 458)}


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def recovered(pose, reference, radius=SUPPORT_RADIUS_M, yaw_deg=SUPPORT_YAW_DEG):
    return (math.hypot(pose[0] - reference[0], pose[1] - reference[1]) <= radius and
            abs(math.degrees(wrap(pose[2] - reference[2]))) <= yaw_deg)


def last_span(trajectory, seconds=30.0):
    """Largest XY distance between any two winner poses in the final window."""
    if not trajectory:
        raise ValueError('empty trajectory')
    end = trajectory[-1]['time_s']
    poses = np.array([p['pose'][:2] for p in trajectory if p['time_s'] >= end - seconds])
    diff = poses[:, None, :] - poses[None, :, :]
    return float(np.sqrt((diff ** 2).sum(-1)).max())


def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return np.array((a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], a[2] + b[2]))


def odd_beam_points(angle_min, increment, ranges, range_min, range_max):
    """Original odd beam indices, split before invalid-range filtering."""
    ranges = np.asarray(ranges, dtype=float)
    idx = np.arange(len(ranges))
    ok = (idx % 2 == 1) & np.isfinite(ranges) & (ranges >= max(.3, range_min)) & (ranges <= min(8., range_max))
    angles = angle_min + idx[ok] * increment
    return np.column_stack((ranges[ok] * np.cos(angles), ranges[ok] * np.sin(angles)))


def endpoint_fit(points, robot_pose, laser_in_base, tree):
    laser = compose(robot_pose, laser_in_base)
    c, s = math.cos(laser[2]), math.sin(laser[2])
    world = points @ np.array(((c, s), (-s, c))) + laser[:2]
    distances, _ = tree.query(world)
    return float(np.mean(distances <= .15)), float(np.median(distances))


def _decode():
    try:
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        return lambda raw, typ: deserialize_message(raw, get_message(typ))
    except ImportError:
        from rosbags.typesys import Stores, get_typestore
        return get_typestore(Stores.ROS2_HUMBLE).deserialize_cdr


def load_scene(bag):
    from scipy.spatial import cKDTree
    segments = list(Path(bag).glob('*.db3'))
    if len(segments) != 1:
        raise ValueError('requires one SQLite segment')
    db = sqlite3.connect('file:' + str(segments[0]) + '?mode=ro', uri=True)
    decode = _decode()
    start = db.execute('SELECT MIN(timestamp) FROM messages').fetchone()[0] / 1e9
    topics = {n: (i, t) for i, n, t in db.execute('SELECT id,name,type FROM topics')}

    def rows(name):
        ident, typ = topics[name]
        for received, raw in db.execute(
                'SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (ident,)):
            yield received / 1e9 - start, decode(raw, typ)

    grid = next(rows('/map'))[1]
    info = grid.info
    cells = np.asarray(grid.data, dtype=np.int16).reshape(info.height, info.width)
    ys, xs = np.nonzero(cells >= 65)
    occupied = np.column_stack(((xs + .5) * info.resolution + info.origin.position.x,
                                (ys + .5) * info.resolution + info.origin.position.y))
    laser = None
    for _, msg in rows('/tf_static'):
        for tr in msg.transforms:
            if (tr.header.frame_id.strip('/'), tr.child_frame_id.strip('/')) == ('base_footprint', 'laser_frame'):
                q = tr.transform.rotation
                laser = np.array((tr.transform.translation.x, tr.transform.translation.y,
                                  math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))))
    if laser is None:
        raise ValueError('laser transform missing')
    scans = [(t, m) for t, m in rows('/scan')]
    return cKDTree(occupied), laser, scans


def held_out_points(scans, window):
    chosen, last = [], -math.inf
    for t, m in scans:
        if window[0] <= t <= window[1] and t - last >= .9:
            pts = odd_beam_points(m.angle_min, m.angle_increment, m.ranges, m.range_min, m.range_max)
            if len(pts) >= 30:
                chosen.append(pts)
                last = t
    if not chosen:
        raise ValueError('no held-out scans in window')
    return chosen


def summarize(document, window_index, tree, laser, scans):
    reference = document['reference_pose']
    held = held_out_points(scans, HELD_OUT[window_index])

    def fit(pose):
        scores = [endpoint_fit(p, np.array(pose), laser, tree) for p in held]
        return {'within_15cm_median': float(np.median([s[0] for s in scores])),
                'wall_distance_median_m': float(np.median([s[1] for s in scores]))}

    policies = {}
    for row in document['results']:
        policies.setdefault(row['mode'], []).append(row)
    out = {'reference_pose': reference, 'reference_is_ground_truth': False,
           'held_out_scans': len(held), 'held_out_offsets_s': HELD_OUT[window_index],
           'reference_held_out_fit': fit(reference), 'policies': {}}
    for mode, rows in policies.items():
        finals = [r['final']['pose'] for r in rows]
        ok = [recovered(p, reference) for p in finals]
        out['policies'][mode] = {
            'runs': len(rows),
            'recovered_to_reference': int(sum(ok)),
            'jumps_median': float(np.median([r['jumps_over_0_5m'] for r in rows])),
            'jumps_max': int(max(r['jumps_over_0_5m'] for r in rows)),
            'max_jump_m': float(max(r['max_step_m'] for r in rows)),
            'last_30s_span_m_median': float(np.median([last_span(r['trajectory']) for r in rows])),
            'last_30s_span_m_max': float(max(last_span(r['trajectory']) for r in rows)),
            'final_xy_error_m_median': float(np.median([math.hypot(p[0]-reference[0], p[1]-reference[1]) for p in finals])),
            'final_heading_error_deg_median': float(np.median([abs(math.degrees(wrap(p[2]-reference[2]))) for p in finals])),
            'held_out_fit_median_of_runs': float(np.median([fit(p)['within_15cm_median'] for p in finals])),
            'held_out_fit_recovered_runs': float(np.median([fit(p)['within_15cm_median'] for p, k in zip(finals, ok) if k])) if any(ok) else None,
            'held_out_fit_unrecovered_runs': float(np.median([fit(p)['within_15cm_median'] for p, k in zip(finals, ok) if not k])) if not all(ok) else None,
        }
    return out


def check_invariants(document):
    rows = document['results']
    initial = rows[0]['initial']
    for row in rows:
        assert row['initial'] == initial, 'A/B initial states differ'
        assert row['updates'] == len(row['trajectory']) and row['final'] == row['trajectory'][-1]
        for point in row['trajectory']:
            assert all(math.isfinite(v) for v in point['pose'])
        if row['mode'] == 'parked_gate':
            assert row['resamples'] == 0 and all(p['pose'] == initial['pose'] for p in row['trajectory'])
        else:
            assert row['resamples'] == row['updates']
    gate = [r['trajectory'] for r in rows if r['mode'] == 'parked_gate']
    assert all(t == gate[0] for t in gate), 'parked gate must not depend on RNG'
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('output')
    parser.add_argument('results', nargs='+', help='window_index=results.json')
    parser.add_argument('--repeat', nargs=2, metavar=('A', 'B'),
                        help='two independent runs with identical seeds that must match exactly')
    args = parser.parse_args()
    tree, laser, scans = load_scene(args.bag)
    summary = {'source_bag': Path(args.bag).name, 'navigation_authorized': False, 'windows': {}}
    runs = 0
    for item in args.results:
        index, path = item.split('=', 1)
        document = json.loads(Path(path).read_text())
        runs += check_invariants(document)
        summary['windows'][index] = {'window_offset_s': document['window_offset_s'],
                                     **summarize(document, int(index), tree, laser, scans)}
    if args.repeat:
        a, b = (json.loads(Path(p).read_text())['results'] for p in args.repeat)
        common = {(r['mode'], r['seed']) for r in a} & {(r['mode'], r['seed']) for r in b}
        pick = lambda rows: {(r['mode'], r['seed']): r for r in rows if (r['mode'], r['seed']) in common}
        assert common and pick(a) == pick(b), 'same-seed repeat differs'
        summary['repeat_checked_runs'] = len(common)
    summary['invariant_checked_runs'] = runs
    Path(args.output).write_text(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps({'output': args.output, 'runs': runs, 'navigation_authorized': False}))


if __name__ == '__main__':
    main()
