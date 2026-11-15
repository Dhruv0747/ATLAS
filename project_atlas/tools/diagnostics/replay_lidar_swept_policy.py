#!/usr/bin/env python3
"""Offline (read-only) replay: old 'arcs need all 72 bins' vs 2026-11-15 swept-path LiDAR availability policy.

For every /scan in a bag: (a) the command actually sent during the drive (/cmd_vel, manual) and (b) a grid of
Nav2-like commands are evaluated as if they came from NAV2. Reports the veto rate of each policy.
Usage: replay_lidar_swept_policy.py <bag_dir> [...]
"""
import bisect, math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'scripts'))
import rosbag2_py
from geometry_msgs.msg import Twist
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import LaserScan
import atlas_lidar_availability as la

GRID = [(0.15, w) for w in (0.0, 0.05, -0.05, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3)] + [(-0.15, 0.0), (-0.15, 0.1)]


def old_required(linear, angular):
    return set(range(72)) if abs(angular) > 1e-4 else la.travel_cone(linear)


def new_required(linear, angular):
    if abs(angular) > 1e-4 and abs(linear) < 1e-4:
        return set(range(72))
    if abs(angular) > 1e-4:
        return la.travel_cone(linear) | la.swept_bins(linear, angular)
    return la.travel_cone(linear)


def bins_of(s):
    b = set()
    for i, d in enumerate(s.ranges):
        if math.isfinite(d) and s.range_min <= d <= s.range_max:
            b.add(int(((math.degrees(s.angle_min + i * s.angle_increment) + 180.0) % 360) // 5) % 72)
    return b


def main(bags):
    for bag in bags:
        r = rosbag2_py.SequentialReader()
        r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
        r.set_filter(rosbag2_py.StorageFilter(topics=['/scan', '/cmd_vel']))
        scans, cmds = [], []
        while r.has_next():
            topic, raw, t = r.read_next()
            if topic == '/scan':
                scans.append((t, bins_of(deserialize_message(raw, LaserScan))))
            else:
                m = deserialize_message(raw, Twist)
                cmds.append((t, m.linear.x, m.angular.z))
        ct = [c[0] for c in cmds]
        real = {'old': 0, 'new': 0, 'n': 0}
        for t, b in scans:
            i = bisect.bisect_right(ct, t) - 1
            if i < 0 or t - cmds[i][0] > 3e8:
                continue
            _, v, w = cmds[i]
            if abs(v) < 0.02:
                continue
            real['n'] += 1
            real['old'] += bool(old_required(v, w) - b)
            real['new'] += bool(new_required(v, w) - b)
        print(f'bag {os.path.basename(bag)}: {len(scans)} scans')
        n = max(1, real['n'])
        print(f"  real driven commands ({real['n']} scans while moving): veto old {100*real['old']/n:.0f} % -> "
              f"new {100*real['new']/n:.0f} %")
        for v, w in GRID:
            o = sum(bool(old_required(v, w) - b) for _, b in scans)
            nn = sum(bool(new_required(v, w) - b) for _, b in scans)
            rad = 'straight' if not w else f'R {v / w:+.2f} m'
            print(f'  v {v:+.2f} w {w:+.2f} ({rad}): veto old {100*o/len(scans):.0f} % -> new {100*nn/len(scans):.0f} %')


if __name__ == '__main__':
    main(sys.argv[1:])
