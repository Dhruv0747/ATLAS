#!/usr/bin/env python3
import json
import math
import re
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Point
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import LaserScan, NavSatFix
from std_msgs.msg import Float32, Int32, String
from visualization_msgs.msg import Marker, MarkerArray


RADAR_RE = re.compile(
    r"T(?P<id>\d+):x=(?P<x>-?\d+(?:\.\d+)?)mm,y=(?P<y>-?\d+(?:\.\d+)?)mm(?:,spd=(?P<speed>-?\d+(?:\.\d+)?)cm/s)?"
)


class AtlasSupervisor(Node):
    def __init__(self):
        super().__init__("atlas_supervisor")
        self.last = {}
        self.values = {}
        self.radar_targets = []
        self.last_scan_summary = 0.0

        self.marker_pub = self.create_publisher(MarkerArray, "/radar/markers", 10)
        self.health_pub = self.create_publisher(String, "/atlas/health", 10)
        self.ready_pub = self.create_publisher(String, "/atlas/readiness", 10)
        self.fresh_pub = self.create_publisher(String, "/atlas/sensor_freshness", 10)
        self.diag_pub = self.create_publisher(DiagnosticArray, "/atlas/diagnostics", 10)

        self.create_subscription(String, "/radar/targets", self.radar_cb, 10)
        self.create_subscription(Float32, "/radar/target_count", lambda m: self.setv("radar_count", m.data), 10)
        self.create_subscription(LaserScan, "/scan", self.scan_cb, 10)
        self.create_subscription(Float32, "/ultrasonic/front_mm", lambda m: self.setv("us_front", m.data), 10)
        self.create_subscription(Float32, "/ultrasonic/left_mm", lambda m: self.setv("us_left", m.data), 10)
        self.create_subscription(Float32, "/ultrasonic/right_mm", lambda m: self.setv("us_right", m.data), 10)
        self.create_subscription(Float32, "/battery/voltage", lambda m: self.setv("battery_v", m.data), 10)
        self.create_subscription(Float32, "/battery/current", lambda m: self.setv("battery_a", m.data), 10)
        self.create_subscription(Float32, "/battery/percent", lambda m: self.setv("battery_pct", m.data), 10)
        self.create_subscription(Float32, "/cellular/signal_percent", lambda m: self.setv("cell_signal", m.data), 10)
        self.create_subscription(String, "/cellular/access_tech", lambda m: self.setv("cell_tech", m.data), 10)
        self.create_subscription(Float32, "/gps/satellites", lambda m: self.setv("gps_sats", m.data), 10)
        self.create_subscription(NavSatFix, "/gps/fix", self.gps_cb, 10)
        self.create_subscription(Float32, "/imu/heading", lambda m: self.setv("heading", m.data), 10)
        self.create_subscription(Odometry, "/odom", self.odom_cb, 10)
        for topic, key in [
            ("/yahboom/encoder/m1", "enc_m1"),
            ("/yahboom/encoder/m2", "enc_m2"),
            ("/yahboom/encoder/m3", "enc_m3"),
            ("/yahboom/encoder/m4", "enc_m4"),
        ]:
            self.create_subscription(Int32, topic, lambda m, k=key: self.setv(k, m.data), 10)

        self.create_timer(1.0, self.publish_status)
        self.get_logger().info("ATLAS supervisor active: health + radar markers + readiness")

    def setv(self, key, value):
        self.values[key] = value
        self.last[key] = time.time()

    def scan_cb(self, msg):
        now = time.time()
        if now - self.last_scan_summary < 0.50:
            return
        self.last_scan_summary = now
        finite = [r for r in msg.ranges if math.isfinite(r) and msg.range_min <= r <= msg.range_max]
        self.setv("lidar_points", len(finite))
        self.setv("lidar_nearest_m", min(finite) if finite else 0.0)

    def gps_cb(self, msg):
        self.setv("gps_status", msg.status.status)
        if math.isfinite(msg.latitude) and math.isfinite(msg.longitude):
            self.setv("gps_lat", msg.latitude)
            self.setv("gps_lon", msg.longitude)

    def odom_cb(self, msg):
        self.setv("odom_x", msg.pose.pose.position.x)
        self.setv("odom_y", msg.pose.pose.position.y)
        self.setv("odom_vx", msg.twist.twist.linear.x)
        self.setv("odom_wz", msg.twist.twist.angular.z)

    def radar_cb(self, msg):
        self.setv("radar_text", msg.data)
        targets = []
        for match in RADAR_RE.finditer(msg.data or ""):
            x_mm = float(match.group("x"))
            y_mm = float(match.group("y"))
            speed = float(match.group("speed") or 0.0)
            targets.append({
                "id": int(match.group("id")),
                "x_m": x_mm / 1000.0,
                "y_m": y_mm / 1000.0,
                "speed_mps": speed / 100.0,
            })
        self.radar_targets = targets
        self.publish_markers()

    def publish_markers(self):
        arr = MarkerArray()
        now = self.get_clock().now().to_msg()

        clear = Marker()
        clear.header.frame_id = "base_link"
        clear.header.stamp = now
        clear.ns = "radar_targets"
        clear.id = 0
        clear.action = Marker.DELETEALL
        arr.markers.append(clear)

        for target in self.radar_targets:
            marker = Marker()
            marker.header.frame_id = "base_link"
            marker.header.stamp = now
            marker.ns = "radar_targets"
            marker.id = target["id"]
            marker.type = Marker.SPHERE
            marker.action = Marker.ADD
            marker.pose.position.x = target["y_m"]
            marker.pose.position.y = -target["x_m"]
            marker.pose.position.z = 0.25
            marker.pose.orientation.w = 1.0
            marker.scale.x = 0.22
            marker.scale.y = 0.22
            marker.scale.z = 0.22
            marker.color.r = 1.0
            marker.color.g = 0.15 if target["y_m"] < 0.8 else 0.8
            marker.color.b = 0.05
            marker.color.a = 0.95
            marker.lifetime.sec = 2
            arr.markers.append(marker)

            text = Marker()
            text.header.frame_id = "base_link"
            text.header.stamp = now
            text.ns = "radar_labels"
            text.id = 100 + target["id"]
            text.type = Marker.TEXT_VIEW_FACING
            text.action = Marker.ADD
            text.pose.position = Point(x=target["y_m"], y=-target["x_m"], z=0.55)
            text.pose.orientation.w = 1.0
            text.scale.z = 0.22
            text.color.r = 0.0
            text.color.g = 0.95
            text.color.b = 1.0
            text.color.a = 1.0
            text.text = f"T{target['id']} {target['y_m']:.2f}m {target['speed_mps']:.2f}m/s"
            text.lifetime.sec = 2
            arr.markers.append(text)

        self.marker_pub.publish(arr)

    def age(self, key):
        return time.time() - self.last.get(key, 0.0)

    def fresh(self, key, max_age=2.5):
        return key in self.last and self.age(key) <= max_age

    def publish_status(self):
        checks = {
            "lidar": self.fresh("lidar_points"),
            "radar": self.fresh("radar_text"),
            "ultrasonic_front": self.fresh("us_front"),
            "ultrasonic_left": self.fresh("us_left"),
            "ultrasonic_right": self.fresh("us_right"),
            "battery": self.fresh("battery_v"),
            "cellular": self.fresh("cell_signal", 8.0),
            "imu": self.fresh("heading"),
            "odom": self.fresh("odom_x"),
            "encoders": all(self.fresh(k) for k in ("enc_m1", "enc_m2", "enc_m3", "enc_m4")),
        }
        stale = [k for k, ok in checks.items() if not ok]
        warnings = []

        voltage = self.values.get("battery_v")
        if isinstance(voltage, (int, float)) and voltage < 11.2:
            warnings.append(f"battery_low:{voltage:.2f}V")
        nearest = self.values.get("lidar_nearest_m")
        if isinstance(nearest, (int, float)) and 0 < nearest < 0.35:
            warnings.append(f"lidar_close:{nearest:.2f}m")
        us_front = self.values.get("us_front")
        if isinstance(us_front, (int, float)) and 0 < us_front < 300:
            warnings.append(f"front_ultrasonic_close:{us_front:.0f}mm")

        ready_for_mapping = (
            checks["lidar"]
            and checks["odom"]
            and checks["imu"]
            and checks["battery"]
            and len(warnings) == 0
        )
        ready_for_autonomy = ready_for_mapping and checks["radar"] and checks["ultrasonic_front"]

        payload = {
            "state": "OK" if not stale and not warnings else "WARN",
            "stale": stale,
            "warnings": warnings,
            "ready_for_mapping": ready_for_mapping,
            "ready_for_autonomy": ready_for_autonomy,
            "radar_targets": len(self.radar_targets),
            "battery_v": voltage,
            "cell_signal": self.values.get("cell_signal"),
            "gps_sats": self.values.get("gps_sats"),
        }
        text = json.dumps(payload, separators=(",", ":"))
        self.health_pub.publish(String(data=text))
        self.ready_pub.publish(String(data="AUTO_READY" if ready_for_autonomy else "MANUAL_OR_MAPPING_ONLY"))
        freshness = {k: round(self.age(k), 1) if k in self.last else None for k in sorted(self.last)}
        self.fresh_pub.publish(String(data=json.dumps(freshness, separators=(",", ":"))))
        self.publish_diag(payload, checks)

    def publish_diag(self, payload, checks):
        arr = DiagnosticArray()
        arr.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = "ATLAS Supervisor"
        status.hardware_id = "project_atlas_pi5"
        status.level = DiagnosticStatus.OK if payload["state"] == "OK" else DiagnosticStatus.WARN
        status.message = payload["state"]
        for key, val in checks.items():
            status.values.append(KeyValue(key=key, value=str(val)))
        for key in ("ready_for_mapping", "ready_for_autonomy", "radar_targets", "battery_v", "cell_signal", "gps_sats"):
            status.values.append(KeyValue(key=key, value=str(payload.get(key))))
        arr.status.append(status)
        self.diag_pub.publish(arr)


def main():
    rclpy.init()
    node = AtlasSupervisor()
    rclpy.spin(node)


if __name__ == "__main__":
    main()
