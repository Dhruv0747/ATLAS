#!/usr/bin/env python3
"""Bounded straight-distance commissioning test with a LiDAR stop guard."""

import argparse
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

from atlas_scan_geometry import ray_in_base_sector


LASER_YAW_DEG = 180.0


class StraightTest(Node):
    def __init__(self, target_m: float, speed: float, timeout_s: float) -> None:
        super().__init__("atlas_straight_distance_test")
        self.target_m = target_m
        self.speed = speed
        self.timeout_s = timeout_s
        self.start_xy = None
        self.xy = None
        self.odom_time = 0.0
        self.clearance_m = math.inf
        self.scan_time = 0.0
        self.started = 0.0
        self.result = "WAITING"
        self.pub = self.create_publisher(Twist, "/cmd_vel_web", 10)
        self.create_subscription(Odometry, "/yahboom/odom", self.on_odom, 20)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.create_timer(0.05, self.tick)

    def on_odom(self, msg: Odometry) -> None:
        self.xy = (msg.pose.pose.position.x, msg.pose.pose.position.y)
        self.odom_time = time.monotonic()
        if self.start_xy is None:
            self.start_xy = self.xy

    def on_scan(self, msg: LaserScan) -> None:
        values = []
        angle = msg.angle_min
        for value in msg.ranges:
            degrees = math.degrees(angle)
            travel_heading = 0.0 if self.speed >= 0.0 else 180.0
            if (
                ray_in_base_sector(degrees, travel_heading, 18.0, LASER_YAW_DEG)
                and math.isfinite(value)
                and value >= msg.range_min
            ):
                values.append(value)
            angle += msg.angle_increment
        self.clearance_m = min(values) if values else math.inf
        self.scan_time = time.monotonic()

    def stop(self, result: str) -> None:
        self.result = result
        self.pub.publish(Twist())

    def distance(self) -> float:
        if self.start_xy is None or self.xy is None:
            return 0.0
        return math.hypot(self.xy[0] - self.start_xy[0], self.xy[1] - self.start_xy[1])

    def tick(self) -> None:
        now = time.monotonic()
        if self.result != "WAITING" and self.result != "RUNNING":
            self.pub.publish(Twist())
            return
        if self.start_xy is None or self.scan_time == 0.0:
            return
        if self.started == 0.0:
            self.started = now
            self.result = "RUNNING"
            direction = "forward" if self.speed >= 0.0 else "reverse"
            print(
                f"START direction={direction} clearance={self.clearance_m:.3f}m "
                f"target={self.target_m:.3f}m",
                flush=True,
            )
        if now - self.odom_time > 0.6 or now - self.scan_time > 0.6:
            self.stop("STOP_STALE_TELEMETRY")
        elif self.clearance_m < 0.55:
            self.stop(f"STOP_LIDAR_{self.clearance_m:.3f}M")
        elif self.distance() >= self.target_m:
            self.stop("PASS_TARGET")
        elif now - self.started >= self.timeout_s:
            self.stop("STOP_TIMEOUT")
        else:
            cmd = Twist()
            cmd.linear.x = self.speed
            self.pub.publish(cmd)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distance", type=float, default=0.50)
    parser.add_argument("--speed", type=float, default=0.10)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    rclpy.init()
    node = StraightTest(args.distance, args.speed, args.timeout)
    try:
        while rclpy.ok() and node.result in ("WAITING", "RUNNING"):
            rclpy.spin_once(node, timeout_sec=0.1)
        end = time.monotonic() + 1.0
        while rclpy.ok() and time.monotonic() < end:
            node.pub.publish(Twist())
            rclpy.spin_once(node, timeout_sec=0.05)
        print(
            f"RESULT {node.result} odom_distance={node.distance():.3f}m "
            f"clearance={node.clearance_m:.3f}m",
            flush=True,
        )
    finally:
        node.pub.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
