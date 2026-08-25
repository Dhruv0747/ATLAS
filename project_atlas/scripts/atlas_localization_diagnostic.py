#!/usr/bin/env python3
"""Measure stationary ATLAS localization, odometry and TF stability."""

import argparse
import json
import math
import statistics
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from std_srvs.srv import Empty
from tf2_ros import Buffer, TransformListener


def yaw(z: float, w: float) -> float:
    return 2.0 * math.atan2(float(z), float(w))


def span(samples, key):
    values = [sample[key] for sample in samples]
    return max(values) - min(values) if values else None


class Diagnostic(Node):
    def __init__(self):
        super().__init__("atlas_localization_diagnostic")
        self.amcl = []
        self.odom = []
        self.wheel = []
        self.scan_ages = []
        self.tf_ages = []
        self.tf_errors = []
        self.started = time.monotonic()
        self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self.on_amcl, 10)
        self.create_subscription(Odometry, "/odom", lambda msg: self.on_odom(self.odom, msg), 20)
        self.create_subscription(
            Odometry, "/yahboom/odom", lambda msg: self.on_odom(self.wheel, msg), 20
        )
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.nomotion = self.create_client(Empty, "/request_nomotion_update")
        self.tf_buffer = Buffer(cache_time=Duration(seconds=15.0))
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.create_timer(2.0, self.request_update)
        self.create_timer(0.2, self.sample_tf)

    def elapsed(self):
        return time.monotonic() - self.started

    def on_amcl(self, msg):
        covariance = msg.pose.covariance
        pose = msg.pose.pose
        self.amcl.append(
            {
                "t": self.elapsed(),
                "x": float(pose.position.x),
                "y": float(pose.position.y),
                "yaw": yaw(pose.orientation.z, pose.orientation.w),
                "xy_std": math.sqrt(max(float(covariance[0]), float(covariance[7]), 0.0)),
                "yaw_std": math.sqrt(max(float(covariance[35]), 0.0)),
            }
        )

    def on_odom(self, target, msg):
        pose = msg.pose.pose
        target.append(
            {
                "t": self.elapsed(),
                "x": float(pose.position.x),
                "y": float(pose.position.y),
                "yaw": yaw(pose.orientation.z, pose.orientation.w),
            }
        )

    def on_scan(self, msg):
        stamp = rclpy.time.Time.from_msg(msg.header.stamp)
        self.scan_ages.append(max(0.0, (self.get_clock().now() - stamp).nanoseconds / 1e9))

    def request_update(self):
        if self.nomotion.service_is_ready():
            self.nomotion.call_async(Empty.Request())

    def sample_tf(self):
        try:
            transform = self.tf_buffer.lookup_transform("map", "base_link", Time())
            stamp = rclpy.time.Time.from_msg(transform.header.stamp)
            self.tf_ages.append(max(0.0, (self.get_clock().now() - stamp).nanoseconds / 1e9))
        except Exception as exc:
            self.tf_errors.append({"t": self.elapsed(), "error": str(exc)})

    @staticmethod
    def drift(samples):
        if len(samples) < 2:
            return None
        first, last = samples[0], samples[-1]
        return {
            "translation_m": math.hypot(last["x"] - first["x"], last["y"] - first["y"]),
            "yaw_deg": abs(math.degrees(math.atan2(
                math.sin(last["yaw"] - first["yaw"]),
                math.cos(last["yaw"] - first["yaw"]),
            ))),
        }

    def report(self, duration):
        amcl_xy = [item["xy_std"] for item in self.amcl]
        amcl_yaw = [math.degrees(item["yaw_std"]) for item in self.amcl]
        return {
            "duration_s": duration,
            "counts": {
                "amcl": len(self.amcl),
                "odom": len(self.odom),
                "wheel_odom": len(self.wheel),
                "scan": len(self.scan_ages),
                "tf": len(self.tf_ages),
                "tf_errors": len(self.tf_errors),
            },
            "amcl": {
                "first_pose": self.amcl[0] if self.amcl else None,
                "last_pose": self.amcl[-1] if self.amcl else None,
                "xy_std_first_m": amcl_xy[0] if amcl_xy else None,
                "xy_std_last_m": amcl_xy[-1] if amcl_xy else None,
                "xy_std_max_m": max(amcl_xy) if amcl_xy else None,
                "yaw_std_last_deg": amcl_yaw[-1] if amcl_yaw else None,
                "position_span_x_m": span(self.amcl, "x"),
                "position_span_y_m": span(self.amcl, "y"),
                "drift": self.drift(self.amcl),
            },
            "ekf_odom_drift": self.drift(self.odom),
            "wheel_odom_drift": self.drift(self.wheel),
            "scan_age_s": {
                "median": statistics.median(self.scan_ages) if self.scan_ages else None,
                "max": max(self.scan_ages) if self.scan_ages else None,
            },
            "tf_age_s": {
                "median": statistics.median(self.tf_ages) if self.tf_ages else None,
                "max": max(self.tf_ages) if self.tf_ages else None,
            },
            "tf_error_examples": self.tf_errors[:5],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rclpy.init()
    node = Diagnostic()
    deadline = time.monotonic() + max(5.0, args.duration)
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        report = node.report(args.duration)
        rendered = json.dumps(report, indent=2)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
