#!/usr/bin/env python3
"""Read-only replay: recorded encoder-consensus deltas + recorded mux commands -> what the speed loop would output."""
import sys, json, statistics, bisect
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'scripts'))
import rosbag2_py
from rclpy.serialization import deserialize_message
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from atlas_speed_loop import SpeedLoop
for name, bag in [('auto3 (autonomous 1 m)', '/home/jetson/project_atlas/data/lidar_tests/auto3_1m_20261115'),
                  ('manual sensitivity drive', '/home/jetson/project_atlas/data/lidar_tests/sensitivity_drive_20261115')]:
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'), rosbag2_py.ConverterOptions('cdr', 'cdr'))
    r.set_filter(rosbag2_py.StorageFilter(topics=['/cmd_vel', '/atlas/encoder_health', '/odom']))
    cmd = 0.0; last_t = None; loop = SpeedLoop(); rows = []; od = []
    while r.has_next():
        topic, b, t = r.read_next()
        if topic == '/cmd_vel':
            cmd = deserialize_message(b, Twist).linear.x; continue
        if topic == '/odom':
            od.append((t / 1e9, deserialize_message(b, Odometry).twist.twist.linear.x)); continue
        h = json.loads(deserialize_message(b, String).data)
        ts = t / 1e9
        sel = [i - 1 for i in h.get('selected_encoders', [])]
        deltas = h.get('encoder_interval_delta_m') or [0, 0, 0, 0]
        ok = bool(h.get('packet_fresh')) and len(sel) >= 2
        d = statistics.median([deltas[i] for i in sel]) if sel else 0.0
        dt = (ts - last_t) if last_t else 0.1
        last_t = ts
        # sign: encoder deltas are magnitudes in the commanded direction for this replay
        signed = d if cmd >= 0 else -abs(d)
        pwm = loop.update(cmd, signed, min(max(dt, 0.02), 0.5), ok)
        rows.append((ts, cmd, d / dt if dt > 0 else 0, pwm, loop.last_reason))
    ot = [o[0] for o in od]
    moving = [x for x in rows if abs(x[1]) > 0.02]
    cuts = [x for x in moving if x[4].startswith('overspeed')]
    print(name, '| ticks with a non-zero command', len(moving), '| overspeed cuts', len(cuts),
          '| invalid-feedback ticks', sum(1 for x in moving if x[4] == 'feedback invalid'))
    if moving:
        t0 = moving[0][0]
        first_cut = cuts[0] if cuts else None
        if first_cut:
            j = bisect.bisect_left(ot, first_cut[0]); vod = od[min(j, len(od) - 1)][1]
            print('  first cut %.2f s after the first command; measured (loop window) %.2f m/s, EKF odom %.2f m/s at that moment'
                  % (first_cut[0] - t0, loop.p['overspeed_ratio'] * 0 + first_cut[2], vod))
        if name.startswith('auto3'):
            for x in moving[:14]:
                print('   %5.2f s cmd %.2f tick-speed %.2f -> PWM %3d (%s)' % (x[0] - t0, x[1], x[2], x[3], x[4]))
