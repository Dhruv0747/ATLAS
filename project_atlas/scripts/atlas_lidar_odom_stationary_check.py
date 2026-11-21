#!/usr/bin/env python3
"""Measure stationary drift of raw, gated, and fused LiDAR odometry."""

from __future__ import annotations

import argparse
import json
import math
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import String


def yaw_of(message: Odometry) -> float:
    q = message.pose.pose.orientation
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class Collector(Node):
    def __init__(self) -> None:
        super().__init__("atlas_lidar_odom_stationary_check")
        self.samples = {"raw": [], "gated": [], "fused": []}
        self.health = None
        self.create_subscription(Odometry, "/lidar/odom_raw", lambda msg: self.add("raw", msg), 20)
        self.create_subscription(Odometry, "/lidar/odom", lambda msg: self.add("gated", msg), 20)
        self.create_subscription(
            Odometry, "/odom/lidar_fused_candidate", lambda msg: self.add("fused", msg), 20
        )
        self.create_subscription(String, "/lidar/odom/health", self.on_health, 10)

    def add(self, name: str, message: Odometry) -> None:
        self.samples[name].append(
            (message.pose.pose.position.x, message.pose.pose.position.y, yaw_of(message))
        )

    def on_health(self, message: String) -> None:
        try:
            self.health = json.loads(message.data)
        except json.JSONDecodeError:
            self.health = {"raw": message.data}


def summarize(samples):
    if len(samples) < 2:
        return {"samples": len(samples), "available": False}
    first, last = samples[0], samples[-1]
    return {
        "samples": len(samples),
        "available": True,
        "translation_drift_m": math.hypot(last[0] - first[0], last[1] - first[1]),
        "yaw_drift_deg": math.degrees(
            math.atan2(math.sin(last[2] - first[2]), math.cos(last[2] - first[2]))
        ),
        "start": first,
        "end": last,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=20.0)
    args = parser.parse_args()
    rclpy.init()
    node = Collector()
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        print(json.dumps({name: summarize(values) for name, values in node.samples.items()} | {
            "health": node.health,
            "duration_s": args.seconds,
        }, indent=2, sort_keys=True))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
