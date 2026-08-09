#!/usr/bin/env python3
"""Passive, bounded Nav2 command-chain monitor for Project ATLAS."""

import argparse
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node
from std_msgs.msg import String


class CommandChainMonitor(Node):
    def __init__(self) -> None:
        super().__init__("atlas_nav_command_chain_monitor")
        self.plan_points = 0
        self.nav_count = 0
        self.mux_count = 0
        self.nav_peak = (0.0, 0.0)
        self.mux_peak = (0.0, 0.0)
        self.odom = (0.0, 0.0, 0.0, 0.0)
        self.drive_mode = "UNKNOWN"
        self.safety = "UNKNOWN"
        self.create_subscription(Path, "/plan", self.on_plan, 10)
        self.create_subscription(Twist, "/cmd_vel_nav", self.on_nav, 10)
        self.create_subscription(Twist, "/cmd_vel", self.on_mux, 10)
        self.create_subscription(Odometry, "/odom", self.on_odom, 10)
        self.create_subscription(String, "/atlas/drive_mode", self.on_mode, 10)
        self.create_subscription(
            String, "/atlas/motion_safety", self.on_safety, 10
        )

    def on_plan(self, message: Path) -> None:
        self.plan_points = len(message.poses)

    def on_nav(self, message: Twist) -> None:
        self.nav_count += 1
        self.nav_peak = (
            max(self.nav_peak[0], abs(float(message.linear.x))),
            max(self.nav_peak[1], abs(float(message.angular.z))),
        )

    def on_mux(self, message: Twist) -> None:
        self.mux_count += 1
        self.mux_peak = (
            max(self.mux_peak[0], abs(float(message.linear.x))),
            max(self.mux_peak[1], abs(float(message.angular.z))),
        )

    def on_odom(self, message: Odometry) -> None:
        self.odom = (
            float(message.pose.pose.position.x),
            float(message.pose.pose.position.y),
            float(message.twist.twist.linear.x),
            float(message.twist.twist.angular.z),
        )

    def on_mode(self, message: String) -> None:
        self.drive_mode = message.data

    def on_safety(self, message: String) -> None:
        self.safety = message.data

    def report(self, label: str) -> None:
        print(
            label,
            f"plan={self.plan_points}",
            f"nav_msgs={self.nav_count}",
            f"nav_peak=({self.nav_peak[0]:.3f},{self.nav_peak[1]:.3f})",
            f"mux_msgs={self.mux_count}",
            f"mux_peak=({self.mux_peak[0]:.3f},{self.mux_peak[1]:.3f})",
            f"odom=({self.odom[0]:.3f},{self.odom[1]:.3f},"
            f"{self.odom[2]:.3f},{self.odom[3]:.3f})",
            f"mode={self.drive_mode!r}",
            f"safety={self.safety!r}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=30.0)
    args = parser.parse_args()
    rclpy.init()
    node = CommandChainMonitor()
    try:
        deadline = time.monotonic() + max(1.0, min(args.duration, 60.0))
        next_report = time.monotonic()
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if time.monotonic() >= next_report:
                node.report("LIVE")
                next_report = time.monotonic() + 1.0
        node.report("FINAL")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
