#!/usr/bin/env python3
"""Read-only heading-sign test (domain 0). Records for DURATION s while the owner turns the rover LEFT (counter-
clockwise seen from above) about 90 degrees in place, then reports each source's integrated turn. Publishes nothing.
Usage: python3 turn_test.py [DURATION_S]"""
import math, sys, time
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, LaserScan
from nav_msgs.msg import Odometry
from scipy.spatial import cKDTree

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
rclpy.init(); n = rclpy.create_node('atlas_turn_test')
data = {k: [] for k in ('im10a_corr', 'im10a_raw', 'yahboom_imu', 'wheel', 'ekf', 'ekf_yaw', 'scan')}
def now(): return time.monotonic()
n.create_subscription(Imu, '/im10a/imu/bias_corrected_candidate', lambda m: data['im10a_corr'].append((now(), m.angular_velocity.z)), qos_profile_sensor_data)
n.create_subscription(Imu, '/im10a/imu/unvalidated', lambda m: data['im10a_raw'].append((now(), m.angular_velocity.z)), qos_profile_sensor_data)
n.create_subscription(Imu, '/imu/data', lambda m: data['yahboom_imu'].append((now(), m.angular_velocity.z)), qos_profile_sensor_data)
n.create_subscription(Odometry, '/yahboom/odom', lambda m: data['wheel'].append((now(), m.twist.twist.angular.z)), 10)
def on_ekf(m):
    q = m.pose.pose.orientation
    data['ekf'].append((now(), m.twist.twist.angular.z))
    data['ekf_yaw'].append((now(), math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))))
n.create_subscription(Odometry, '/odom', on_ekf, 10)
n.create_subscription(LaserScan, '/scan', lambda m: data['scan'].append((now(), m)), qos_profile_sensor_data)
t0 = now(); last = 0
print(f'RECORDING {DUR:.0f} s — turn LEFT ~90 deg slowly now', flush=True)
while now() - t0 < DUR:
    rclpy.spin_once(n, timeout_sec=0.05)
    if now() - last > 10:
        last = now(); print(f'  {now()-t0:4.0f}s  samples: ' + ', '.join(f'{k} {len(v)}' for k, v in data.items()), flush=True)

def integ(key):
    v = data[key]
    if len(v) < 3: return None
    t = np.array([x for x, _ in v]); w = np.array([y for _, y in v])
    rest = w[: max(3, len(w) // 10)]   # first 10 % as a crude bias reference (rover still at start)
    return math.degrees(float(np.sum(w[1:] * np.diff(t)))), math.degrees(float(np.sum((w[1:] - np.median(rest)) * np.diff(t))))
def pts(s):
    r = np.array(s.ranges, float); a = s.angle_min + np.arange(len(r)) * s.angle_increment
    ok = np.isfinite(r) & (r > 0.15) & (r < 6.0); return np.c_[r[ok] * np.cos(a[ok]), r[ok] * np.sin(a[ok])]
def icp(P, Q, it=30):
    tree = cKDTree(Q); th, tx, ty = 0.0, 0.0, 0.0
    for _ in range(it):
        c, s = math.cos(th), math.sin(th); Pt = P @ np.array([[c, s], [-s, c]]) + [tx, ty]
        dist, idx = tree.query(Pt); m = dist < 0.3
        if m.sum() < 30: return None
        A, B = P[m], Q[idx[m]]; ca, cb = A.mean(0), B.mean(0); H = (A - ca).T @ (B - cb)
        th = math.atan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1]); c, s = math.cos(th), math.sin(th)
        tx, ty = cb - ca @ np.array([[c, s], [-s, c]])
    return th
lidar = 0.0; fails = 0
for (_, a), (_, b) in zip(data['scan'], data['scan'][1:]):
    th = icp(pts(a), pts(b))
    if th is None: fails += 1
    else: lidar += -math.degrees(th)    # laser_frame is base_link rotated 180 deg about z: same turn sign
print('\nRESULT (+ = left / counter-clockwise, ROS convention):')
print(f'  LiDAR scan-to-scan (independent reference): {lidar:+7.1f} deg  ({len(data["scan"])} scans, {fails} ICP failures)')
for k, label in (('yahboom_imu', 'Yahboom IMU gyro /imu/data'), ('im10a_raw', 'IM10A raw /im10a/imu/unvalidated'),
                 ('im10a_corr', 'IM10A corrected (EKF input)'), ('wheel', 'wheel odometry'), ('ekf', 'EKF /odom turn rate')):
    r = integ(k)
    print(f'  {label:34s}: ' + ('no data' if r is None else f'{r[0]:+7.1f} deg (start-bias removed {r[1]:+7.1f})'))
ey = data['ekf_yaw']
if len(ey) > 2:
    y = np.unwrap([v for _, v in ey]); print(f'  {"EKF /odom heading change":34s}: {math.degrees(y[-1] - y[0]):+7.1f} deg')
rclpy.shutdown()
