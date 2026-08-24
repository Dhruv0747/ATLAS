#!/usr/bin/env python3
"""Sensor-guarded short arc for ATLAS steering-curvature commissioning."""

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


class ArcTest(Node):
    def __init__(self, distance, speed, angular, timeout):
        super().__init__("atlas_bounded_arc_test")
        self.target, self.speed, self.angular, self.timeout = distance, speed, angular, timeout
        self.start = self.pose = None
        self.odom_at = self.scan_at = self.started = 0.0
        self.clearance = math.inf
        self.result = "WAITING"
        self.pub = self.create_publisher(Twist, "/cmd_vel_recovery", 10)
        self.create_subscription(Odometry, "/yahboom/odom", self.on_odom, 20)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.create_timer(0.05, self.tick)

    def on_odom(self, msg):
        p = msg.pose.pose
        self.pose = (p.position.x, p.position.y)
        self.odom_at = time.monotonic()
        if self.start is None:
            self.start = self.pose

    def on_scan(self, msg):
        values, angle = [], msg.angle_min
        heading = 35.0 if self.angular >= 0.0 else -35.0
        for value in msg.ranges:
            if (ray_in_base_sector(math.degrees(angle), heading, 55.0, 180.0)
                    and math.isfinite(value) and value >= msg.range_min):
                values.append(value)
            angle += msg.angle_increment
        self.clearance = min(values) if values else math.inf
        self.scan_at = time.monotonic()

    def distance(self):
        return 0.0 if self.start is None or self.pose is None else math.hypot(
            self.pose[0] - self.start[0], self.pose[1] - self.start[1]
        )

    def stop(self, reason):
        self.result = reason
        self.pub.publish(Twist())

    def tick(self):
        now = time.monotonic()
        if self.result not in ("WAITING", "RUNNING"):
            self.pub.publish(Twist()); return
        if self.start is None or not self.scan_at:
            return
        if not self.started:
            self.started, self.result = now, "RUNNING"
            print(f"START clearance={self.clearance:.3f}m target={self.target:.3f}m", flush=True)
        if now - self.odom_at > 0.6 or now - self.scan_at > 0.6:
            self.stop("STOP_STALE_TELEMETRY")
        elif self.clearance < 0.55:
            self.stop(f"STOP_LIDAR_{self.clearance:.3f}M")
        elif self.distance() >= self.target:
            self.stop("PASS_TARGET")
        elif now - self.started >= self.timeout:
            self.stop("STOP_TIMEOUT")
        else:
            command = Twist()
            command.linear.x, command.angular.z = self.speed, self.angular
            self.pub.publish(command)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distance", type=float, default=0.20)
    parser.add_argument("--speed", type=float, default=0.08)
    parser.add_argument("--angular", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    rclpy.init()
    node = ArcTest(args.distance, args.speed, args.angular, args.timeout)
    try:
        while rclpy.ok() and node.result in ("WAITING", "RUNNING"):
            rclpy.spin_once(node, timeout_sec=0.1)
        end = time.monotonic() + 1.0
        while rclpy.ok() and time.monotonic() < end:
            node.pub.publish(Twist()); rclpy.spin_once(node, timeout_sec=0.05)
        print(f"RESULT {node.result} odom_distance={node.distance():.3f}m clearance={node.clearance:.3f}m", flush=True)
    finally:
        node.pub.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
