#!/usr/bin/env python3
"""Report LiDAR returns projected inside ATLAS's physical footprint."""

import argparse
import json
import math
import time

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener


class ScanDiagnostic(Node):
    def __init__(self, scans):
        super().__init__("atlas_scan_self_hit_diagnostic")
        self.target_scans = scans
        self.received = 0
        self.hits = {}
        self.tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.subscription = self.create_subscription(
            LaserScan, "/scan", self.on_scan, qos_profile_sensor_data
        )

    def on_scan(self, msg):
        try:
            transform = self.tf_buffer.lookup_transform(
                "base_link", msg.header.frame_id, Time(),
                timeout=Duration(seconds=0.2),
            )
        except Exception:
            return
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        sensor_yaw = 2.0 * math.atan2(float(rotation.z), float(rotation.w))
        self.received += 1
        for index, distance in enumerate(msg.ranges):
            if not math.isfinite(distance) or distance < msg.range_min or distance > msg.range_max:
                continue
            angle = float(msg.angle_min) + index * float(msg.angle_increment)
            base_angle = sensor_yaw + angle
            x = float(translation.x) + float(distance) * math.cos(base_angle)
            y = float(translation.y) + float(distance) * math.sin(base_angle)
            if abs(x) <= 0.25 and abs(y) <= 0.18:
                key = index
                entry = self.hits.setdefault(
                    key,
                    {
                        "index": index,
                        "scan_angle_deg": math.degrees(angle),
                        "count": 0,
                        "min_range_m": float(distance),
                        "max_range_m": float(distance),
                        "last_base_x_m": x,
                        "last_base_y_m": y,
                    },
                )
                entry["count"] += 1
                entry["min_range_m"] = min(entry["min_range_m"], float(distance))
                entry["max_range_m"] = max(entry["max_range_m"], float(distance))
                entry["last_base_x_m"] = x
                entry["last_base_y_m"] = y

    def report(self):
        ordered = sorted(self.hits.values(), key=lambda item: (-item["count"], item["index"]))
        return {
            "scans": self.received,
            "self_hit_beams": len(ordered),
            "persistent_hits": [item for item in ordered if item["count"] >= max(2, self.received // 4)],
            "all_hits": ordered[:50],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scans", type=int, default=50)
    args = parser.parse_args()
    rclpy.init()
    node = ScanDiagnostic(args.scans)
    deadline = time.monotonic() + 15.0
    try:
        while node.received < args.scans and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        print(json.dumps(node.report(), indent=2))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
