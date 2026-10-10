#!/usr/bin/env python3
"""Read-only audit of localization behaviour versus motion in a saved drive.

For one rosbag2 SQLite recording, report:

- motion segments from /odom twist (moving / stopped), with speed;
- AMCL publication interval, header-to-receipt latency and covariance
  (XY std, yaw std) per segment, and the dashboard's UNCERTAIN rule
  (XY std > 0.25 m or yaw std > 20 deg, from atlas_localization_display);
- after each stop: AMCL updates and seconds until the rule turns CONFIDENT;
- every AMCL map->odom correction while moving, projected onto the rover's
  direction of travel (positive = AMCL moved the rover forward, i.e. wheel
  odometry under-reported distance), plus its size and timing;
- AMCL pose steps larger than 0.5 m, with odometry motion over the same
  interval.

No ROS node, publisher, service or actuator is created.
"""
import argparse
import json
import math
from pathlib import Path
import sqlite3

MOVING_MPS = 0.03
MOVING_RADPS = 0.05
UNCERTAIN_XY_M = 0.25
UNCERTAIN_YAW_DEG = 20.0
JUMP_M = 0.5


def _decoder():
    try:
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        return lambda raw, typ: deserialize_message(raw, get_message(typ))
    except ImportError:
        from rosbags.typesys import Stores, get_typestore
        return get_typestore(Stores.ROS2_HUMBLE).deserialize_cdr


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def uncertain(xy_std, yaw_std_deg):
    return xy_std > UNCERTAIN_XY_M or yaw_std_deg > UNCERTAIN_YAW_DEG


def segments(samples, moving_mps=MOVING_MPS, moving_radps=MOVING_RADPS, min_s=1.0):
    """Split (t, vx, wz) samples into alternating moving/stopped segments."""
    out = []
    for t, vx, wz in samples:
        state = 'moving' if abs(vx) >= moving_mps or abs(wz) >= moving_radps else 'stopped'
        if out and out[-1]['state'] == state:
            out[-1]['end'] = t
            out[-1]['speeds'].append(abs(vx))
        else:
            out.append({'state': state, 'start': t, 'end': t, 'speeds': [abs(vx)]})
    merged = []
    for seg in out:
        if merged and seg['end'] - seg['start'] < min_s and merged[-1]['state'] != seg['state']:
            merged[-1]['end'] = seg['end']
            merged[-1]['speeds'] += seg['speeds']
        elif merged and merged[-1]['state'] == seg['state']:
            merged[-1]['end'] = seg['end']
            merged[-1]['speeds'] += seg['speeds']
        else:
            merged.append(seg)
    return merged


def median(values):
    v = sorted(values)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('output')
    args = parser.parse_args()
    db_files = list(Path(args.bag).glob('*.db3'))
    if len(db_files) != 1:
        raise ValueError('requires one SQLite segment')
    db = sqlite3.connect('file:' + str(db_files[0]) + '?mode=ro', uri=True)
    decode = _decoder()
    start = db.execute('SELECT MIN(timestamp) FROM messages').fetchone()[0] / 1e9
    topics = {n: (i, t) for i, n, t in db.execute('SELECT id,name,type FROM topics')}

    def rows(name):
        if name not in topics:
            return
        ident, typ = topics[name]
        for received, raw in db.execute(
                'SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (ident,)):
            yield received / 1e9 - start, decode(raw, typ)

    odom = []
    for t, m in rows('/odom'):
        p = m.pose.pose
        odom.append((t, p.position.x, p.position.y, yaw_of(p.orientation),
                     m.twist.twist.linear.x, m.twist.twist.angular.z))
    amcl = []
    for t, m in rows('/amcl_pose'):
        p = m.pose.pose
        c = m.pose.covariance
        stamp = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9 - start
        amcl.append({'t': t, 'latency_s': t - stamp, 'x': p.position.x, 'y': p.position.y,
                     'yaw': yaw_of(p.orientation),
                     'xy_std': math.sqrt(max(0.0, c[0]) + max(0.0, c[7])),
                     'yaw_std_deg': math.degrees(math.sqrt(max(0.0, c[35])))})
    map_odom = []
    for t, m in rows('/tf'):
        for tr in m.transforms:
            if (tr.header.frame_id.strip('/'), tr.child_frame_id.strip('/')) == ('map', 'odom'):
                q = tr.transform.rotation
                map_odom.append((t, tr.transform.translation.x, tr.transform.translation.y, yaw_of(q)))
    if not odom or not amcl:
        raise ValueError('recording needs /odom and /amcl_pose')

    def odom_at(t):
        lo, hi = 0, len(odom) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if odom[mid][0] < t:
                lo = mid + 1
            else:
                hi = mid
        return odom[lo]

    segs = segments([(o[0], o[4], o[5]) for o in odom])
    seg_out = []
    for i, s in enumerate(segs):
        inside = [a for a in amcl if s['start'] <= a['t'] <= s['end']]
        intervals = [b['t'] - a['t'] for a, b in zip(inside, inside[1:])]
        info = {'state': s['state'], 'start_s': round(s['start'], 2), 'end_s': round(s['end'], 2),
                'duration_s': round(s['end'] - s['start'], 2),
                'median_speed_mps': round(median(s['speeds']) or 0.0, 3),
                'max_speed_mps': round(max(s['speeds']), 3),
                'amcl_updates': len(inside),
                'amcl_interval_median_s': None if not intervals else round(median(intervals), 3),
                'amcl_interval_max_s': None if not intervals else round(max(intervals), 3),
                'amcl_latency_median_s': None if not inside else round(median([a['latency_s'] for a in inside]), 3),
                'uncertain_fraction': None if not inside else round(
                    sum(uncertain(a['xy_std'], a['yaw_std_deg']) for a in inside) / len(inside), 3),
                'xy_std_median_m': None if not inside else round(median([a['xy_std'] for a in inside]), 3),
                'yaw_std_median_deg': None if not inside else round(median([a['yaw_std_deg'] for a in inside]), 1)}
        if s['state'] == 'stopped' and inside:
            first_ok = next((k for k, a in enumerate(inside) if not uncertain(a['xy_std'], a['yaw_std_deg'])), None)
            info['entered_uncertain'] = uncertain(inside[0]['xy_std'], inside[0]['yaw_std_deg'])
            info['updates_until_confident'] = first_ok
            info['seconds_until_confident'] = None if first_ok is None else round(inside[first_ok]['t'] - s['start'], 2)
        seg_out.append(info)

    corrections = []
    for a, b in zip(map_odom, map_odom[1:]):
        dx, dy = b[1] - a[1], b[2] - a[2]
        size = math.hypot(dx, dy)
        if size < 0.02 and abs(wrap(b[3] - a[3])) < math.radians(2):
            continue
        o = odom_at(b[0])
        moving = abs(o[4]) >= MOVING_MPS or abs(o[5]) >= MOVING_RADPS
        heading = b[3] + o[3]  # map yaw of base = map->odom yaw + odom yaw
        along = dx * math.cos(heading) + dy * math.sin(heading)
        corrections.append({'t': round(b[0], 2), 'moving': moving, 'speed_mps': round(o[4], 3),
                            'size_m': round(size, 3), 'along_travel_m': round(along, 3),
                            'sideways_m': round(-dx * math.sin(heading) + dy * math.cos(heading), 3),
                            'yaw_deg': round(math.degrees(wrap(b[3] - a[3])), 2)})
    moving_corr = [c for c in corrections if c['moving']]
    forward = [c for c in moving_corr if c['along_travel_m'] > 0]

    jumps = []
    for a, b in zip(amcl, amcl[1:]):
        step = math.hypot(b['x'] - a['x'], b['y'] - a['y'])
        if step <= JUMP_M:
            continue
        oa, ob = odom_at(a['t']), odom_at(b['t'])
        jumps.append({'t': round(b['t'], 2), 'step_m': round(step, 3),
                      'step_deg': round(math.degrees(abs(wrap(b['yaw'] - a['yaw']))), 1),
                      'interval_s': round(b['t'] - a['t'], 2),
                      'odom_moved_m': round(math.hypot(ob[1] - oa[1], ob[2] - oa[2]), 3),
                      'speed_mps': round(ob[4], 3),
                      'xy_std_before': round(a['xy_std'], 3), 'xy_std_after': round(b['xy_std'], 3),
                      'from': [round(a['x'], 3), round(a['y'], 3)], 'to': [round(b['x'], 3), round(b['y'], 3)]})

    result = {
        'source_bag': Path(args.bag).name, 'navigation_authorized': False,
        'duration_s': round(odom[-1][0], 2),
        'thresholds': {'moving_mps': MOVING_MPS, 'moving_radps': MOVING_RADPS,
                       'uncertain_xy_m': UNCERTAIN_XY_M, 'uncertain_yaw_deg': UNCERTAIN_YAW_DEG,
                       'jump_m': JUMP_M},
        'segments': seg_out,
        'corrections_while_moving': {
            'count': len(moving_corr),
            'forward_fraction': None if not moving_corr else round(len(forward) / len(moving_corr), 3),
            'along_travel_sum_m': round(sum(c['along_travel_m'] for c in moving_corr), 3),
            'sideways_sum_m': round(sum(c['sideways_m'] for c in moving_corr), 3),
            'size_median_m': None if not moving_corr else median([c['size_m'] for c in moving_corr]),
            'size_max_m': None if not moving_corr else max(c['size_m'] for c in moving_corr)},
        'corrections': corrections,
        'jumps_over_0_5m': jumps,
    }
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({'output': args.output, 'segments': len(seg_out), 'jumps': len(jumps),
                      'navigation_authorized': False}))


if __name__ == '__main__':
    main()
