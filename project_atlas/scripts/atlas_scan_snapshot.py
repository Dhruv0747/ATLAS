#!/usr/bin/env python3
"""Capture one raw and filtered ATLAS LiDAR scan and summarize geometry."""

import json
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan


class ScanSnapshot(Node):
    def __init__(self):
        super().__init__("atlas_scan_snapshot")
        self.messages = {}
        self.create_subscription(
            LaserScan, "/scan_raw", lambda msg: self.capture("raw", msg),
            qos_profile_sensor_data,
        )
        self.create_subscription(
            LaserScan, "/scan", lambda msg: self.capture("filtered", msg),
            qos_profile_sensor_data,
        )

    def capture(self, name, msg):
        if name not in self.messages:
            self.messages[name] = msg


def summarize(msg):
    points = []
    for index, distance in enumerate(msg.ranges):
        if not math.isfinite(distance) or not msg.range_min <= distance <= msg.range_max:
            continue
        angle = msg.angle_min + index * msg.angle_increment
        points.append((distance, math.degrees(angle), distance * math.cos(angle), distance * math.sin(angle)))

    def sector(center, half_width=15.0):
        values = [
            distance for distance, angle, _x, _y in points
            if abs((angle - center + 180.0) % 360.0 - 180.0) <= half_width
        ]
        return round(min(values), 3) if values else None

    inside_rover = [
        (distance, angle, x, y) for distance, angle, x, y in points
        if -0.20 <= x <= 0.30 and -0.18 <= y <= 0.18
    ]
    nearest = [
        {"range_m": round(distance, 3), "angle_deg": round(angle, 1),
         "x_m": round(x, 3), "y_m": round(y, 3)}
        for distance, angle, x, y in sorted(points)[:12]
    ]
    return {
        "frame": msg.header.frame_id,
        "valid_points": len(points),
        "front_m": sector(0.0),
        "left_m": sector(90.0),
        "rear_m": sector(180.0),
        "right_m": sector(-90.0),
        "points_inside_rover_rectangle": len(inside_rover),
        "nearest": nearest,
    }


def main():
    rclpy.init()
    node = ScanSnapshot()
    deadline = time.monotonic() + 5.0
    while len(node.messages) < 2 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.25)
    output = {name: summarize(msg) for name, msg in node.messages.items()}
    print(json.dumps(output, indent=2, sort_keys=True))
    node.destroy_node()
    rclpy.shutdown()
    if len(output) < 2:
        raise SystemExit("Did not receive both /scan_raw and /scan")


if __name__ == "__main__":
    main()
