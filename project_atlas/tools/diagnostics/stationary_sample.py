#!/usr/bin/env python3
"""Read-only stationary sample of odometry, IMU, scan and AMCL topics (subscribes only).

Usage: stationary_sample.py [seconds]   (default 60). Prints JSON: rate, worst gap, net
position/yaw change per odometry source, gyro-Z mean/std per IMU. Only meaningful when the
rover is confirmed parked for the whole window: check /yahboom/odom dxy is 0 and that no drive
events appear in data/safety/estop_events.jsonl during the sample.
"""
import json
import math
import sys
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, LaserScan
from std_msgs.msg import String

ODOM = ['/odom', '/yahboom/odom', '/lidar/odom', '/lidar/odom_raw', '/odom/lidar_fused_candidate']
IMUS = ['/imu/data', '/yahboom/imu/data_calibrated', '/im10a/imu/unvalidated', '/im10a/imu/bias_corrected_candidate']


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def wrap_deg(a):
    return math.degrees(math.atan2(math.sin(a), math.cos(a)))


class Sampler(Node):
    def __init__(self):
        super().__init__('atlas_readonly_stationary_sample')
        self.d = {}
        for t in ODOM:
            self.create_subscription(Odometry, t, lambda m, t=t: self.pose(t, m.pose.pose), qos_profile_sensor_data)
        for t in IMUS:
            self.create_subscription(Imu, t, lambda m, t=t: self.imu(t, m), qos_profile_sensor_data)
        self.create_subscription(LaserScan, '/scan', lambda m: self.stamp('/scan'), qos_profile_sensor_data)
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', lambda m: self.pose('/amcl_pose', m.pose.pose), 10)
        self.create_subscription(String, '/atlas/encoder_health', lambda m: self.d.__setitem__('encoder_health', m.data[:400]), 10)

    def stamp(self, t):
        e = self.d.setdefault(t, {'t': []})
        e['t'].append(time.monotonic())
        return e

    def pose(self, t, p):
        e = self.stamp(t)
        v = (p.position.x, p.position.y, yaw(p.orientation))
        e.setdefault('first', v)
        e['last'] = v

    def imu(self, t, m):
        e = self.stamp(t)
        e.setdefault('gz', []).append(m.angular_velocity.z)
        y = yaw(m.orientation)
        e.setdefault('y0', y)
        e['y1'] = y


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    rclpy.init()
    node = Sampler()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    out = {'duration_s': seconds, 'wall': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    for k, e in node.d.items():
        if not isinstance(e, dict):
            out[k] = e
            continue
        ts = e['t']
        r = {'n': len(ts)}
        if len(ts) > 1:
            r['hz'] = round((len(ts) - 1) / (ts[-1] - ts[0]), 2)
            r['max_gap_s'] = round(max(b - a for a, b in zip(ts, ts[1:])), 3)
        if 'first' in e:
            f, l = e['first'], e['last']
            r['dxy_m'] = round(math.hypot(l[0] - f[0], l[1] - f[1]), 4)
            r['dyaw_deg'] = round(wrap_deg(l[2] - f[2]), 3)
        if 'gz' in e:
            gz = e['gz']
            mu = sum(gz) / len(gz)
            r['gz_mean_dps'] = round(math.degrees(mu), 4)
            r['gz_std_dps'] = round(math.degrees((sum((x - mu) ** 2 for x in gz) / len(gz)) ** 0.5), 4)
            r['orient_dyaw_deg'] = round(wrap_deg(e['y1'] - e['y0']), 3)
        out[k] = r
    print(json.dumps(out, indent=1))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
