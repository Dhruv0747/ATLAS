#!/usr/bin/env python3
"""Associate camera people with LiDAR range and RD-03D motion targets."""

import json
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, Int32, String

from atlas_person_fusion_core import associate_radar, camera_person, parse_radar_targets
from atlas_vision_lidar_core import associate_detection


class PersonSensorFusion(Node):
    def __init__(self):
        super().__init__("atlas_person_sensor_fusion")
        self.pan_us = 1300
        self.detections = None
        self.detections_at = 0.0
        self.radar = []
        self.radar_at = 0.0
        self.scan = None
        self.scan_at = 0.0
        self.target_pub = self.create_publisher(String, "/atlas/person_fusion/target", 10)
        self.status_pub = self.create_publisher(String, "/atlas/person_fusion/status", 10)
        self.confirmed_pub = self.create_publisher(Bool, "/atlas/person_fusion/confirmed", 10)
        self.create_subscription(String, "/camera/detections/json", self.on_detections, 10)
        self.create_subscription(String, "/radar/targets", self.on_radar, 10)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.create_subscription(Int32, "/camera/bottom_servo_us", self.on_pan, 10)
        self.create_timer(0.20, self.publish_fusion)
        self.get_logger().info("Camera + LiDAR + RD-03D person fusion ready")

    def on_detections(self, message):
        try:
            self.detections = json.loads(message.data)
            self.detections_at = time.monotonic()
        except (TypeError, ValueError, json.JSONDecodeError):
            self.detections = None

    def on_radar(self, message):
        self.radar = parse_radar_targets(message.data)
        self.radar_at = time.monotonic()

    def on_scan(self, message):
        self.scan = message
        self.scan_at = time.monotonic()

    def on_pan(self, message):
        self.pan_us = int(message.data)

    def publish_fusion(self):
        now = time.monotonic()
        result = {"state": "NO_PERSON", "confirmed": False}
        person = None
        if self.detections is not None and now - self.detections_at <= 0.8:
            person = camera_person(self.detections, self.pan_us)
        if person is not None:
            result.update({
                "state": "CAMERA_PERSON",
                "camera_confidence": round(person["confidence"], 3),
                "bearing_deg": round(math.degrees(person["bearing_rad"]), 1),
                "pan_us": self.pan_us,
            })
            lidar = None
            if self.scan is not None and now - self.scan_at <= 0.8:
                lidar = associate_detection(
                    self.scan.ranges, self.scan.angle_min, self.scan.angle_increment,
                    self.scan.range_min, self.scan.range_max,
                    person["left_bearing"], person["right_bearing"], max_distance_m=4.0,
                )
            if lidar is not None:
                _, _, lidar_distance = lidar
                result.update({
                    "state": "PERSON_LIDAR_CONFIRMED",
                    "confirmed": True,
                    "distance_m": round(lidar_distance, 3),
                })
                radar = associate_radar(
                    person["bearing_rad"],
                    self.radar if now - self.radar_at <= 0.8 else [],
                    lidar_distance=lidar_distance,
                )
                if radar is not None:
                    result.update({
                        "state": "PERSON_CAMERA_LIDAR_RADAR",
                        "radar_confirmed": True,
                        "radar_target": radar["id"],
                        "radar_distance_m": round(radar["distance_m"], 3),
                        "speed_mps": round(radar["speed_mps"], 3),
                        "motion": "APPROACHING" if radar["speed_mps"] < -0.05 else
                                  ("MOVING_AWAY" if radar["speed_mps"] > 0.05 else "STATIONARY"),
                    })
                else:
                    result.update({"radar_confirmed": False, "speed_mps": None, "motion": "UNKNOWN"})
        payload = json.dumps(result, separators=(",", ":"))
        self.target_pub.publish(String(data=payload))
        self.confirmed_pub.publish(Bool(data=bool(result["confirmed"])))
        self.status_pub.publish(String(data=payload))


def main():
    rclpy.init()
    node = PersonSensorFusion()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
