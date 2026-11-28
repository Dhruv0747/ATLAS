#!/usr/bin/env python3
"""Print one read-only directional LiDAR clearance snapshot."""

import json
import math
import statistics

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

from atlas_scan_geometry import ray_in_base_sector


SECTORS = {
    "front": (0.0, 24.0),
    "front_right": (-45.0, 30.0),
    "right": (-90.0, 30.0),
    "rear_right": (-135.0, 30.0),
    "rear": (180.0, 24.0),
    "rear_left": (135.0, 30.0),
    "left": (90.0, 30.0),
    "front_left": (45.0, 30.0),
}


class Snapshot(Node):
    def __init__(self):
        super().__init__("atlas_lidar_clearance_snapshot")
        self.result = None
        self.create_subscription(
            LaserScan, "/scan", self.on_scan, qos_profile_sensor_data
        )

    def on_scan(self, msg):
        buckets = {name: [] for name in SECTORS}
        angle = msg.angle_min
        for value in msg.ranges:
            degrees = math.degrees(angle)
            if math.isfinite(value) and msg.range_min <= value <= msg.range_max:
                for name, (heading, width) in SECTORS.items():
                    if ray_in_base_sector(degrees, heading, width, 180.0):
                        buckets[name].append(float(value))
            angle += msg.angle_increment
        self.result = {}
        for name, values in buckets.items():
            ordered = sorted(values)
            index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.10)))
            self.result[name] = {
                "minimum_m": round(min(ordered), 3) if ordered else None,
                "p10_m": round(ordered[index], 3) if ordered else None,
                "median_m": round(statistics.median(ordered), 3) if ordered else None,
                "samples": len(ordered),
            }


def main():
    rclpy.init()
    node = Snapshot()
    try:
        end = node.get_clock().now().nanoseconds + 5_000_000_000
        while rclpy.ok() and node.result is None:
            if node.get_clock().now().nanoseconds >= end:
                raise RuntimeError("no /scan received within five seconds")
            rclpy.spin_once(node, timeout_sec=0.2)
        print(json.dumps(node.result, sort_keys=True))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
