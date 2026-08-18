#!/usr/bin/env python3
"""Analyze remapped ATLAS teaching topics while ros2 bag play replays them."""

import json
import math
import time
from collections import defaultdict

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Imu, LaserScan


def yaw_of(q) -> float:
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


class Analyzer(Node):
    def __init__(self) -> None:
        super().__init__("atlas_route_replay_analyzer")
        self.samples = defaultdict(list)
        self.scan_stamps = []
        self.last_message = time.monotonic()
        self.received = False
        self.create_subscription(
            Odometry, "/analysis/odom", lambda msg: self.on_odom("fused", msg), 50
        )
        self.create_subscription(
            Odometry,
            "/analysis/yahboom_odom",
            lambda msg: self.on_odom("encoder", msg),
            50,
        )
        self.create_subscription(LaserScan, "/analysis/scan", self.on_scan, 50)
        self.create_subscription(Imu, "/analysis/imu", self.on_imu, 50)

    def touch(self) -> None:
        self.received = True
        self.last_message = time.monotonic()

    def on_odom(self, name: str, msg: Odometry) -> None:
        pose = msg.pose.pose
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        self.samples[name].append(
            (stamp, pose.position.x, pose.position.y, yaw_of(pose.orientation))
        )
        self.touch()

    def on_scan(self, msg: LaserScan) -> None:
        self.scan_stamps.append(msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9)
        self.touch()

    def on_imu(self, msg: Imu) -> None:
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        self.samples["imu"].append((stamp, 0.0, 0.0, yaw_of(msg.orientation)))
        self.touch()


def summarize(samples):
    if not samples:
        return {"samples": 0}
    distance = 0.0
    max_step = 0.0
    yaw_jumps = []
    for first, second in zip(samples, samples[1:]):
        step = math.hypot(second[1] - first[1], second[2] - first[2])
        distance += step
        max_step = max(max_step, step)
        delta = math.atan2(
            math.sin(second[3] - first[3]), math.cos(second[3] - first[3])
        )
        yaw_jumps.append(abs(delta))
    first, last = samples[0], samples[-1]
    return {
        "samples": len(samples),
        "start": [round(first[1], 3), round(first[2], 3), round(math.degrees(first[3]), 2)],
        "end": [round(last[1], 3), round(last[2], 3), round(math.degrees(last[3]), 2)],
        "net_distance_m": round(math.hypot(last[1] - first[1], last[2] - first[2]), 3),
        "integrated_distance_m": round(distance, 3),
        "max_position_step_m": round(max_step, 4),
        "max_yaw_step_deg": round(math.degrees(max(yaw_jumps, default=0.0)), 3),
    }


def main() -> None:
    rclpy.init()
    node = Analyzer()
    started = time.monotonic()
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.2)
        if node.received and time.monotonic() - node.last_message > 2.0:
            break
        if time.monotonic() - started > 45.0:
            break
    result = {name: summarize(values) for name, values in node.samples.items()}
    if len(node.scan_stamps) > 1:
        intervals = sorted(
            second - first
            for first, second in zip(node.scan_stamps, node.scan_stamps[1:])
            if second > first
        )
        result["scan"] = {
            "samples": len(node.scan_stamps),
            "median_period_ms": round(1000 * intervals[len(intervals) // 2], 2),
            "max_period_ms": round(1000 * intervals[-1], 2),
        }
    print(json.dumps(result, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
