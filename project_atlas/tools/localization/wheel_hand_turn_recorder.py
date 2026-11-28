#!/usr/bin/env python3
"""Read-only recorder for the wheels-off-ground hand-turn test (no commands are published).
Subscribes to /yahboom/encoder/m1..m4 (Int32 raw counts), remembers the first count of each wheel,
and every 2 s writes the change since start, in counts and in wheel turns using the configured CPR,
to /tmp/hand_turn_status.txt (and a CSV log). Stops when /tmp/hand_turn_stop exists or after 15 min.
"""
import os
import time

import rclpy
import yaml
from std_msgs.msg import Int32

CAL = yaml.safe_load(open(os.path.expanduser('~/project_atlas/config/encoder_calibration.yaml')))['encoder_calibration']
POS = {k: v['position'] for k, v in CAL['motors'].items()}
CPR = {k: v['counts_per_revolution'] for k, v in CAL['motors'].items()}
SIGN = {k: v['encoder_sign'] for k, v in CAL['motors'].items()}
first, last, n = {}, {}, {k: 0 for k in CPR}


def cb(k):
    def f(m):
        first.setdefault(k, m.data); last[k] = m.data; n[k] += 1
    return f


rclpy.init(); node = rclpy.create_node('atlas_hand_turn_recorder')
for k in CPR: node.create_subscription(Int32, f'/yahboom/encoder/{k}', cb(k), 50)
t0 = time.time(); nxt = t0; log = open('/tmp/hand_turn_log.csv', 'w'); log.write('t,wheel,count\n')
try:
    while rclpy.ok() and not os.path.exists('/tmp/hand_turn_stop') and time.time() - t0 < 900:
        rclpy.spin_once(node, timeout_sec=0.1)
        if time.time() >= nxt:
            nxt += 2.0; lines = [f'{time.strftime("%H:%M:%S")}  ({time.time()-t0:.0f} s)']
            for k in sorted(CPR):
                if k not in first: lines.append(f'{k} {POS[k]:12s}: no data yet'); continue
                dc = last[k] - first[k]; log.write(f'{time.time():.2f},{k},{last[k]}\n')
                lines.append(f'{k} {POS[k]:12s}: change {dc:+8d} counts = {dc / CPR[k]:+7.2f} turns '
                             f'(forward-signed {SIGN[k] * dc / CPR[k]:+7.2f}) | msgs {n[k]}')
            open('/tmp/hand_turn_status.txt', 'w').write('\n'.join(lines) + '\n'); log.flush()
finally:
    node.destroy_node(); rclpy.shutdown()
