#!/usr/bin/env python3
"""Validate RF2O output and attach usable covariance before EKF fusion."""

from __future__ import annotations

import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import String

from atlas_lidar_odom_gate_core import LidarOdomGate, StationaryPoseStabilizer


def yaw_of(orientation) -> float:
    return math.atan2(
        2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
        1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
    )


def covariance(x: float, y: float, yaw: float) -> list[float]:
    result = [0.0] * 36
    result[0], result[7], result[35] = x, y, yaw
    result[14] = result[21] = result[28] = 1.0e6
    return result


class AtlasLidarOdomGateNode(Node):
    def __init__(self) -> None:
        super().__init__("atlas_lidar_odom_gate")
        self.gate = LidarOdomGate()
        self.stabilizer = StationaryPoseStabilizer()
        self.output = self.create_publisher(Odometry, "/lidar/odom", 10)
        self.health = self.create_publisher(String, "/lidar/odom/health", 10)
        self.create_subscription(Odometry, "/lidar/odom_raw", self.on_odom, 10)
        self.create_subscription(Odometry, "/yahboom/odom", self.on_wheel_odom, 10)
        self.create_subscription(Twist, "/cmd_vel", self.on_command, 10)
        self.create_timer(0.5, self.publish_health)
        self.last_input_at = 0.0
        self.last_accept_at = 0.0
        self.accepted = 0
        self.rejected = 0
        self.reason = "WAITING_FOR_RF2O"
        self.last_delta_m = 0.0
        self.last_delta_yaw = 0.0
        self.last_wheel_at = 0.0
        self.last_command_at = 0.0
        self.wheel_motion = 0.0
        self.command_motion = 0.0
        self.stationary_lock = False

    def on_wheel_odom(self, message: Odometry) -> None:
        self.last_wheel_at = time.monotonic()
        self.wheel_motion = max(
            abs(message.twist.twist.linear.x), abs(message.twist.twist.angular.z)
        )

    def on_command(self, message: Twist) -> None:
        self.last_command_at = time.monotonic()
        self.command_motion = max(abs(message.linear.x), abs(message.angular.z))

    def on_odom(self, message: Odometry) -> None:
        now = time.monotonic()
        self.last_input_at = now
        stamp_s = message.header.stamp.sec + message.header.stamp.nanosec / 1e9
        decision = self.gate.evaluate(
            stamp_s,
            message.pose.pose.position.x,
            message.pose.pose.position.y,
            yaw_of(message.pose.pose.orientation),
        )
        self.reason = decision.reason
        self.last_delta_m = decision.translation_delta_m
        self.last_delta_yaw = decision.yaw_delta_rad
        if not decision.accepted:
            self.rejected += 1
            return

        wheel_fresh = now - self.last_wheel_at <= 0.6
        command_fresh = now - self.last_command_at <= 0.6
        self.stationary_lock = (
            wheel_fresh and self.wheel_motion < 0.01
            and (not command_fresh or self.command_motion < 0.01)
        )
        x_m, y_m, yaw_rad = self.stabilizer.update(
            message.pose.pose.position.x,
            message.pose.pose.position.y,
            yaw_of(message.pose.pose.orientation),
            self.stationary_lock,
        )
        message.pose.pose.position.x = x_m
        message.pose.pose.position.y = y_m
        message.pose.pose.orientation.x = 0.0
        message.pose.pose.orientation.y = 0.0
        message.pose.pose.orientation.z = math.sin(yaw_rad / 2.0)
        message.pose.pose.orientation.w = math.cos(yaw_rad / 2.0)
        if self.stationary_lock:
            message.twist.twist.linear.x = 0.0
            message.twist.twist.linear.y = 0.0
            message.twist.twist.angular.z = 0.0
        message.header.frame_id = "odom"
        message.child_frame_id = "base_link"
        message.pose.covariance = covariance(0.01, 0.01, 0.03)
        message.twist.covariance = covariance(0.04, 1.0e-3, 0.06)
        self.output.publish(message)
        self.accepted += 1
        self.last_accept_at = now

    def publish_health(self) -> None:
        now = time.monotonic()
        input_age = None if not self.last_input_at else now - self.last_input_at
        accepted_age = None if not self.last_accept_at else now - self.last_accept_at
        state = "LIVE"
        reason = self.reason
        if input_age is None or input_age > 1.0:
            state, reason = "STALE", "RF2O_INPUT_STALE"
        elif accepted_age is None or accepted_age > 1.0:
            state, reason = "REJECTING", self.reason
        payload = {
            "state": state,
            "reason": reason,
            "input_age_s": input_age,
            "accepted_age_s": accepted_age,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "last_translation_delta_m": self.last_delta_m,
            "last_yaw_delta_rad": self.last_delta_yaw,
            "stationary_lock": self.stationary_lock,
            "wheel_motion": self.wheel_motion,
            "command_motion": self.command_motion,
            "authority": "SHADOW_CANDIDATE",
        }
        self.health.publish(String(data=json.dumps(payload, sort_keys=True)))


def main() -> None:
    rclpy.init()
    node = AtlasLidarOdomGateNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
