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
from std_srvs.srv import Trigger

from atlas_scan_geometry import ray_in_base_sector
from atlas_straight_distance_core import (
    IncrementalPlanarDistance,
    conservative_progress,
    forward_clearance_progress,
    robust_corridor_range,
)


LASER_YAW_DEG = 180.0


class StraightTest(Node):
    def __init__(
        self,
        target_m: float,
        speed: float,
        timeout_s: float,
        pulse_on_s: float,
        settle_s: float,
        tolerance_m: float,
    ) -> None:
        super().__init__("atlas_straight_distance_test")
        self.target_m = target_m
        self.speed = speed
        self.timeout_s = timeout_s
        self.pulse_on_s = pulse_on_s
        self.settle_s = settle_s
        self.tolerance_m = tolerance_m
        self.wheel_start_xy = None
        self.wheel_xy = None
        self.wheel_odom_time = 0.0
        self.lidar_distance = IncrementalPlanarDistance()
        self.lidar_odom_time = 0.0
        self.clearance_m = math.inf
        self.start_clearance_m = math.inf
        self.corridor_range_m = math.inf
        self.start_corridor_range_m = math.inf
        self.scan_time = 0.0
        self.started = 0.0
        self.phase = "WAITING"
        self.phase_started = 0.0
        self.cycle_start_distance_m = 0.0
        self.active_pulse_s = pulse_on_s
        self.result = "WAITING"
        self.pub = self.create_publisher(Twist, "/cmd_vel_commission", 10)
        self.arm_client = self.create_client(Trigger, "/atlas/commission/arm")
        self.disarm_client = self.create_client(Trigger, "/atlas/commission/disarm")
        self.create_subscription(Odometry, "/yahboom/odom", self.on_wheel_odom, 20)
        self.create_subscription(Odometry, "/lidar/odom", self.on_lidar_odom, 20)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.create_timer(0.05, self.tick)

    def arm(self) -> tuple[bool, str]:
        if not self.arm_client.wait_for_service(timeout_sec=3.0):
            return False, "commissioning arm service unavailable"
        future = self.arm_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
        response = future.result()
        if response is None:
            return False, "commissioning arm request timed out"
        return bool(response.success), str(response.message)

    def disarm(self) -> None:
        if not self.disarm_client.wait_for_service(timeout_sec=0.5):
            return
        future = self.disarm_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=1.0)

    def on_wheel_odom(self, msg: Odometry) -> None:
        self.wheel_xy = (msg.pose.pose.position.x, msg.pose.pose.position.y)
        self.wheel_odom_time = time.monotonic()
        if self.wheel_start_xy is None:
            self.wheel_start_xy = self.wheel_xy

    def on_lidar_odom(self, msg: Odometry) -> None:
        if self.lidar_distance.update(
            msg.pose.pose.position.x, msg.pose.pose.position.y
        ):
            self.lidar_odom_time = time.monotonic()

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
        self.corridor_range_m = robust_corridor_range(values)
        self.scan_time = time.monotonic()

    def stop(self, result: str) -> None:
        self.result = result
        self.pub.publish(Twist())

    def wheel_distance(self) -> float:
        if self.wheel_start_xy is None or self.wheel_xy is None:
            return 0.0
        return math.hypot(
            self.wheel_xy[0] - self.wheel_start_xy[0],
            self.wheel_xy[1] - self.wheel_start_xy[1],
        )

    def clearance_distance(self) -> float:
        if self.speed < 0.0:
            return 0.0
        return forward_clearance_progress(
            self.start_corridor_range_m, self.corridor_range_m
        )

    def control_distance(self) -> float:
        return conservative_progress(
            self.lidar_distance.distance_m, self.clearance_distance()
        )

    def tick(self) -> None:
        now = time.monotonic()
        if self.result != "WAITING" and self.result != "RUNNING":
            self.pub.publish(Twist())
            return
        if (
            self.wheel_start_xy is None
            or self.lidar_distance.previous is None
            or self.scan_time == 0.0
        ):
            return
        if self.started == 0.0:
            self.started = now
            self.result = "RUNNING"
            self.phase = "PULSE"
            self.phase_started = now
            self.start_clearance_m = self.clearance_m
            self.start_corridor_range_m = self.corridor_range_m
            self.cycle_start_distance_m = self.control_distance()
            direction = "forward" if self.speed >= 0.0 else "reverse"
            print(
                f"START direction={direction} clearance={self.clearance_m:.3f}m "
                f"target={self.target_m:.3f}m",
                flush=True,
            )
        if (
            now - self.wheel_odom_time > 0.6
            or now - self.lidar_odom_time > 0.6
            or now - self.scan_time > 0.6
        ):
            self.stop(
                "STOP_STALE_TELEMETRY_"
                f"wheel={now - self.wheel_odom_time:.3f}s_"
                f"lidar={now - self.lidar_odom_time:.3f}s_"
                f"scan={now - self.scan_time:.3f}s"
            )
        elif self.clearance_m < 0.55:
            self.stop(f"STOP_LIDAR_{self.clearance_m:.3f}M")
        elif now - self.started >= self.timeout_s:
            self.stop("STOP_TIMEOUT")
        elif self.phase == "PULSE":
            if self.control_distance() > self.target_m + self.tolerance_m:
                self.phase = "SETTLE"
                self.phase_started = now
                self.pub.publish(Twist())
            elif now - self.phase_started < self.active_pulse_s:
                cmd = Twist()
                cmd.linear.x = self.speed
                self.pub.publish(cmd)
            else:
                self.phase = "SETTLE"
                self.phase_started = now
                self.pub.publish(Twist())
        elif now - self.phase_started < self.settle_s:
            self.pub.publish(Twist())
        else:
            distance_m = self.control_distance()
            progress_m = distance_m - self.cycle_start_distance_m
            if distance_m >= self.target_m - self.tolerance_m:
                if distance_m <= self.target_m + self.tolerance_m:
                    self.stop("PASS_TARGET_SETTLED")
                else:
                    self.stop("STOP_OVERSHOOT")
                return
            # Increase a pulse only when the previous one did not overcome the
            # drivetrain's starting threshold. Keep every pulse bounded.
            if progress_m < 0.005:
                self.active_pulse_s = min(0.35, self.active_pulse_s + 0.04)
            self.cycle_start_distance_m = distance_m
            self.phase = "PULSE"
            self.phase_started = now
            cmd = Twist()
            cmd.linear.x = self.speed
            self.pub.publish(cmd)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distance", type=float, default=0.50)
    parser.add_argument("--speed", type=float, default=0.10)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--pulse-on", type=float, default=0.12)
    parser.add_argument("--settle", type=float, default=0.60)
    parser.add_argument("--tolerance", type=float, default=0.03)
    args = parser.parse_args()
    rclpy.init()
    node = StraightTest(
        args.distance,
        args.speed,
        args.timeout,
        args.pulse_on,
        args.settle,
        args.tolerance,
    )
    try:
        armed, arm_message = node.arm()
        print(f"ARM success={armed} message={arm_message}", flush=True)
        if not armed:
            return
        while rclpy.ok() and node.result in ("WAITING", "RUNNING"):
            rclpy.spin_once(node, timeout_sec=0.1)
        end = time.monotonic() + 1.0
        while rclpy.ok() and time.monotonic() < end:
            node.pub.publish(Twist())
            rclpy.spin_once(node, timeout_sec=0.05)
        print(
            f"RESULT {node.result} lidar_distance="
            f"{node.lidar_distance.distance_m:.3f}m "
            f"clearance_distance={node.clearance_distance():.3f}m "
            f"control_distance={node.control_distance():.3f}m "
            f"wheel_distance={node.wheel_distance():.3f}m "
            f"clearance_start={node.start_clearance_m:.3f}m "
            f"clearance_end={node.clearance_m:.3f}m "
            f"lidar_rejected={node.lidar_distance.rejected_updates}",
            flush=True,
        )
    finally:
        node.pub.publish(Twist())
        node.disarm()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
