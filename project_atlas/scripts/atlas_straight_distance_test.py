#!/usr/bin/env python3
"""Bounded straight-distance commissioning test with a LiDAR stop guard."""

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
from std_msgs.msg import Int32, String
from std_srvs.srv import Trigger

from atlas_scan_geometry import ray_in_base_sector
from atlas_straight_distance_core import (
    conservative_corridor_range,
    IncrementalPlanarDistance,
    conservative_progress,
    corridor_clearance_progress,
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
        # Never allow a stale/legacy CLI value to create a long open-loop
        # burst.  Sensor updates can lag while the drivetrain is loaded, so
        # every motion pulse stays short even when the caller asks for more.
        self.pulse_on_s = max(0.05, min(0.35, float(pulse_on_s)))
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
        self.guard_corridor_range_m = math.inf
        self.start_guard_corridor_range_m = math.inf
        self.scan_time = 0.0
        self.started = 0.0
        self.phase = "WAITING"
        self.phase_started = 0.0
        self.cycle_start_distance_m = 0.0
        self.active_pulse_s = self.pulse_on_s
        self.target_seen_since = 0.0
        self.result = "WAITING"
        self.encoder_counts = [None, None, None, None]
        self.encoder_start_counts = None
        self.encoder_health = {}
        self.armed = False
        self.pub = self.create_publisher(Twist, "/cmd_vel_commission", 10)
        self.arm_client = self.create_client(Trigger, "/atlas/commission/arm")
        self.disarm_client = self.create_client(Trigger, "/atlas/commission/disarm")
        self.create_subscription(Odometry, "/yahboom/odom", self.on_wheel_odom, 20)
        self.create_subscription(Odometry, "/lidar/odom", self.on_lidar_odom, 20)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        for index in range(4):
            self.create_subscription(
                Int32,
                f"/yahboom/encoder/m{index + 1}",
                lambda msg, i=index: self.on_encoder(i, msg),
                20,
            )
        self.create_subscription(
            String, "/atlas/encoder_health", self.on_encoder_health, 20
        )
        self.create_timer(0.05, self.tick)

    def on_encoder(self, index: int, msg: Int32) -> None:
        self.encoder_counts[index] = int(msg.data)

    def on_encoder_health(self, msg: String) -> None:
        try:
            value = json.loads(msg.data)
            self.encoder_health = value if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            self.encoder_health = {}

    def encoder_deltas(self) -> list[int | None]:
        if self.encoder_start_counts is None:
            return [None, None, None, None]
        return [
            None if current is None or start is None else current - start
            for start, current in zip(self.encoder_start_counts, self.encoder_counts)
        ]

    def arm(self) -> tuple[bool, str]:
        # A fresh Fast DDS participant can need several seconds to discover
        # the already-running mux on a loaded Jetson.  This wait grants no
        # motion authority; the lease still begins only after Trigger succeeds.
        if not self.arm_client.wait_for_service(timeout_sec=12.0):
            return False, "commissioning arm service unavailable"
        future = self.arm_client.call_async(Trigger.Request())
        # The fully loaded Jetson can take several seconds to schedule the mux
        # service response. Waiting longer does not grant authority: the mux
        # creates its bounded 20-second lease only when the response succeeds.
        rclpy.spin_until_future_complete(self, future, timeout_sec=8.0)
        response = future.result()
        if response is None:
            return False, "commissioning arm request timed out"
        self.armed = bool(response.success)
        return self.armed, str(response.message)

    def disarm(self) -> None:
        self.armed = False
        if not self.disarm_client.wait_for_service(timeout_sec=0.5):
            return
        future = self.disarm_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)

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
        self.guard_corridor_range_m = conservative_corridor_range(values)
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
        return corridor_clearance_progress(
            self.start_corridor_range_m, self.corridor_range_m
        )

    def nearest_clearance_distance(self) -> float:
        """Conservative travel guard from the nearest ray in the corridor.

        The robust median remains useful for measurement, but it can stay
        almost unchanged when the rover approaches one side of a doorway or
        wall.  A decreasing nearest range must therefore be allowed to stop a
        commissioning run; it never grants permission to move.
        """
        return corridor_clearance_progress(
            self.start_clearance_m, self.clearance_m
        )

    def guard_clearance_distance(self) -> float:
        return corridor_clearance_progress(
            self.start_guard_corridor_range_m,
            self.guard_corridor_range_m,
        )

    def control_distance(self) -> float:
        # Only stable LiDAR odometry and the robust corridor statistic may
        # prove target travel.  The nearest ray is deliberately excluded: it
        # is a conservative stop guard, never evidence of successful motion.
        return conservative_progress(
            self.lidar_distance.distance_m, self.clearance_distance()
        )

    def tick(self) -> None:
        now = time.monotonic()
        if not self.armed:
            return
        if self.result != "WAITING" and self.result != "RUNNING":
            self.pub.publish(Twist())
            return
        if (
            self.wheel_start_xy is None
            or self.lidar_distance.previous is None
            or self.scan_time == 0.0
            or any(value is None for value in self.encoder_counts)
            or str(self.encoder_health.get("state", "MISSING")).upper()
            not in ("READY", "HEALTHY", "DEGRADED")
        ):
            return
        if self.started == 0.0:
            self.started = now
            self.result = "RUNNING"
            self.phase = "PULSE"
            self.phase_started = now
            self.start_clearance_m = self.clearance_m
            self.start_corridor_range_m = self.corridor_range_m
            self.start_guard_corridor_range_m = self.guard_corridor_range_m
            self.encoder_start_counts = list(self.encoder_counts)
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
        elif str(self.encoder_health.get("state", "MISSING")).upper() in (
            "CRITICAL", "INVALID", "MISSING", "QUALIFYING"
        ):
            self.stop(
                "STOP_ENCODER_"
                + str(self.encoder_health.get("state", "MISSING")).upper()
            )
        elif self.clearance_m < 0.55:
            self.stop(f"STOP_LIDAR_{self.clearance_m:.3f}M")
        elif self.guard_clearance_distance() > (
            self.target_m + self.tolerance_m
        ):
            self.stop(
                "STOP_CORRIDOR_CLEARANCE_GUARD_"
                f"{self.guard_clearance_distance():.3f}M"
            )
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
                if distance_m > self.target_m + self.tolerance_m:
                    self.stop("STOP_OVERSHOOT")
                    return
                # A single nearest LiDAR ray can change as the rover vibrates
                # or the beam moves across an edge.  Require the conservative
                # target estimate to remain in-range across several scans
                # before declaring a pass.
                if self.target_seen_since == 0.0:
                    self.target_seen_since = now
                if now - self.target_seen_since >= 0.30:
                    self.stop("PASS_TARGET_SETTLED")
                    return
                self.pub.publish(Twist())
                return
            self.target_seen_since = 0.0
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
            f"nearest_clearance_distance="
            f"{node.nearest_clearance_distance():.3f}m "
            f"guard_clearance_distance="
            f"{node.guard_clearance_distance():.3f}m "
            f"control_distance={node.control_distance():.3f}m "
            f"wheel_distance={node.wheel_distance():.3f}m "
            f"clearance_start={node.start_clearance_m:.3f}m "
            f"clearance_end={node.clearance_m:.3f}m "
            f"lidar_rejected={node.lidar_distance.rejected_updates} "
            f"encoder_deltas={node.encoder_deltas()} "
            f"encoder_state={node.encoder_health.get('state', 'MISSING')} "
            f"consensus={node.encoder_health.get('consensus_state', 'MISSING')}",
            flush=True,
        )
    finally:
        node.pub.publish(Twist())
        node.disarm()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
