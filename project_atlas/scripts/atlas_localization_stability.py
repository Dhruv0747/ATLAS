#!/usr/bin/env python3
"""Measure stationary AMCL and LiDAR stability without commanding ATLAS."""

import argparse
import json
import math
import statistics
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_srvs.srv import Empty


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * q.z * q.z)


class Monitor(Node):
    def __init__(self):
        super().__init__("atlas_localization_stability")
        self.poses = []
        self.scan_ages_ms = []
        self.scan_nearest = []
        self.update_client = self.create_client(Empty, "/request_nomotion_update")
        self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self.pose, 50)
        self.create_subscription(LaserScan, "/scan", self.scan, 50)
        self.create_timer(2.0, self.request_update)

    def request_update(self):
        if self.update_client.service_is_ready():
            self.update_client.call_async(Empty.Request())

    def pose(self, msg):
        p = msg.pose.pose
        self.poses.append((
            time.time(), p.position.x, p.position.y, yaw_of(p.orientation),
            msg.pose.covariance[0], msg.pose.covariance[7], msg.pose.covariance[35],
        ))

    def scan(self, msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        self.scan_ages_ms.append((self.get_clock().now().nanoseconds / 1e9 - stamp) * 1000.0)
        finite = [value for value in msg.ranges if math.isfinite(value) and value > 0.0]
        if finite:
            self.scan_nearest.append(min(finite))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=45.0)
    args = parser.parse_args()
    rclpy.init()
    node = Monitor()
    deadline = time.monotonic() + max(5.0, args.duration)
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    poses = node.poses
    steps = []
    yaw_steps = []
    for first, second in zip(poses, poses[1:]):
        steps.append(math.hypot(second[1] - first[1], second[2] - first[2]))
        yaw_steps.append(abs(math.atan2(math.sin(second[3] - first[3]), math.cos(second[3] - first[3]))))
    result = {
        "duration_s": args.duration,
        "amcl_samples": len(poses),
        "start": ({"x": poses[0][1], "y": poses[0][2], "yaw_deg": math.degrees(poses[0][3])} if poses else None),
        "end": ({"x": poses[-1][1], "y": poses[-1][2], "yaw_deg": math.degrees(poses[-1][3])} if poses else None),
        "max_pose_step_m": max(steps, default=None),
        "max_yaw_step_deg": math.degrees(max(yaw_steps)) if yaw_steps else None,
        "position_span_m": (math.hypot(max(p[1] for p in poses)-min(p[1] for p in poses), max(p[2] for p in poses)-min(p[2] for p in poses)) if poses else None),
        "covariance_latest": ({"x": poses[-1][4], "y": poses[-1][5], "yaw": poses[-1][6]} if poses else None),
        "scan_samples": len(node.scan_ages_ms),
        "scan_age_median_ms": statistics.median(node.scan_ages_ms) if node.scan_ages_ms else None,
        "scan_age_max_ms": max(node.scan_ages_ms, default=None),
        "nearest_scan_m": min(node.scan_nearest, default=None),
    }
    print(json.dumps(result, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
