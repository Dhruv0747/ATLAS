#!/usr/bin/env python3
"""Stopped-only camera scan adviser; never publishes rover velocity."""

import json
import math
import os
import re
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, Int32, String


HOME_FILE = "/home/jetson/.config/systemd/user/atlas-uno-r4-sensor-hub.service.d/camera-home.conf"


def saved_home():
    pan = int(os.environ.get("ATLAS_CAMERA_PAN_HOME_US", "1725"))
    tilt = int(os.environ.get("ATLAS_CAMERA_TILT_HOME_US", "1500"))
    try:
        text = open(HOME_FILE, encoding="utf-8").read()
        match = re.search(r"ATLAS_CAMERA_PAN_HOME_US=(\d+)", text)
        pan = int(match.group(1)) if match else pan
        match = re.search(r"ATLAS_CAMERA_TILT_HOME_US=(\d+)", text)
        tilt = int(match.group(1)) if match else tilt
    except OSError:
        pass
    return pan, tilt


class ActiveVision(Node):
    SETTLE_S = 1.0
    STALE_S = 1.0
    AI_DEADLINE_S = 4.0

    def __init__(self):
        super().__init__("atlas_active_vision")
        self.home_pan, self.home_tilt = saved_home()
        span = 350
        self.views = [
            ("LEFT", min(2300, self.home_pan + span)),
            ("CENTRE", self.home_pan),
            ("RIGHT", max(700, self.home_pan - span)),
        ]
        self.scan = None
        self.scan_at = 0.0
        self.detections = None
        self.detections_at = 0.0
        self.last_motion = 0.0
        self.active = False
        self.index = -1
        self.command_at = 0.0
        self.results = []
        self.pan_pub = self.create_publisher(Int32, "/camera/bottom_servo_cmd_us", 10)
        self.tilt_pub = self.create_publisher(Int32, "/camera/second_servo_cmd_us", 10)
        self.tracker_pub = self.create_publisher(Bool, "/atlas/camera_tracking/enabled", 10)
        self.status_pub = self.create_publisher(String, "/atlas/active_vision/status", 10)
        self.create_subscription(String, "/atlas/active_vision/request", self.request, 10)
        self.create_subscription(Twist, "/cmd_vel", self.motion, 10)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        # Best-effort avoids a stale reliable queue after a detector restart;
        # active vision only needs the newest inference frame.
        self.create_subscription(
            String, "/camera/detections/json", self.on_detections, qos_profile_sensor_data
        )
        self.create_timer(0.1, self.tick)
        self.report("READY", detail="stopped-only; no motor authority")

    def report(self, state, **extra):
        payload = {"state": state, "active": self.active, "home_pan_us": self.home_pan,
                   "motor_authority": False, **extra}
        self.status_pub.publish(String(data=json.dumps(payload, separators=(",", ":"))))

    def motion(self, msg):
        if abs(msg.linear.x) > 0.005 or abs(msg.angular.z) > 0.005:
            self.last_motion = time.monotonic()
            if self.active:
                self.finish("CANCELLED_MOTION")

    def on_scan(self, msg):
        self.scan, self.scan_at = msg, time.monotonic()

    def on_detections(self, msg):
        try:
            self.detections = json.loads(msg.data)
            self.detections_at = time.monotonic()
        except (TypeError, ValueError):
            self.detections = None

    def request(self, msg):
        now = time.monotonic()
        if str(msg.data).strip().lower() not in ("inspect", "scan", "look"):
            return
        if self.active:
            self.report("REJECTED_BUSY")
        elif now - self.last_motion < 1.0:
            self.report("REJECTED_ROVER_NOT_STATIONARY")
        elif self.scan is None or now - self.scan_at > self.STALE_S:
            self.report("REJECTED_LIDAR_STALE")
        elif self.detections is None or now - self.detections_at > self.AI_DEADLINE_S:
            self.report(
                "REJECTED_CAMERA_AI_STALE",
                camera_ai_age_s=None if not self.detections_at else round(now - self.detections_at, 3),
                lidar_age_s=round(now - self.scan_at, 3),
            )
        else:
            self.active, self.index, self.results = True, -1, []
            self.tracker_pub.publish(Bool(data=False))
            self.tilt_pub.publish(Int32(data=self.home_tilt))
            self.advance()

    def advance(self):
        self.index += 1
        if self.index >= len(self.views):
            self.finish("COMPLETE")
            return
        name, pan = self.views[self.index]
        self.pan_pub.publish(Int32(data=pan))
        self.command_at = time.monotonic()
        self.report("SCANNING", view=name, pan_us=pan)

    def clearance(self, pan):
        # Saved forward pan is zero bearing; +700 us is approximately +45 degrees.
        centre = (pan - self.home_pan) / 700.0 * math.radians(45.0)
        values = []
        for i, distance in enumerate(self.scan.ranges):
            if not math.isfinite(distance) or not self.scan.range_min <= distance <= self.scan.range_max:
                continue
            bearing = math.atan2(math.sin(self.scan.angle_min + i * self.scan.angle_increment + math.pi),
                                 math.cos(self.scan.angle_min + i * self.scan.angle_increment + math.pi))
            if abs(math.atan2(math.sin(bearing-centre), math.cos(bearing-centre))) <= math.radians(12):
                values.append(float(distance))
        return min(values) if values else None

    def tick(self):
        if not self.active or time.monotonic() - self.command_at < self.SETTLE_S:
            return
        # Never score a view using an inference captured at the previous
        # camera angle. Wait for a post-move frame, then fail closed.
        if self.detections_at <= self.command_at:
            if time.monotonic() - self.command_at > self.AI_DEADLINE_S:
                self.finish("CANCELLED_CAMERA_AI_TIMEOUT")
            return
        name, pan = self.views[self.index]
        objects = [d.get("label", "object") for d in (self.detections or {}).get("detections", [])
                   if float(d.get("confidence", 0.0) or 0.0) >= 0.45]
        self.results.append({"view": name, "clearance_m": self.clearance(pan), "objects": objects[:8]})
        self.advance()

    def finish(self, state):
        self.pan_pub.publish(Int32(data=self.home_pan))
        self.tilt_pub.publish(Int32(data=self.home_tilt))
        recommendation = None
        valid = [r for r in self.results if r["clearance_m"] is not None]
        if valid:
            recommendation = max(valid, key=lambda r: r["clearance_m"])["view"]
        self.active = False
        self.report(state, recommendation=recommendation, views=self.results,
                    note="advisory only; LiDAR/Nav2 must validate any route")


def main():
    rclpy.init()
    node = ActiveVision()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
