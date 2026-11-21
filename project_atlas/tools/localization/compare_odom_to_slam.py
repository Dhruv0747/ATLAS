#!/usr/bin/env python3
"""Offline: how far each odometry drifts from the SLAM pose during a recorded mapping drive.
SLAM pose = map->odom (bag /tf) composed with the live odom->base_link pose (bag /odom).
Each odometry CSV (stamp,yaw,x,y) is rigidly aligned to SLAM at the first moving moment, then the
position error vs SLAM is reported. Big drift = big correction SLAM must apply (map->odom jumps).
Usage: compare_odom_to_slam.py BAG CSV_DIR"""
import math
import sys
import time

import numpy as np

sys.path.insert(0, '/tmp')
import analyze_drive_bag as A  # noqa: E402

bag, D = sys.argv[1], sys.argv[2]
d = A.read_bag(bag, ['/tf', '/odom', '/yahboom/odom'])
mo = []
for t, m in d['/tf']:
    for tr in m.transforms:
        if tr.header.frame_id == 'map' and tr.child_frame_id == 'odom':
            mo.append((t, tr.transform.translation.x, tr.transform.translation.y, A.yaw_of(tr.transform.rotation)))
mo = np.array(mo)
od = np.array([(t, m.pose.pose.position.x, m.pose.pose.position.y, A.yaw_of(m.pose.pose.orientation)) for t, m in d['/odom']])
ts = od[:, 0]
mx, my = np.interp(ts, mo[:, 0], mo[:, 1]), np.interp(ts, mo[:, 0], mo[:, 2])
myaw = np.interp(ts, mo[:, 0], np.unwrap(mo[:, 3]))
sx = mx + np.cos(myaw) * od[:, 1] - np.sin(myaw) * od[:, 2]
sy = my + np.sin(myaw) * od[:, 1] + np.cos(myaw) * od[:, 2]
syaw = myaw + np.unwrap(od[:, 3])
wv = np.array([(t, m.twist.twist.linear.x) for t, m in d['/yahboom/odom']])
moving = wv[np.abs(wv[:, 1]) > 0.03, 0]
t0 = moving[0] - 1.0 if len(moving) else ts[0]
path = np.r_[0, np.cumsum(np.hypot(np.diff(sx), np.diff(sy)))]
print(f'SLAM path length {path[-1]:.2f} m over {ts[-1]-ts[0]:.0f} s; alignment at {time.strftime("%H:%M:%S", time.localtime(t0))}')


def report(name, a):
    t, yaw, x, y = a[:, 0], np.unwrap(a[:, 1]), a[:, 2], a[:, 3]
    i = np.searchsorted(t, t0); j = np.searchsorted(ts, t0)
    dyaw = syaw[j] - yaw[i]; c, s = math.cos(dyaw), math.sin(dyaw)
    X = sx[j] + c * (x - x[i]) - s * (y - y[i]); Y = sy[j] + s * (x - x[i]) + c * (y - y[i])
    ex = np.interp(ts, t, X) - sx; ey = np.interp(ts, t, Y) - sy; e = np.hypot(ex, ey)
    ey_deg = np.degrees(np.interp(ts, t, yaw + dyaw) - syaw)
    k = ts >= t0
    print(f'  {name:8s}: position error vs SLAM max {e[k].max():.2f} m, final {e[-1]:.2f} m, per 10 m of path '
          f'{10*e[-1]/max(path[-1],1e-3):.2f} m | heading error max {np.abs(ey_deg[k]).max():.1f} deg, final {ey_deg[-1]:+.1f} deg')


for name in ('current', 'wheelimu', 'rf2o', 'lidar'):
    try:
        a = np.loadtxt(f'{D}/{name}.csv', delimiter=',', ndmin=2)
        if len(a) > 10: report(name, a)
        else: print(f'  {name}: too few rows ({len(a)})')
    except Exception as ex:
        print(f'  {name}: {ex}')
live = np.c_[od[:, 0], od[:, 3], od[:, 1], od[:, 2]]
report('live/odom', live)
