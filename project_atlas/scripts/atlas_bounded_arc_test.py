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
from sensor_msgs.msg import Imu, LaserScan
from std_msgs.msg import Int32, String
from std_srvs.srv import Trigger

from atlas_scan_geometry import ray_in_base_sector
from atlas_straight_distance_core import IncrementalPlanarDistance


class ArcTest(Node):
    def __init__(self, distance, speed, angular, timeout, pulse_on, settle):
        super().__init__("atlas_bounded_arc_test")
        self.target, self.speed, self.angular, self.timeout = distance, speed, angular, timeout
        self.start = self.pose = None
        self.odom_at = self.lidar_odom_at = self.scan_at = self.started = 0.0
        # At this low commissioning speed, a 3 cm inter-sample pose change is
        # already implausible. Reject RF2O jumps instead of treating them as
        # achieved physical travel.
        self.lidar_distance = IncrementalPlanarDistance(max_step_m=0.03)
        self.encoder_health = {}
        self.last_critical_health = {}
        self.encoder_health_at = 0.0
        self.encoder_counts = [None, None, None, None]
        self.encoder_start_counts = None
        self.gyro_turn_rad = {"im10a": 0.0, "board": 0.0}
        self.gyro_last_at = {"im10a": 0.0, "board": 0.0}
        self.clearance = math.inf
        self.result = "WAITING"
        self.phase = "WAITING"
        self.phase_started = 0.0
        self.pulse_on = pulse_on
        self.settle = settle
        self.armed = False
        self.pub = self.create_publisher(Twist, "/cmd_vel_commission", 10)
        self.arm_client = self.create_client(Trigger, "/atlas/commission/arm")
        self.disarm_client = self.create_client(Trigger, "/atlas/commission/disarm")
        self.create_subscription(Odometry, "/yahboom/odom", self.on_odom, 20)
        self.create_subscription(Odometry, "/lidar/odom", self.on_lidar_odom, 20)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.create_subscription(String, "/atlas/encoder_health", self.on_encoder_health, 20)
        self.create_subscription(
            Imu, "/im10a/imu/unvalidated",
            lambda msg: self.on_gyro("im10a", msg), 20,
        )
        self.create_subscription(
            Imu, "/imu/data", lambda msg: self.on_gyro("board", msg), 20
        )
        for index in range(4):
            self.create_subscription(
                Int32,
                f"/yahboom/encoder/m{index + 1}",
                lambda msg, i=index: self.on_encoder(i, msg),
                20,
            )
        self.create_timer(0.05, self.tick)

    def on_encoder(self, index, msg):
        self.encoder_counts[index] = int(msg.data)

    def encoder_deltas(self):
        if self.encoder_start_counts is None:
            return [None, None, None, None]
        return [
            None if current is None or start is None else current - start
            for start, current in zip(self.encoder_start_counts, self.encoder_counts)
        ]

    def on_gyro(self, source, msg):
        now = time.monotonic()
        previous = self.gyro_last_at[source]
        self.gyro_last_at[source] = now
        rate = float(msg.angular_velocity.z)
        if (self.started and previous and math.isfinite(rate)
                and 0.0 < now - previous <= 0.30):
            self.gyro_turn_rad[source] += rate * (now - previous)

    def gyro_turn_degrees(self):
        return {
            source: math.degrees(value)
            for source, value in self.gyro_turn_rad.items()
        }

    def selected_encoder_motion(self):
        values = self.encoder_deltas()[:3]
        return any(value is not None and abs(value) >= 50 for value in values)

    def turn_evidence(self):
        angles = self.gyro_turn_degrees()
        # Mounting/sign conventions are reported separately; short-term turn
        # magnitude is valid evidence only when LiDAR or encoders corroborate.
        gyro_deg = max((abs(value) for value in angles.values()), default=0.0)
        lidar_motion = self.lidar_distance.distance_m >= 0.01
        encoder_motion = self.selected_encoder_motion()
        return gyro_deg, lidar_motion, encoder_motion

    def arm(self):
        # Discovery may be slow under the full ATLAS workload. Waiting longer
        # does not arm motion; the 20-second lease starts only on success.
        if not self.arm_client.wait_for_service(timeout_sec=12.0):
            return False, "commissioning arm service unavailable"
        future = self.arm_client.call_async(Trigger.Request())
        # Allow for service scheduling latency under the real camera/AI/
        # dashboard workload. The mux remains the authority and grants only
        # its existing bounded commissioning lease after a successful reply.
        rclpy.spin_until_future_complete(self, future, timeout_sec=8.0)
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
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)

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
        if str(self.encoder_health.get("state", "")).upper() == "CRITICAL":
            self.last_critical_health = dict(self.encoder_health)
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

    def wheel_distance(self):
        return 0.0 if self.start is None or self.pose is None else math.hypot(
            self.pose[0] - self.start[0], self.pose[1] - self.start[1]
        )

    def distance(self):
        return max(self.wheel_distance(), self.lidar_distance.distance_m)

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
                or not self.encoder_health_at
                or any(value is None for value in self.encoder_counts)):
            return
        if not self.started:
            self.started, self.result = now, "RUNNING"
            # Use the same car-like vx/wz pair during alignment and traction.
            # A zero-linear pre-steer command uses the base driver's direct
            # steering map, which does not match its moving curvature map and
            # caused traction to remain inhibited for the whole short pulse.
            self.phase, self.phase_started = "PULSE", now
            self.encoder_start_counts = list(self.encoder_counts)
            print(f"START clearance={self.clearance:.3f}m target={self.target:.3f}m", flush=True)
        encoder_state = str(self.encoder_health.get("state", "MISSING")).upper()
        if (now - self.odom_at > 0.6 or now - self.lidar_odom_at > 0.6
                or now - self.scan_at > 0.6 or now - self.encoder_health_at > 0.6):
            self.stop("STOP_STALE_TELEMETRY")
        elif encoder_state in ("CRITICAL", "INVALID", "MISSING", "QUALIFYING"):
            self.stop("STOP_ENCODER_" + encoder_state)
        elif self.clearance < 0.55:
            self.stop(f"STOP_LIDAR_{self.clearance:.3f}M")
        elif self.turn_evidence()[0] >= 8.0 and (
            self.turn_evidence()[1] or self.turn_evidence()[2]
        ):
            self.stop("PASS_MULTI_SENSOR_TURN")
        elif self.phase == "VERIFY":
            # Stop traction immediately at the distance target, then allow a
            # short window for IMU/LiDAR samples timestamped during the pulse
            # to arrive. Previously the validator declared disagreement one
            # callback before both IMUs reported the completed turn.
            self.pub.publish(Twist())
            if now - self.phase_started >= 0.75:
                gyro_deg, lidar_motion, encoder_motion = self.turn_evidence()
                evidence_count = sum((
                    gyro_deg >= 3.0, lidar_motion, encoder_motion,
                ))
                self.stop(
                    "PASS_MULTI_SENSOR_DISTANCE"
                    if evidence_count >= 2
                    else "STOP_SENSOR_DISAGREEMENT"
                )
        elif self.distance() >= self.target:
            gyro_deg, lidar_motion, encoder_motion = self.turn_evidence()
            evidence_count = sum((
                gyro_deg >= 3.0, lidar_motion, encoder_motion,
            ))
            if evidence_count >= 2:
                self.stop("PASS_MULTI_SENSOR_DISTANCE")
            else:
                self.phase, self.phase_started = "VERIFY", now
                self.pub.publish(Twist())
        elif now - self.started >= self.timeout:
            self.stop("STOP_TIMEOUT")
        elif self.phase == "PRESTEER" and now - self.phase_started < 1.0:
            command = Twist()
            command.angular.z = self.angular
            self.pub.publish(command)
        elif self.phase == "PRESTEER":
            self.phase, self.phase_started = "PULSE", now
            command = Twist()
            command.linear.x, command.angular.z = self.speed, self.angular
            self.pub.publish(command)
        elif self.phase == "PULSE" and now - self.phase_started < self.pulse_on:
            command = Twist()
            command.linear.x, command.angular.z = self.speed, self.angular
            self.pub.publish(command)
        elif self.phase == "PULSE":
            self.phase, self.phase_started = "SETTLE", now
            command = Twist()
            command.angular.z = self.angular
            self.pub.publish(command)
        elif now - self.phase_started < self.settle:
            command = Twist()
            command.angular.z = self.angular
            self.pub.publish(command)
        else:
            self.phase, self.phase_started = "PULSE", now
            command = Twist()
            command.linear.x, command.angular.z = self.speed, self.angular
            self.pub.publish(command)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distance", type=float, default=0.20)
    parser.add_argument("--speed", type=float, default=0.08)
    parser.add_argument("--angular", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--pulse-on", type=float, default=0.10)
    parser.add_argument("--settle", type=float, default=0.60)
    args = parser.parse_args()
    rclpy.init()
    node = ArcTest(
        args.distance, args.speed, args.angular, args.timeout,
        args.pulse_on, args.settle,
    )
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
              f"wheel_distance={node.wheel_distance():.3f}m "
              f"lidar_rejected={node.lidar_distance.rejected_updates} "
              f"clearance={node.clearance:.3f}m "
              f"encoder_state={node.encoder_health.get('state', 'MISSING')} "
              f"encoder_deltas={node.encoder_deltas()} "
              f"gyro_turn_deg={json.dumps(node.gyro_turn_degrees(), sort_keys=True)} "
              f"turn_evidence={node.turn_evidence()} "
              f"critical_health={json.dumps(node.last_critical_health, sort_keys=True)}",
              flush=True)
    finally:
        node.pub.publish(Twist())
        node.disarm()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
