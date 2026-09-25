#!/usr/bin/env python3
"""Sensor-guarded short arc for ATLAS steering-curvature commissioning."""

import argparse
import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from std_srvs.srv import Trigger

from atlas_scan_geometry import ray_in_base_sector
from atlas_straight_distance_core import IncrementalPlanarDistance


class ArcTest(Node):
    def __init__(self, distance, speed, angular, timeout):
        super().__init__("atlas_bounded_arc_test")
        self.target, self.speed, self.angular, self.timeout = distance, speed, angular, timeout
        self.start = self.pose = None
        self.odom_at = self.lidar_odom_at = self.scan_at = self.started = 0.0
        self.lidar_distance = IncrementalPlanarDistance()
        self.encoder_health = {}
        self.encoder_health_at = 0.0
        self.clearance = math.inf
        self.result = "WAITING"
        self.armed = False
        self.pub = self.create_publisher(Twist, "/cmd_vel_commission", 10)
        self.arm_client = self.create_client(Trigger, "/atlas/commission/arm")
        self.disarm_client = self.create_client(Trigger, "/atlas/commission/disarm")
        self.create_subscription(Odometry, "/yahboom/odom", self.on_odom, 20)
        self.create_subscription(Odometry, "/lidar/odom", self.on_lidar_odom, 20)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.create_subscription(String, "/atlas/encoder_health", self.on_encoder_health, 20)
        self.create_timer(0.05, self.tick)

    def arm(self):
        # Discovery may be slow under the full ATLAS workload. Waiting longer
        # does not arm motion; the 20-second lease starts only on success.
        if not self.arm_client.wait_for_service(timeout_sec=12.0):
            return False, "commissioning arm service unavailable"
        future = self.arm_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
        response = future.result()
        if response is None:
            return False, "commissioning arm request timed out"
        self.armed = bool(response.success)
        return self.armed, str(response.message)

    def disarm(self):
        self.armed = False
        if not self.disarm_client.wait_for_service(timeout_sec=0.5):
            return
        future = self.disarm_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=1.0)

    def on_odom(self, msg):
        p = msg.pose.pose
        self.pose = (p.position.x, p.position.y)
        self.odom_at = time.monotonic()
        if self.start is None:
            self.start = self.pose

    def on_lidar_odom(self, msg):
        p = msg.pose.pose.position
        if self.lidar_distance.update(p.x, p.y):
            self.lidar_odom_at = time.monotonic()

    def on_encoder_health(self, msg):
        try:
            value = json.loads(msg.data)
            self.encoder_health = value if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            self.encoder_health = {}
        self.encoder_health_at = time.monotonic()

    def on_scan(self, msg):
        values, angle = [], msg.angle_min
        # Guard the direction of travel. The old implementation always
        # inspected a forward-side sector, even for a reverse arc, so it could
        # not safely commission a doorway escape maneuver.
        if self.speed < 0.0:
            heading = 180.0
            sector_width = 70.0
        elif abs(self.angular) < 1.0e-3:
            heading = 0.0
            sector_width = 35.0
        else:
            heading = 35.0 if self.angular >= 0.0 else -35.0
            sector_width = 55.0
        for value in msg.ranges:
            if (ray_in_base_sector(math.degrees(angle), heading, sector_width, 180.0)
                    and math.isfinite(value) and value >= msg.range_min):
                values.append(value)
            angle += msg.angle_increment
        self.clearance = min(values) if values else math.inf
        self.scan_at = time.monotonic()

    def distance(self):
        wheel = 0.0 if self.start is None or self.pose is None else math.hypot(
            self.pose[0] - self.start[0], self.pose[1] - self.start[1]
        )
        return max(wheel, self.lidar_distance.distance_m)

    def stop(self, reason):
        self.result = reason
        self.pub.publish(Twist())

    def tick(self):
        now = time.monotonic()
        if not self.armed:
            return
        if self.result not in ("WAITING", "RUNNING"):
            self.pub.publish(Twist()); return
        if (self.start is None or not self.scan_at or not self.lidar_odom_at
                or not self.encoder_health_at):
            return
        if not self.started:
            self.started, self.result = now, "RUNNING"
            print(f"START clearance={self.clearance:.3f}m target={self.target:.3f}m", flush=True)
        encoder_state = str(self.encoder_health.get("state", "MISSING")).upper()
        if (now - self.odom_at > 0.6 or now - self.lidar_odom_at > 0.6
                or now - self.scan_at > 0.6 or now - self.encoder_health_at > 0.6):
            self.stop("STOP_STALE_TELEMETRY")
        elif encoder_state in ("CRITICAL", "INVALID", "MISSING", "QUALIFYING"):
            self.stop("STOP_ENCODER_" + encoder_state)
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
        armed, message = node.arm()
        print(f"ARM success={armed} message={message}", flush=True)
        if not armed:
            return
        while rclpy.ok() and node.result in ("WAITING", "RUNNING"):
            rclpy.spin_once(node, timeout_sec=0.1)
        end = time.monotonic() + 1.0
        while rclpy.ok() and time.monotonic() < end:
            node.pub.publish(Twist()); rclpy.spin_once(node, timeout_sec=0.05)
        print(f"RESULT {node.result} distance={node.distance():.3f}m "
              f"lidar_distance={node.lidar_distance.distance_m:.3f}m "
              f"clearance={node.clearance:.3f}m "
              f"encoder_state={node.encoder_health.get('state', 'MISSING')}", flush=True)
    finally:
        node.pub.publish(Twist())
        node.disarm()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
