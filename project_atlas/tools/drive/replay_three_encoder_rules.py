#!/usr/bin/env python3
"""Offline replay (read-only) of candidate 3-encoder consensus rules on a recorded bag. 2026-11-15.

Uses the per-interval, wheel-path-normalized deltas the live base publishes in /atlas/encoder_health
('encoder_interval_delta_m'), drops M3 (simulating excluded_encoders: [3]) and compares rules on:
  * fail fraction of moving intervals (CRITICAL ticks -> speed scale 0),
  * longest continuous fail run (s),
  * integrated distance vs LiDAR ICP path length (/lidar/icp_odom).
Usage: replay_three_encoder_rules.py <bag_dir>
"""
import json, math, statistics, sys

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'scripts'))
import rosbag2_py
from nav_msgs.msg import Odometry
from rclpy.serialization import deserialize_message
from std_msgs.msg import String

KEEP = (0, 1, 3)               # M1, M2, M4
REL, ABS = 0.45, 0.004         # live EncoderDeltaEstimator tolerances


def agree(a, b):
    return abs(a - b) <= max(ABS, REL * max(abs(a), abs(b)))


def rule_all3(d):
    v = [d[i] for i in KEEP]
    ok = all(agree(v[i], v[j]) for i in range(3) for j in range(i + 1, 3)) or \
        any(all(agree(c, x) for x in v) for c in v)
    return statistics.median(v) if ok else None


def rule_2of3(d):
    v = [d[i] for i in KEEP]
    if rule_all3(d) is not None:
        return statistics.median(v)
    pairs = [(abs(v[i] - v[j]), (v[i] + v[j]) / 2) for i in range(3) for j in range(i + 1, 3) if agree(v[i], v[j])]
    # a pair must also share the direction of motion and not both be ~zero while the third moves
    pairs = [p for p in pairs if True]
    return min(pairs)[1] if pairs else None


def main(bag):
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
    r.set_filter(rosbag2_py.StorageFilter(topics=['/atlas/encoder_health', '/lidar/icp_odom']))
    ticks, icp = [], []
    while r.has_next():
        topic, raw, t = r.read_next()
        if topic == '/lidar/icp_odom':
            p = deserialize_message(raw, Odometry).pose.pose.position
            icp.append((t / 1e9, p.x, p.y))
        else:
            m = json.loads(deserialize_message(raw, String).data)
            d = m.get('encoder_interval_delta_m') or [0, 0, 0, 0]
            ticks.append((t / 1e9, bool(m.get('traction')), d, m.get('state')))
    lidar_path = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(icp, icp[1:])
                     if math.hypot(b[1] - a[1], b[2] - a[2]) < 0.5)
    moving = [x for x in ticks if x[1] and max(abs(x[2][i]) for i in KEEP) > 1e-6]
    print(f'bag {bag}\n ticks {len(ticks)}, moving intervals {len(moving)}, LiDAR ICP path {lidar_path:.2f} m')
    from atlas_encoder_selection import EncoderDeltaEstimator
    est = EncoderDeltaEstimator(); cum = [0.0] * 4; est.update(cum, KEEP)

    def rule_live_new(d):                       # the edited live estimator, fed the same normalized deltas
        for i in range(4):
            cum[i] += d[i]
        v = est.update(list(cum), KEEP)
        return v if est.last_accepted else None
    rules = {'old: all 3 agree (live rule, M3 excluded)': rule_all3, 'approx: 2 of 3 agree': rule_2of3,
             'NEW live estimator (coherent pair, stalled guard)': rule_live_new}
    for name, fn in rules.items():
        dist, fails, run, worst, last_t = 0.0, 0, 0.0, 0.0, None
        for t, _, d, _ in moving:
            v = fn(d)
            if v is None:
                fails += 1
                run = run + (t - last_t if last_t is not None and t - last_t < 0.5 else 0.1)
                worst = max(worst, run)
            else:
                dist += abs(v); run = 0.0
            last_t = t
        # persistence variants for the old rule: CRITICAL only if failing continuously > N s
        print(f' {name}: fail {fails}/{len(moving)} = {100.0 * fails / max(1, len(moving)):.1f} % of moving '
              f'intervals, longest fail run {worst:.2f} s, distance {dist:.2f} m '
              f'({100.0 * (dist - lidar_path) / max(lidar_path, 1e-9):+.1f} % vs LiDAR)')
    for hold in (0.3, 0.5, 1.0):
        crit, run, last_t, runs = 0, 0.0, None, 0
        for t, _, d, _ in moving:
            if rule_2of3(d) is None:
                run = run + (t - last_t if last_t is not None and t - last_t < 0.5 else 0.1)
                if run > hold:
                    crit += 1
            else:
                run = 0.0
            last_t = t
        print(f'  2-of-3 + CRITICAL only after {hold:.1f} s without agreement: CRITICAL ticks {crit}')
    # per-channel bias vs the 3-channel median (systematic scale differences)
    for i, name in zip(KEEP, ('M1', 'M2', 'M4')):
        tot = sum(abs(d[i]) for _, _, d, _ in moving)
        print(f'  {name}: summed |delta| {tot:.2f} m')


if __name__ == '__main__':
    main(sys.argv[1])
