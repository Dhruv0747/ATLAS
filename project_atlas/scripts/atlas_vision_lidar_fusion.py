#!/usr/bin/env python3
"""Fuse camera semantics with LiDAR ranges for conservative Nav2 obstacles."""

import json
import math
import struct
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan, PointCloud2, PointField
from std_msgs.msg import Header, Int32, String

from atlas_vision_lidar_core import associate_detection, pixel_to_bearing


FORWARD_PAN_US = 2300
FORWARD_TILT_US = 1500
PAN_TOLERANCE_US = 90
TILT_TOLERANCE_US = 180
HORIZONTAL_FOV_RAD = math.radians(66.0)
MIN_CONFIDENCE = 0.45
MAX_CONFIRMED_RANGE_M = 3.0
STALE_SECONDS = 0.8

NAVIGATION_CLASSES = {
    "person", "bicycle", "car", "motorcycle", "bus", "truck", "bench",
    "cat", "dog", "backpack", "handbag", "suitcase", "sports ball",
    "skateboard", "bottle", "chair", "couch", "potted plant", "bed",
    "dining table", "toilet", "tv", "laptop", "refrigerator",
}


class AtlasVisionLidarFusion(Node):
    def __init__(self) -> None:
        super().__init__("atlas_vision_lidar_fusion")
        self.scan = None
        self.scan_time = 0.0
        self.detections = None
        self.detection_time = 0.0
        self.pan_us = FORWARD_PAN_US
        self.tilt_us = FORWARD_TILT_US
        self.cloud_pub = self.create_publisher(
            # Nav2 obstacle-layer PointCloud2 subscriptions request reliable
            # delivery. A sensor-data (best-effort) publisher is QoS-
            # incompatible and silently leaves the costmaps disconnected.
            PointCloud2, "/camera/semantic_obstacles", 10
        )
        self.status_pub = self.create_publisher(
            String, "/atlas/vision_navigation/status", 10
        )
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.create_subscription(String, "/camera/detections/json", self.on_detections, 10)
        self.create_subscription(Int32, "/camera/bottom_servo_us", self.on_pan, 10)
        self.create_subscription(Int32, "/camera/second_servo_us", self.on_tilt, 10)
        self.create_timer(0.2, self.publish_fusion)
        self.get_logger().info(
            "Camera/LiDAR navigation fusion ready; visual detections require LiDAR confirmation"
        )

    def on_scan(self, message: LaserScan) -> None:
        self.scan = message
        self.scan_time = time.monotonic()

    def on_detections(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            if isinstance(payload, dict):
                self.detections = payload
                self.detection_time = time.monotonic()
        except (TypeError, ValueError):
            self.detections = None

    def on_pan(self, message: Int32) -> None:
        self.pan_us = int(message.data)

    def on_tilt(self, message: Int32) -> None:
        self.tilt_us = int(message.data)

    @staticmethod
    def make_cloud(points) -> PointCloud2:
        message = PointCloud2()
        message.header = Header(frame_id="base_link")
        message.height = 1
        message.width = len(points)
        message.fields = [
            PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        ]
        message.is_bigendian = False
        message.point_step = 12
        message.row_step = message.point_step * message.width
        message.is_dense = True
        message.data = b"".join(struct.pack("<fff", x, y, 0.10) for x, y in points)
        return message

    def publish_fusion(self) -> None:
        now = time.monotonic()
        reason = "ACTIVE"
        points = []
        confirmed = []
        candidates = []
        camera_forward = (
            abs(self.pan_us - FORWARD_PAN_US) <= PAN_TOLERANCE_US
            and abs(self.tilt_us - FORWARD_TILT_US) <= TILT_TOLERANCE_US
        )
        if not camera_forward:
            reason = "SUSPENDED_CAMERA_NOT_FORWARD"
        elif self.scan is None or now - self.scan_time > STALE_SECONDS:
            reason = "SUSPENDED_LIDAR_STALE"
        elif self.detections is None or now - self.detection_time > STALE_SECONDS:
            reason = "SUSPENDED_CAMERA_AI_STALE"
        else:
            width = int(self.detections.get("width", 0) or 0)
            for detection in self.detections.get("detections", []):
                label = str(detection.get("label", "")).strip().lower()
                confidence = float(detection.get("confidence", 0.0) or 0.0)
                if label not in NAVIGATION_CLASSES or confidence < MIN_CONFIDENCE or width <= 0:
                    continue
                candidates.append(label)
                left = pixel_to_bearing(float(detection.get("x1", 0)), width, HORIZONTAL_FOV_RAD)
                right = pixel_to_bearing(float(detection.get("x2", 0)), width, HORIZONTAL_FOV_RAD)
                # Guarantee a small correlation cone for narrow/distant boxes.
                center = (left + right) * 0.5
                half = max(abs(left - right) * 0.5, math.radians(2.0))
                match = associate_detection(
                    self.scan.ranges,
                    self.scan.angle_min,
                    self.scan.angle_increment,
                    self.scan.range_min,
                    self.scan.range_max,
                    center + half,
                    center - half,
                    max_distance_m=MAX_CONFIRMED_RANGE_M,
                )
                if match is not None:
                    x, y, distance = match
                    points.append((x, y))
                    confirmed.append(
                        {"label": label, "confidence": confidence, "distance_m": round(distance, 2)}
                    )

        cloud = self.make_cloud(points)
        cloud.header.stamp = self.get_clock().now().to_msg()
        self.cloud_pub.publish(cloud)
        self.status_pub.publish(
            String(data=json.dumps({
                "state": reason,
                "camera_forward": camera_forward,
                "pan_us": self.pan_us,
                "tilt_us": self.tilt_us,
                "candidates": candidates,
                "confirmed": confirmed,
                "costmap_points": len(points),
            }, separators=(",", ":")))
        )


def main() -> None:
    rclpy.init()
    node = AtlasVisionLidarFusion()
    try:
        rclpy.spin(node)
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
