#!/usr/bin/env python3
"""Sweep a pose along the robot's forward and sideways axes on one saved scan.

Read-only. For each offset, report the nav2_amcl 1.1.20 likelihood-field
weight factor (as reimplemented in atlas_amcl_weak_hypothesis_trace) and the
held-out fit of odd original beams (fraction within 15 cm of a mapped wall).
Also report the first published particle clouds and odometry movement before
a chosen time, to show whether AMCL entered the recording already converged.
No ROS node, publisher, service or actuator is created.
"""
import argparse
import json
import math
from pathlib import Path
import sqlite3

import numpy as np

from atlas_amcl_diversity_summary import endpoint_fit, load_scene, odd_beam_points
from atlas_amcl_weak_hypothesis_trace import AMCL, _pose, _reader, distance_field, likelihood_field


def offset_pose(pose, forward_m, left_m):
    """Pose moved in its own frame; heading unchanged."""
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return np.array((pose[0] + c * forward_m - s * left_m, pose[1] + s * forward_m + c * left_m, pose[2]))


def peak(rows, key):
    best = max(rows, key=lambda r: r[key])
    return {'offset_m': best['offset_m'], key: best[key]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('output')
    parser.add_argument('--pose', nargs=3, type=float, required=True, metavar=('X', 'Y', 'YAW_RAD'))
    parser.add_argument('--scan-after-s', type=float, required=True)
    parser.add_argument('--history-until-s', type=float, required=True)
    parser.add_argument('--range-m', type=float, default=0.8)
    parser.add_argument('--step-m', type=float, default=0.05)
    args = parser.parse_args()
    segments = list(Path(args.bag).glob('*.db3'))
    if len(segments) != 1:
        raise ValueError('requires one SQLite segment')
    db = sqlite3.connect('file:' + str(segments[0]) + '?mode=ro', uri=True)
    decode = _reader(segments[0])
    start = db.execute('SELECT MIN(timestamp) FROM messages').fetchone()[0] / 1e9
    topics = {n: (i, t) for i, n, t in db.execute('SELECT id,name,type FROM topics')}

    def rows(name):
        ident, typ = topics[name]
        for received, raw in db.execute(
                'SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (ident,)):
            yield received / 1e9 - start, decode(raw, typ)

    grid_msg = next(rows('/map'))[1]
    info = grid_msg.info
    cells = np.asarray(grid_msg.data, dtype=np.int16).reshape(info.height, info.width)
    field = distance_field(cells == 100, info.resolution, AMCL['laser_likelihood_max_dist'])
    origin = (info.origin.position.x, info.origin.position.y)
    tree, laser, scans = load_scene(args.bag)
    received, scan = next((t, m) for t, m in scans if t >= args.scan_after_s)
    model_scan = (scan.angle_min, scan.angle_increment, np.asarray(scan.ranges, dtype=float),
                  scan.range_min, scan.range_max)
    held_out = odd_beam_points(scan.angle_min, scan.angle_increment, scan.ranges,
                               scan.range_min, scan.range_max)
    base = np.array(args.pose)
    offsets = np.round(np.arange(-args.range_m, args.range_m + 1e-9, args.step_m), 4)

    def sweep(axis):
        out = []
        for off in offsets:
            p = offset_pose(base, off, 0.0) if axis == 'forward' else offset_pose(base, 0.0, off)
            out.append({'offset_m': float(off),
                        'amcl_likelihood': float(likelihood_field(p[None], model_scan, laser, field, origin, info.resolution)[0]),
                        'held_out_fit': endpoint_fit(held_out, p, laser, tree)[0]})
        return out

    forward = sweep('forward')
    best_forward = peak(forward, 'amcl_likelihood')['offset_m']
    side_base = offset_pose(base, best_forward, 0.0)
    side = []
    for off in offsets:
        p = offset_pose(side_base, 0.0, off)
        side.append({'offset_m': float(off),
                     'amcl_likelihood': float(likelihood_field(p[None], model_scan, laser, field, origin, info.resolution)[0]),
                     'held_out_fit': endpoint_fit(held_out, p, laser, tree)[0]})
    odom = [(t, np.array(_pose(m.pose.pose))) for t, m in rows('/odom') if t <= args.history_until_s]
    clouds = []
    for t, m in rows('/particle_cloud'):
        if t > args.history_until_s or len(clouds) >= 3:
            break
        p = np.array([_pose(q.pose) for q in m.particles])
        clouds.append({'receipt_s': round(t, 3), 'particles': len(p),
                       'unique_at_1e_minus_6': int(len(np.unique(np.round(p, 6), axis=0))),
                       'mean_xy': [float(v) for v in p[:, :2].mean(axis=0)],
                       'std_xy_m': [float(v) for v in p[:, :2].std(axis=0)]})
    first_pose = next(((t, _pose(m.pose.pose)) for t, m in rows('/amcl_pose')), None)
    result = {
        'source_bag': Path(args.bag).name, 'navigation_authorized': False,
        'base_pose': base.tolist(), 'scan_receipt_s': round(received, 3),
        'forward_sweep': forward, 'forward_peak': peak(forward, 'amcl_likelihood'),
        'side_sweep_at_forward_peak': side, 'side_peak': peak(side, 'amcl_likelihood'),
        'best_pose': offset_pose(side_base, peak(side, 'amcl_likelihood')['offset_m'], 0.0).tolist(),
        'first_amcl_pose': None if first_pose is None else {'receipt_s': round(first_pose[0], 3), 'pose': list(first_pose[1])},
        'max_odometry_displacement_before_m': float(max(np.hypot(*(p[:2] - odom[0][1][:2])) for _, p in odom)) if odom else None,
        'first_clouds': clouds,
        'limitations': ['One scan; likelihood is a reimplementation checked against the C++ harness, not AMCL internal state',
                        'Held-out fit uses unused beams of the same scan, not surveyed position',
                        'Events before the recording started (seeding, AMCL restart) are not visible in the bag'],
    }
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({'output': args.output, 'forward_peak': result['forward_peak'],
                      'side_peak': result['side_peak'], 'navigation_authorized': False}))


if __name__ == '__main__':
    main()
