#!/usr/bin/env python3
"""Summarize displacement on one odometry topic over a bounded interval."""

from __future__ import annotations

import argparse
import json
import math
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node


def yaw_of(message: Odometry) -> float:
    q = message.pose.pose.orientation
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class Collector(Node):
    def __init__(self, topic: str) -> None:
        super().__init__("atlas_odom_topic_check")
        self.samples = []
        self.last_at = 0.0
        self.create_subscription(Odometry, topic, self.on_message, 50)

    def on_message(self, message: Odometry) -> None:
        self.last_at = time.monotonic()
        self.samples.append((message.pose.pose.position.x, message.pose.pose.position.y, yaw_of(message)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--idle-timeout", type=float, default=3.0)
    args = parser.parse_args()
    rclpy.init()
    node = Collector(args.topic)
    started = time.monotonic()
    try:
        while time.monotonic() - started < args.timeout:
            rclpy.spin_once(node, timeout_sec=0.1)
            if node.samples and time.monotonic() - node.last_at > args.idle_timeout:
                break
        result = {"topic": args.topic, "samples": len(node.samples)}
        if len(node.samples) >= 2:
            first, last = node.samples[0], node.samples[-1]
            result.update({
                "start": first,
                "end": last,
                "net_translation_m": math.hypot(last[0] - first[0], last[1] - first[1]),
                "net_yaw_deg": math.degrees(
                    math.atan2(math.sin(last[2] - first[2]), math.cos(last[2] - first[2]))
                ),
            })
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
