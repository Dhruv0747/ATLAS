#!/usr/bin/env python3
"""Print one live LaserScan's raw and base-frame sector clearances."""

import argparse
import json
import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


def angular_error_degrees(angle, center):
    return abs((angle - center + 180.0) % 360.0 - 180.0)


class SectorCheck(Node):
    def __init__(self, laser_yaw_deg):
        super().__init__("atlas_lidar_sector_check")
        self.laser_yaw_deg = laser_yaw_deg
        self.result = None
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)

    def on_scan(self, msg):
        centers = {"front": 0.0, "left": 90.0, "right": -90.0, "rear": 180.0}
        raw = {name: math.inf for name in centers}
        base = {name: math.inf for name in centers}
        for index, value in enumerate(msg.ranges):
            if not math.isfinite(value) or value < msg.range_min or value > msg.range_max:
                continue
            raw_deg = math.degrees(msg.angle_min + index * msg.angle_increment)
            base_deg = raw_deg + self.laser_yaw_deg
            for name, center in centers.items():
                if angular_error_degrees(raw_deg, center) <= 17.5:
                    raw[name] = min(raw[name], value)
                if angular_error_degrees(base_deg, center) <= 17.5:
                    base[name] = min(base[name], value)
        def clean(values):
            return {key: (round(value, 3) if math.isfinite(value) else None)
                    for key, value in values.items()}
        self.result = {
            "frame": msg.header.frame_id,
            "laser_yaw_deg": self.laser_yaw_deg,
            "raw_sensor_sectors_m": clean(raw),
            "interpreted_base_sectors_m": clean(base),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--laser-yaw-deg", type=float, default=180.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    rclpy.init()
    node = SectorCheck(args.laser_yaw_deg)
    deadline = node.get_clock().now().nanoseconds + int(args.timeout * 1e9)
    while rclpy.ok() and node.result is None and node.get_clock().now().nanoseconds < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
    print(json.dumps(node.result or {"error": "no /scan received"}, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
