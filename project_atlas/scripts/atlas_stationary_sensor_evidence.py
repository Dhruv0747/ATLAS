#!/usr/bin/env python3
"""Offline stationary-window evidence, never navigation authorization.

Reads one SQLite ROS bag read-only. No ROS node, publishers or services.
Windows are explicit offsets, not discovered from AMCL pose-message counts.
Endpoint and scan-repeatability metrics do not establish unique global pose.
"""
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import numpy as np


def stamp(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def coverage(times, begin, end):
    values = np.asarray(times, dtype=float)
    if not len(values) or not np.all(np.isfinite(values)):
        return {'count': 0, 'max_gap_s': None, 'duplicates': 0, 'regressions': 0}
    delta = np.diff(values)
    ordered = np.sort(values)
    gaps = np.diff(np.concatenate(([begin], ordered, [end])))
    return {'count': len(values), 'max_gap_s': float(max(gaps)),
            'duplicates': int(np.sum(delta == 0)), 'regressions': int(np.sum(delta < 0))}


def pose_span(points):
    if not len(points):
        return None
    p = np.asarray(points)
    headings = np.unwrap(p[:, 2])
    return {'xy_bbox_diagonal_m': float(np.linalg.norm(np.ptp(p[:, :2], axis=0))),
            'yaw_span_deg': float(np.degrees(np.ptp(headings)))}


def latest(series, t):
    index = bisect.bisect_right([row[0] for row in series], t) - 1
    return series[index] if index >= 0 else None


def main():
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from atlas_amcl_stationary_jump_audit import (pose, transform_pose, compose,
        map_model, scan_points, score_scan)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('output')
    parser.add_argument('--window', nargs=2, type=float, action='append', required=True)
    args = parser.parse_args()
    segments = list(Path(args.bag).glob('*.db3'))
    if len(segments) != 1:
        raise ValueError('one SQLite segment required')
    db = sqlite3.connect('file:' + str(segments[0]) + '?mode=ro', uri=True)
    start_ns = db.execute('SELECT MIN(timestamp) FROM messages').fetchone()[0]
    start = start_ns / 1e9
    topics = {name: (i, typ) for i, name, typ in db.execute('SELECT id,name,type FROM topics')}
    names = ['/scan', '/odom', '/yahboom/odom', '/imu/data',
             '/im10a/imu/bias_corrected_candidate', '/amcl_pose', '/tf', '/tf_static', '/map']
    names += ['/yahboom/encoder/m' + str(i) for i in range(1, 5)]
    data = {}
    for name in names:
        data[name] = []
        if name not in topics:
            continue
        ident, typ = topics[name]
        cls = get_message(typ)
        for t, raw in db.execute('SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (ident,)):
            data[name].append((t / 1e9, deserialize_message(raw, cls)))
    if len(data['/map']) != 1:
        raise ValueError('one immutable recorded map required')
    grid = data['/map'][0][1]
    model = map_model(grid)
    static = {}
    dynamic = {}
    for topic in ('/tf_static', '/tf'):
        for received, msg in data[topic]:
            for tf in msg.transforms:
                key = (tf.header.frame_id.strip('/'), tf.child_frame_id.strip('/'))
                if topic == '/tf_static':
                    value = transform_pose(tf.transform)
                    if key in static and not np.allclose(static[key], value):
                        raise ValueError('changing static extrinsics')
                    static[key] = value
                else:
                    dynamic.setdefault(key, []).append((received, stamp(tf), transform_pose(tf.transform)))
    base = static.get(('base_link', 'base_footprint'))
    if base is None or np.linalg.norm(base) > 1e-8:
        raise ValueError('explicit identity base_link/base_footprint required')
    laser = compose(base, static[('base_footprint', 'laser_frame')])
    poses = [(t, pose(m.pose.pose), m) for t, m in data['/amcl_pose']]
    output = {'source_bag': Path(args.bag).name, 'start_ns': start_ns,
              'map_cells_sha256': hashlib.sha256(np.asarray(grid.data, dtype=np.int8).tobytes()).hexdigest(),
              'map_resolution_m': grid.info.resolution, 'laser_in_base': laser.tolist(),
              'navigation_authorized': False, 'windows': [],
              'limitations': ['No surveyed ground truth or global ambiguity search',
                'Scan repeatability is not translation/rotation estimation',
                'Wheel and EKF odometry are correlated, not independent sensors',
                'TF bracket test uses recorded headers available within 0.5 s after scan receipt; not proof of AMCL callback consumption',
                'Encoder scalar messages have receipt time only; stopped counts cannot prove sensor health']}
    for a, b in args.window:
        if not 0 <= a < b:
            raise ValueError('invalid window')
        begin, end = start+a, start+b
        selected = {n: [(t, m) for t, m in rows if begin <= t <= end] for n, rows in data.items()}
        result = {'offset_s': [a,b], 'topics': {}, 'odometry': {}, 'gyro': {}, 'encoders': {}}
        for n in names:
            if n in ('/tf','/tf_static','/map'):
                continue
            rows = selected[n]
            entry = {'receipt': coverage([t for t, _ in rows], begin, end)}
            if rows and hasattr(rows[0][1], 'header'):
                headers = [stamp(m) for _, m in rows]
                entry['header'] = coverage(headers, begin, end)
                ages = [t-stamp(m) for t,m in rows]
                entry['receipt_minus_header_s'] = [float(min(ages)), float(np.median(ages)), float(max(ages))]
                entry['frames'] = sorted({m.header.frame_id for _,m in rows})
            result['topics'][n] = entry
        for n in ('/odom','/yahboom/odom'):
            result['odometry'][n] = pose_span([pose(m.pose.pose) for _,m in selected[n]])
        for n in ('/imu/data','/im10a/imu/bias_corrected_candidate'):
            rows = selected[n]
            if rows:
                z = np.array([m.angular_velocity.z for _,m in rows])
                ts = np.array([stamp(m) for _,m in rows])
                result['gyro'][n] = {'max_abs_z_rad_s': float(np.max(np.abs(z))),
                    'signed_integral_deg': float(np.degrees(np.trapz(z,ts))),
                    'absolute_integral_deg': float(np.degrees(np.trapz(np.abs(z),ts)))}
        for i in range(1,5):
            values = [m.data for _,m in selected['/yahboom/encoder/m'+str(i)]]
            result['encoders']['m'+str(i)] = max(values)-min(values) if values else None
        result['amcl_span'] = pose_span([pose(m.pose.pose) for _,m in selected['/amcl_pose']])
        anchor = latest(poses, begin)
        result['anchor_pose'] = anchor[1].tolist() if anchor else None
        result['anchor_receipt_age_s'] = begin-anchor[0] if anchor else None
        scores, repeats, tf_brackets = [], [], {}
        scan_anchor = selected['/scan'][0][1] if selected['/scan'] else None
        last_sample = -math.inf
        for received, scan in selected['/scan']:
            if received-last_sample < .9:
                continue
            last_sample = received
            if scan.header.frame_id.strip('/') != 'laser_frame':
                raise ValueError('unexpected laser frame')
            s = stamp(scan)
            for key in (('odom','base_link'), ('map','odom')):
                stamps = sorted(t for r,t,_ in dynamic.get(key,[]) if r <= received+.5 and abs(t-s)<=.5)
                bracket = bool(stamps and stamps[0] <= s <= stamps[-1])
                tf_brackets.setdefault('/'.join(key), []).append(bracket)
            if anchor:
                points = scan_points(scan)[::4]
                if len(points) >= 30:
                    score = score_scan(points, anchor[1], laser, model)
                    score['offset_s'] = received-start
                    scores.append(score)
            if (len(scan.ranges)==len(scan_anchor.ranges) and
                    scan.angle_min==scan_anchor.angle_min and scan.angle_increment==scan_anchor.angle_increment):
                x,y = np.asarray(scan.ranges),np.asarray(scan_anchor.ranges)
                valid = np.isfinite(x)&np.isfinite(y)&(x>.3)&(y>.3)&(x<8)&(y<8)
                if np.count_nonzero(valid)>=30:
                    repeats.append(float(np.median(np.abs(x[valid]-y[valid]))))
        result['sampled_scan_map_scores_at_fixed_anchor'] = scores
        result['scan_repeatability_median_abs_range_change_m'] = repeats
        result['tf_bracket_coverage'] = {k: {'covered': sum(v), 'sampled': len(v)} for k,v in tf_brackets.items()}
        output['windows'].append(result)
    Path(args.output).write_text(json.dumps(output, indent=2, allow_nan=False))
    print(json.dumps({'windows': len(output['windows']), 'output': args.output, 'navigation_authorized': False}))


if __name__ == '__main__':
    main()
