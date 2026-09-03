#!/usr/bin/env python3
import html
import glob
import ipaddress
import os
import json
import math
import re
import socket
import subprocess
import threading
import time
import signal

import cv2
import numpy as np
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import rclpy
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import NavSatFix, LaserScan, CompressedImage, Joy
from std_msgs.msg import Bool, Float32, String, Int32

PORT = 8088
SENSOR_HUB_CAMERA_SOCKET = os.environ.get(
    "ATLAS_SENSOR_HUB_CAMERA_SOCKET",
    "/run/user/1000/atlas-sensor-hub-camera.sock",
)
SENSOR_HUB_STATUS_PATH = os.environ.get(
    "ATLAS_SENSOR_HUB_STATUS_PATH",
    "/run/user/1000/atlas-sensor-hub-status.json",
)
COCO_LABELS = ['person','bicycle','car','motorcycle','airplane','bus','train','truck','boat','traffic light','fire hydrant','stop sign','parking meter','bench','bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe','backpack','umbrella','handbag','tie','suitcase','frisbee','skis','snowboard','sports ball','kite','baseball bat','baseball glove','skateboard','surfboard','tennis racket','bottle','wine glass','cup','fork','knife','spoon','bowl','banana','apple','sandwich','orange','broccoli','carrot','hot dog','pizza','donut','cake','chair','couch','potted plant','bed','dining table','toilet','tv','laptop','mouse','remote','keyboard','cell phone','microwave','oven','toaster','sink','refrigerator','book','clock','vase','scissors','teddy bear','hair drier','toothbrush']
AI_MODES = {"eco", "object", "face", "gesture", "color", "line", "follow"}
MANIFEST_JSON = """{
  "name": "Project ATLAS Rover",
  "short_name": "ATLAS",
  "description": "Project ATLAS rover command center",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "any",
  "background_color": "#020711",
  "theme_color": "#00d7ff",
  "icons": [
    {"src": "/logo.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/logo.png", "sizes": "512x512", "type": "image/png"}
  ]
}"""
SERVICES = ["rover-base", "rover-teleop", "atlas-uno-r4-sensor-hub", "rover-cellular", "rover-ups", "rover-daly-bms", "rover-atlas-supervisor", "rover-status-web"]
TODO = [
    ("GPS/NavIC", "Move GNSS antenna outside metal body; validate satellites later."),
    ("Encoder odom", "Calibrate Yahboom encoder ticks to real wheel distance."),
    ("Autonomy", "Finish robust Nav2 goal success and return-home behavior."),
    ("Radar Foxglove", "Publish radar targets as MarkerArray or PointCloud2."),
    ("Wiring polish", "Add labels, fuse notes, strain relief, final photos."),
]


def run(cmd, timeout=2):
    try:
        return subprocess.check_output(cmd, text=True, timeout=timeout, stderr=subprocess.STDOUT).strip()
    except Exception:
        return ""


def run_quiet(cmd, timeout=2):
    try:
        subprocess.check_call(cmd, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


SENSOR_HUB_CACHE_KEYS = {
    "i2c_status", "pca_status", "camera_servo_status",
    "outside_temperature", "outside_humidity", "outside_pressure",
    "outside_gas", "outside_status", "bme680_json",
    "thermal_status", "thermal_json",
    "us_status", "us_front", "us_left", "us_right", "us_rear",
    "radar_link",
}
_sensor_hub_cache_lock = threading.Lock()
_sensor_hub_cache_mtime = None
_sensor_hub_cache_payload = {"updated_at": 0.0, "data": {}}


def sensor_hub_cache_snapshot():
    """Read the UNO snapshot used when ROS discovery misses its publisher."""
    global _sensor_hub_cache_mtime, _sensor_hub_cache_payload
    try:
        stat = os.stat(SENSOR_HUB_STATUS_PATH)
    except OSError:
        with _sensor_hub_cache_lock:
            return _sensor_hub_cache_payload
    with _sensor_hub_cache_lock:
        if stat.st_mtime_ns == _sensor_hub_cache_mtime:
            return _sensor_hub_cache_payload
        try:
            with open(SENSOR_HUB_STATUS_PATH, encoding="utf-8") as stream:
                payload = json.load(stream)
            if payload.get("schema") != 1 or not isinstance(payload.get("data"), dict):
                return _sensor_hub_cache_payload
            clean = {}
            for key, item in payload["data"].items():
                if key not in SENSOR_HUB_CACHE_KEYS or not isinstance(item, dict):
                    continue
                if "value" not in item or not isinstance(item.get("ts"), (int, float)):
                    continue
                clean[key] = {"value": item["value"], "ts": float(item["ts"])}
            _sensor_hub_cache_payload = {
                "updated_at": float(payload.get("updated_at", 0.0)),
                "data": clean,
            }
            _sensor_hub_cache_mtime = stat.st_mtime_ns
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return _sensor_hub_cache_payload


class AtlasRosNode:
    def __init__(self):
        self.ready = False
        self.data = {}
        self.lock = threading.Lock()
        self.node = None
        self.pub = None
        self.pan_pub = None
        self.tilt_pub = None
        self.ai_pub = None
        self.pan_us = 1300
        self.tilt_us = 2100
        self.last_drive_command = 0.0
        self.drive_active = False
        self.last_raw_camera_encode = 0.0
        self.last_compressed_camera = 0.0
        self.panel_camera_frame = None
        self.panel_camera_source_ts = 0.0
        self.overview_camera_frame = None
        self.overview_camera_source_ts = 0.0
        self.last_scan_summary = 0.0
        self.last_motion_check = 0.0
        self.prev_motion_gray = None
        self.yolo_ready = os.path.exists(
            "/home/jetson/project_atlas/scripts/yolov8n_fp16.engine"
        )
        self.ai_mode = "eco"
        self.ai_model = None
        self.ai_input_name = None
        self.last_ai_check = 0.0
        self.ai_detections = []
        self._set("ai_mode", self.ai_mode)
        self._set("ai_status", "YOLO ready, off in Eco Mode" if self.yolo_ready else "YOLO model missing")
        self._set("companion_state", "STANDBY")
        self._set("companion_mode", "LOCAL SAFETY")
        self._set("companion_transcript", "Waiting for the ATLAS voice service")
        self._set("companion_intent", "None")
        self._set("companion_action", "No action selected")
        self._set("companion_response", "Voice firmware and ROS bridge are being prepared")
        self._set("companion_confirmation", "NOT REQUIRED")
        self._set("companion_rgb", "BLUE")
        self._set("companion_cloud", "NOT CONNECTED")
        self._set("agent_status", "Agent supervisor starting")
        self._set("agent_decision", "No mission selected")
        self._set("agent_state", "{}")
        self.spin_thread = threading.Thread(target=self._spin, daemon=True)
        self.spin_thread.start()

    def _set(self, key, value):
        with self.lock:
            self.data[key] = {"value": value, "ts": time.time()}

    def _spin(self):
        try:
            rclpy.init(args=None)
            self.node = rclpy.create_node("atlas_web_control")
            self.pub = self.node.create_publisher(Twist, "/cmd_vel_web", 10)
            self.pan_pub = self.node.create_publisher(
                Int32, "/camera/bottom_servo_cmd_us", 10
            )
            self.tilt_pub = self.node.create_publisher(
                Int32, "/camera/second_servo_cmd_us", 10
            )
            self.ai_pub = self.node.create_publisher(
                Bool, "/atlas/ai_enabled", 10
            )
            n = self.node
            n.create_subscription(String, "/ultrasonic/status", self._ultrasonic_status_cb, 10)
            n.create_subscription(
                String,
                "/arduino/i2c/status",
                lambda m: self._set("i2c_status", m.data),
                10,
            )
            n.create_subscription(
                String,
                "/arduino/pca9685/status",
                lambda m: self._set("pca_status", m.data),
                10,
            )
            n.create_subscription(
                String,
                "/camera/arducam/status",
                lambda m: self._set("camera_servo_status", m.data),
                10,
            )
            n.create_subscription(String, "/radar/targets", self._radar_targets_cb, 10)
            n.create_subscription(
                String, "/radar/hub/status",
                lambda m: self._set("radar_link", m.data), 10,
            )
            n.create_subscription(
                String, "/radar/decoder_status",
                lambda m: self._set("radar_decoder_status", m.data), 10,
            )
            n.create_subscription(String, "/thermal/amg8833/status", lambda m: self._set("thermal_status", m.data), 10)
            n.create_subscription(String, "/thermal/amg8833/json", lambda m: self._set("thermal_json", m.data), 10)
            n.create_subscription(
                Float32,
                "/environment/outside_temperature_c",
                lambda m: self._set("outside_temperature", m.data),
                10,
            )
            n.create_subscription(
                Float32,
                "/environment/outside_humidity_pct",
                lambda m: self._set("outside_humidity", m.data),
                10,
            )
            n.create_subscription(
                Float32,
                "/environment/pressure_hpa",
                lambda m: self._set("outside_pressure", m.data),
                10,
            )
            n.create_subscription(
                Float32,
                "/environment/gas_resistance_ohm",
                lambda m: self._set("outside_gas", m.data),
                10,
            )
            n.create_subscription(
                String,
                "/environment/bme680/json",
                lambda m: self._set("bme680_json", m.data),
                10,
            )
            n.create_subscription(
                String,
                "/environment/outside_status",
                lambda m: self._set("outside_status", m.data),
                10,
            )
            n.create_subscription(Float32, "/battery/voltage", lambda m: self._set("bat_voltage", m.data), 10)
            n.create_subscription(Float32, "/battery/current", lambda m: self._set("bat_current", m.data), 10)
            n.create_subscription(Float32, "/battery/percent", lambda m: self._set("bat_percent", m.data), 10)
            n.create_subscription(String, "/bms/status", lambda m: self._set("bms_status", m.data), 10)
            n.create_subscription(String, "/bms/json", lambda m: self._set("bms_json", m.data), 10)
            n.create_subscription(Float32, "/bms/voltage", lambda m: self._set("bms_voltage", m.data), 10)
            n.create_subscription(Float32, "/bms/current", lambda m: self._set("bms_current", m.data), 10)
            n.create_subscription(Float32, "/bms/percent", lambda m: self._set("bms_percent", m.data), 10)
            n.create_subscription(Float32, "/bms/power", lambda m: self._set("bms_power", m.data), 10)
            n.create_subscription(Float32, "/bms/cell1_voltage", lambda m: self._set("bms_cell1", m.data), 10)
            n.create_subscription(Float32, "/bms/cell2_voltage", lambda m: self._set("bms_cell2", m.data), 10)
            n.create_subscription(Float32, "/bms/cell3_voltage", lambda m: self._set("bms_cell3", m.data), 10)
            n.create_subscription(Float32, "/bms/cell4_voltage", lambda m: self._set("bms_cell4", m.data), 10)
            n.create_subscription(Float32, "/cellular/hat_voltage", lambda m: self._set("hat_voltage", m.data), 10)
            n.create_subscription(Float32, "/cellular/hat_current", lambda m: self._set("hat_current", m.data), 10)
            n.create_subscription(Float32, "/cellular/hat_power", lambda m: self._set("hat_power", m.data), 10)
            n.create_subscription(String, "/cellular/hat_status", lambda m: self._set("hat_status", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/input_voltage", lambda m: self._set("jetson_voltage", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/input_current", lambda m: self._set("jetson_current", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/input_power", lambda m: self._set("jetson_power", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/cpu_gpu_power", lambda m: self._set("jetson_cpu_gpu_power", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/soc_power", lambda m: self._set("jetson_soc_power", m.data), 10)
            n.create_subscription(String, "/jetson/power/status", lambda m: self._set("jetson_power_status", m.data), 10)
            n.create_subscription(String, "/jetson/carrier/json", lambda m: self._set("carrier_json", m.data), 10)
            n.create_subscription(String, "/jetson/carrier/status", lambda m: self._set("carrier_status", m.data), 10)
            n.create_subscription(String, "/ups/status", lambda m: self._set("ups_status", m.data), 10)
            n.create_subscription(Float32, "/ups/battery_voltage", lambda m: self._set("ups_bat_voltage", m.data), 10)
            n.create_subscription(Float32, "/ups/battery_current", lambda m: self._set("ups_bat_current", m.data), 10)
            n.create_subscription(Float32, "/ups/battery_power", lambda m: self._set("ups_bat_power", m.data), 10)
            n.create_subscription(Float32, "/ups/battery_percent", lambda m: self._set("ups_bat_percent", m.data), 10)
            n.create_subscription(Float32, "/ups/vbus_voltage", lambda m: self._set("ups_vbus_voltage", m.data), 10)
            n.create_subscription(Float32, "/ups/vbus_current", lambda m: self._set("ups_vbus_current", m.data), 10)
            n.create_subscription(Float32, "/ups/cell1_voltage", lambda m: self._set("ups_cell1", m.data), 10)
            n.create_subscription(Float32, "/ups/cell2_voltage", lambda m: self._set("ups_cell2", m.data), 10)
            n.create_subscription(Float32, "/ups/cell3_voltage", lambda m: self._set("ups_cell3", m.data), 10)
            n.create_subscription(Float32, "/ups/cell4_voltage", lambda m: self._set("ups_cell4", m.data), 10)
            n.create_subscription(Float32, "/cellular/signal_percent", lambda m: self._set("cell_signal", m.data), 10)
            n.create_subscription(String, "/cellular/access_tech", lambda m: self._set("cell_tech", m.data), 10)
            n.create_subscription(String, "/cellular/operator", lambda m: self._set("cell_operator", m.data), 10)
            n.create_subscription(Float32, "/gps/satellites", lambda m: self._set("gps_sats", m.data), 10)
            n.create_subscription(Float32, "/gps/hdop", lambda m: self._set("gps_hdop", m.data), 10)
            n.create_subscription(String, "/gps/constellations", lambda m: self._set("gps_const", m.data), 10)
            n.create_subscription(String, "/gps/arduino_status", lambda m: self._set("gps_arduino_status", m.data), 10)
            n.create_subscription(String, "/gps/receiver_status", lambda m: self._set("gps_receiver_status", m.data), 10)
            n.create_subscription(String, "/imu/dashboard_json", self._imu_dashboard_cb, 10)
            n.create_subscription(Float32, "/yahboom/imu/roll", lambda m: self._set("board_imu_roll", m.data), 10)
            n.create_subscription(Float32, "/yahboom/imu/pitch", lambda m: self._set("board_imu_pitch", m.data), 10)
            n.create_subscription(Float32, "/yahboom/imu/heading", lambda m: self._set("board_imu_heading", m.data), 10)
            n.create_subscription(Float32, "/motor_speed", lambda m: self._set("motor_speed", m.data), 10)
            n.create_subscription(Int32, "/yahboom/encoder/m1", lambda m: self._set("enc_m1", m.data), 10)
            n.create_subscription(Int32, "/yahboom/encoder/m2", lambda m: self._set("enc_m2", m.data), 10)
            n.create_subscription(Int32, "/yahboom/encoder/m3", lambda m: self._set("enc_m3", m.data), 10)
            n.create_subscription(Int32, "/yahboom/encoder/m4", lambda m: self._set("enc_m4", m.data), 10)
            n.create_subscription(LaserScan, "/scan", self._scan_cb, qos_profile_sensor_data)
            n.create_subscription(CompressedImage, "/camera/image_raw/compressed", self._camera_cb, qos_profile_sensor_data)
            n.create_subscription(CompressedImage, "/camera/detections/compressed", self._ai_camera_cb, 10)
            n.create_subscription(String, "/camera/detections/json", self._ai_detections_cb, 10)
            n.create_subscription(Float32, "/steering/front_angle_deg", lambda m: self._set("front_steer", m.data), 10)
            n.create_subscription(Float32, "/steering/rear_angle_deg", lambda m: self._set("rear_steer", m.data), 10)
            n.create_subscription(String, "/steering/mode", lambda m: self._set("steer_mode", m.data), 10)
            n.create_subscription(NavSatFix, "/gps/fix", lambda m: self._set("gps_fix", {"status": m.status.status, "lat": m.latitude, "lon": m.longitude}), 10)
            n.create_subscription(Odometry, "/odom", self._odom_cb, 10)
            n.create_subscription(Twist, "/cmd_vel", lambda m: self._set("cmd_vel", {"lin": m.linear.x, "ang": m.angular.z}), 10)
            n.create_subscription(String, "/atlas/health", lambda m: self._set("atlas_health", m.data), 10)
            n.create_subscription(String, "/atlas/readiness", lambda m: self._set("atlas_readiness", m.data), 10)
            n.create_subscription(String, "/atlas/sensor_freshness", lambda m: self._set("atlas_freshness", m.data), 10)
            n.create_subscription(String, "/atlas/agent/status", lambda m: self._set("agent_status", m.data), 10)
            n.create_subscription(String, "/atlas/agent/decision", lambda m: self._set("agent_decision", m.data), 10)
            n.create_subscription(String, "/atlas/agent/state", lambda m: self._set("agent_state", m.data), 10)
            n.create_subscription(String, "/atlas/agent_team/status", lambda m: self._set("agent_team_status", m.data), 10)
            n.create_subscription(String, "/atlas/experience/status", lambda m: self._set("experience_status", m.data), 10)
            n.create_subscription(String, "/voice/vc02/status", lambda m: self._set("voice_status", m.data), 10)
            n.create_subscription(String, "/voice/vc02/event", lambda m: self._set("voice_event", m.data), 10)
            n.create_subscription(String, "/voice/vc02/raw", lambda m: self._set("voice_raw", m.data), 10)
            n.create_subscription(Bool, "/voice/vc02/enabled", lambda m: self._set("voice_enabled", m.data), 10)
            n.create_subscription(String, "/atlas/voice/state", lambda m: self._set("companion_state", m.data), 10)
            n.create_subscription(String, "/atlas/voice/mode", lambda m: self._set("companion_mode", m.data), 10)
            n.create_subscription(String, "/atlas/voice/transcript", lambda m: self._set("companion_transcript", m.data), 10)
            n.create_subscription(String, "/atlas/voice/intent", lambda m: self._set("companion_intent", m.data), 10)
            n.create_subscription(String, "/atlas/voice/action", lambda m: self._set("companion_action", m.data), 10)
            n.create_subscription(String, "/atlas/voice/response", lambda m: self._set("companion_response", m.data), 10)
            n.create_subscription(String, "/atlas/voice/confirmation", lambda m: self._set("companion_confirmation", m.data), 10)
            n.create_subscription(String, "/atlas/voice/rgb", lambda m: self._set("companion_rgb", m.data), 10)
            n.create_subscription(String, "/atlas/voice/cloud", lambda m: self._set("companion_cloud", m.data), 10)
            n.create_subscription(Joy, "/joy", lambda m: self._set("joy", {
                "axes": len(m.axes), "buttons": len(m.buttons)
            }), 10)
            n.create_subscription(
                Int32,
                "/camera/bottom_servo_us",
                lambda m: setattr(self, "pan_us", int(m.data)),
                10,
            )
            n.create_subscription(
                Int32,
                "/camera/second_servo_us",
                lambda m: setattr(self, "tilt_us", int(m.data)),
                10,
            )
            n.create_timer(0.1, self._drive_watchdog)
            self.ready = True
            rclpy.spin(n)
        except Exception as exc:
            self._set("web_error", str(exc))
            self.ready = False
        finally:
            self.ready = False
            try:
                if self.node is not None:
                    self.node.destroy_node()
            except Exception:
                pass
            self.node = None

    def close(self):
        self.ready = False
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass
        if self.spin_thread.is_alive():
            self.spin_thread.join(timeout=3.0)

    def _odom_cb(self, msg):
        self._set("odom", {
            "x": msg.pose.pose.position.x,
            "y": msg.pose.pose.position.y,
            "vx": msg.twist.twist.linear.x,
            "wz": msg.twist.twist.angular.z,
        })

    def _ultrasonic_status_cb(self, msg):
        now = time.time()
        values = dict(re.findall(r"(front|left|right|rear)=(-?\d+)", msg.data))
        with self.lock:
            self.data["us_status"] = {"value": msg.data, "ts": now}
            if values:
                self.data["us_front"] = {"value": float(values.get("front", -1)), "ts": now}
                # Arduino LEFT/RIGHT fields are mirrored on the installed rover.
                self.data["us_left"] = {"value": float(values.get("right", -1)), "ts": now}
                self.data["us_right"] = {"value": float(values.get("left", -1)), "ts": now}
                self.data["us_rear"] = {"value": float(values.get("rear", -1)), "ts": now}

    def _radar_targets_cb(self, msg):
        targets = []
        for part in msg.data.split("|"):
            match = re.search(r"x=(-?\d+)mm,y=(-?\d+)mm,spd=(-?\d+)cm/s", part)
            if not match:
                continue
            x, y, speed = (float(v) for v in match.groups())
            if y > 0:
                targets.append((math.hypot(x, y), x, y, speed))
        if targets:
            distance, x, y, speed = min(targets, key=lambda item: item[0])
            zone = "DANGER" if distance < 500 else "CAUTION" if distance < 1000 else "CLEAR"
        else:
            distance, x, y, speed, zone = -1.0, 0.0, 0.0, 0.0, "NO_TARGET"
        now = time.time()
        with self.lock:
            for key, value in (
                ("radar", msg.data), ("radar_count", float(len(targets))),
                ("radar_dist", distance), ("radar_x", x), ("radar_y", y),
                ("radar_speed", speed), ("radar_zone", zone),
            ):
                self.data[key] = {"value": value, "ts": now}

    def _imu_cb(self, msg):
        self._set("imu_full", {
            "qx": msg.orientation.x,
            "qy": msg.orientation.y,
            "qz": msg.orientation.z,
            "qw": msg.orientation.w,
            "gx": msg.angular_velocity.x,
            "gy": msg.angular_velocity.y,
            "gz": msg.angular_velocity.z,
            "ax": msg.linear_acceleration.x,
            "ay": msg.linear_acceleration.y,
            "az": msg.linear_acceleration.z,
            "frame": msg.header.frame_id,
        })

    def _mag_cb(self, msg):
        self._set("imu_mag", {
            "x_ut": msg.magnetic_field.x * 1e6,
            "y_ut": msg.magnetic_field.y * 1e6,
            "z_ut": msg.magnetic_field.z * 1e6,
            "frame": msg.header.frame_id,
        })

    def _imu_dashboard_cb(self, msg):
        try:
            data = json.loads(msg.data)
        except Exception:
            return
        now = time.time()
        full = {k: data.get(k) for k in (
            "qx", "qy", "qz", "qw", "gx", "gy", "gz",
            "ax", "ay", "az", "mx_raw", "my_raw", "mz_raw", "frame",
            "source", "role", "navigation_fusion", "heading_reference_mode",
            "qualified_for_navigation"
        )}
        mag = {
            "x_ut": data.get("mx_ut"),
            "y_ut": data.get("my_ut"),
            "z_ut": data.get("mz_ut"),
            "frame": data.get("frame"),
        }
        with self.lock:
            for key, value in (
                ("imu_heading", data.get("heading")),
                ("imu_roll", data.get("roll")),
                ("imu_pitch", data.get("pitch")),
                ("imu_yaw", data.get("yaw")),
                ("imu_full", full),
                ("imu_mag", mag),
            ):
                self.data[key] = {"value": value, "ts": now}

    def _scan_cb(self, msg):
        now = time.time()
        if now - self.last_scan_summary < 0.50:
            return
        self.last_scan_summary = now
        finite = [r for r in msg.ranges if r == r and msg.range_min <= r <= msg.range_max and r != float("inf")]
        nearest = min(finite) if finite else 0.0
        self._set("lidar", {
            "points": len(finite),
            "total": len(msg.ranges),
            "nearest_m": nearest,
            "range_max": msg.range_max,
            "frame": msg.header.frame_id,
        })

    def _camera_cb(self, msg):
        now = time.time()
        if now - self.last_compressed_camera < 0.05:
            return
        self.last_compressed_camera = now
        frame_bytes = bytes(msg.data)
        motion_text = "motion waiting"
        if now - self.last_motion_check >= 0.90:
            self.last_motion_check = now
            try:
                jpg = np.frombuffer(frame_bytes, dtype=np.uint8)
                gray = cv2.imdecode(jpg, cv2.IMREAD_GRAYSCALE)
                if gray is not None:
                    small = cv2.resize(gray, (96, 72))
                    small = cv2.GaussianBlur(small, (5, 5), 0)
                    if self.prev_motion_gray is not None:
                        diff = cv2.absdiff(self.prev_motion_gray, small)
                        changed = float((diff > 22).mean() * 100.0)
                        motion_text = "MOTION" if changed >= 2.5 else "quiet"
                        self._set("motion_percent", round(changed, 1))
                        self._set("motion_state", motion_text)
                    self.prev_motion_gray = small
            except Exception as exc:
                self._set("motion_error", str(exc))
        # Object inference is owned by ai_annotator_node. Running another
        # TensorRT engine here duplicated GPU work and gave the dashboard a
        # different result from Foxglove's annotated stream.
        if self.ai_mode == "object":
            ai_status = self.data.get("ai_status", {}).get("value", "Object detection armed")
        elif self.ai_mode == "eco":
            ai_status = "YOLO ready, off in Eco Mode" if self.yolo_ready else "YOLO model missing"
        else:
            ai_status = f"{self.ai_mode.title()} mode staged; safe preview only"
        with self.lock:
            self.data["camera_frame"] = {"value": frame_bytes, "ts": time.time()}
            self.data["camera_info"] = {"value": {"bytes": len(frame_bytes), "source": "compressed", "motion": motion_text, "ai": ai_status}, "ts": time.time()}
            self.data["ai_status"] = {"value": ai_status, "ts": time.time()}

    def _ai_camera_cb(self, msg):
        self._set("ai_camera_frame", bytes(msg.data))

    def _ai_detections_cb(self, msg):
        try:
            payload = json.loads(msg.data)
            objects = []
            for detection in payload.get("detections", [])[:12]:
                objects.append({
                    "label": str(detection.get("label", "object")),
                    "conf": round(float(detection.get("confidence", 0.0)), 3),
                    "x1": int(detection.get("x1", 0)),
                    "y1": int(detection.get("y1", 0)),
                    "x2": int(detection.get("x2", 0)),
                    "y2": int(detection.get("y2", 0)),
                })
        except (ValueError, TypeError, AttributeError):
            return
        self._set("ai_objects", json.dumps(objects, separators=(",", ":")))
        self._set("ai_detector_live", True)
        if self.ai_mode == "object":
            if objects:
                text = ", ".join(f"{item['label']} {item['conf']:.2f}" for item in objects[:4])
                self._set("ai_status", "OBJECT " + text)
            else:
                self._set("ai_status", "OBJECT no object in frame")
    def _raw_camera_cb(self, msg):
        now = time.time()
        if now - self.last_compressed_camera < 2.0:
            return
        if now - self.last_raw_camera_encode < 0.33:
            return
        self.last_raw_camera_encode = now
        try:
            channels = 4 if msg.encoding in ("bgra8", "rgba8") else 3
            if msg.encoding in ("mono8", "8UC1"):
                arr = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width))
                frame = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            else:
                arr = np.frombuffer(msg.data, dtype=np.uint8).reshape((msg.height, msg.width, channels))
                if msg.encoding == "rgb8":
                    frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                elif msg.encoding == "rgba8":
                    frame = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                elif msg.encoding == "bgra8":
                    frame = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
                else:
                    frame = arr[:, :, :3]
            ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
            if not ok:
                return
            jpg = enc.tobytes()
            with self.lock:
                self.data["camera_frame"] = {"value": jpg, "ts": time.time()}
                self.data["camera_info"] = {"value": {"bytes": len(jpg), "source": "raw", "encoding": msg.encoding}, "ts": time.time()}
        except Exception as exc:
            self._set("camera_error", str(exc))

    def set_ai_mode(self, mode):
        mode = (mode or "eco").strip().lower()
        if mode not in AI_MODES:
            return False, "unknown AI mode"
        self.ai_mode = mode
        if self.ai_pub is not None:
            self.ai_pub.publish(Bool(data=mode != "eco"))
        self._set("ai_mode", mode)
        if mode == "object":
            msg = "TensorRT object detection enabled" if self.yolo_ready else "YOLO model missing"
        elif mode == "eco":
            self.ai_model = None
            self.ai_detections = []
            self._set("ai_objects", "[]")
            msg = "Eco mode: AI object detection off"
        else:
            msg = f"{mode.title()} mode staged; safe preview only"
        self._set("ai_status", msg)
        return True, msg

    def _drive_watchdog(self):
        if self.drive_active and time.monotonic() - self.last_drive_command > 0.35:
            self.publish(0.0, 0.0)
            self.drive_active = False
            self._set("web_drive", "WATCHDOG STOP")

    def camera_move(self, axis, direction):
        direction = max(-1, min(1, int(direction)))
        if axis == "pan" and self.pan_pub is not None:
            self.pan_us = max(700, min(2300, self.pan_us + direction * 40))
            self.pan_pub.publish(Int32(data=self.pan_us))
            self._send_sensor_hub_camera(0, self.pan_us)
            return True, f"pan {self.pan_us}us"
        if axis == "tilt" and self.tilt_pub is not None:
            # The web UI's screen-space direction is opposite the installed
            # B0283 servo pulse direction: a lower pulse points the camera
            # down, while a higher pulse points it up. Translate here so even
            # an already-open/cached dashboard controls the physical direction.
            direction = -direction
            self.tilt_us = max(700, min(2300, self.tilt_us + direction * 50))
            self.tilt_pub.publish(Int32(data=self.tilt_us))
            self._send_sensor_hub_camera(1, self.tilt_us)
            return True, f"tilt {self.tilt_us}us"
        if axis == "center" and self.pan_pub is not None and self.tilt_pub is not None:
            self.pan_us = 1300
            self.tilt_us = 2100
            self.pan_pub.publish(Int32(data=self.pan_us))
            self.tilt_pub.publish(Int32(data=self.tilt_us))
            self._send_sensor_hub_camera(0, self.pan_us)
            self._send_sensor_hub_camera(1, self.tilt_us)
            return True, "camera centred"
        return False, "camera publisher unavailable"

    @staticmethod
    def _send_sensor_hub_camera(channel, pulse_us):
        """Local fallback; the UNO R4 bridge remains the sole serial owner."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                sock.sendto(
                    f"SERVO,{int(channel)},{int(pulse_us)}".encode(),
                    SENSOR_HUB_CAMERA_SOCKET,
                )
            finally:
                sock.close()
            return True
        except OSError:
            return False

    def _load_ai_model(self):
        if self.ai_model is not None:
            return True
        try:
            from trt_yolo_detector import TensorRTYOLO
            self.ai_model = TensorRTYOLO(
                "/home/jetson/project_atlas/scripts/yolov8n_fp16.engine",
                confidence=0.35,
            )
            return True
        except Exception as exc:
            self._set("ai_status", f"YOLO load error: {exc}")
            return False

    def _run_object_ai(self, frame_bytes):
        now = time.time()
        if self.ai_mode != "object" or now - self.last_ai_check < 3.0:
            return
        self.last_ai_check = now
        if not self.yolo_ready or not self._load_ai_model():
            return
        try:
            jpg = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame = cv2.imdecode(jpg, cv2.IMREAD_COLOR)
            if frame is None:
                return
            raw = self.ai_model.infer(frame)
            if not raw:
                raw = self.ai_model.infer(cv2.rotate(frame, cv2.ROTATE_180))
            dets = []
            for _x1, _y1, _x2, _y2, cls, conf in raw[:8]:
                dets.append({
                    "label": COCO_LABELS[cls] if cls < len(COCO_LABELS) else str(cls),
                    "conf": round(float(conf), 2),
                })
            self.ai_detections = dets
            if dets:
                txt = ", ".join(f"{d['label']} {d['conf']:.2f}" for d in dets[:4])
                self._set("ai_status", "OBJECT " + txt)
            else:
                self._set("ai_status", "OBJECT no object")
            self._set("ai_objects", json.dumps(dets, separators=(",", ":")))
        except Exception as exc:
            self._set("ai_status", f"OBJECT error: {exc}")

    def publish(self, linear=0.0, angular=0.0):
        if not self.ready or self.pub is None:
            return False
        msg = Twist()
        msg.linear.x = float(linear)
        msg.angular.z = float(angular)
        self.pub.publish(msg)
        if linear or angular:
            self.last_drive_command = time.monotonic()
            self.drive_active = True
            self._set("web_drive", f"{linear:.2f},{angular:.2f}")
        else:
            self.drive_active = False
            self._set("web_drive", "STOP")
        return True

    def snapshot(self):
        with self.lock:
            data = {key: dict(item) for key, item in self.data.items()}
        fallback = sensor_hub_cache_snapshot()
        for key, item in fallback["data"].items():
            direct = data.get(key)
            if direct is None or item["ts"] > direct["ts"]:
                data[key] = item
        out = {}
        now = time.time()
        for k, v in data.items():
            if k in {"camera_frame", "ai_camera_frame"}:
                continue
            out[k] = {"value": v["value"], "age": round(now - v["ts"], 1)}
        cache_updated = fallback.get("updated_at", 0.0)
        out["sensor_hub_cache"] = {
            "value": {
                "source": "UNO R4 local fallback",
                "items": len(fallback["data"]),
            },
            "age": round(now - cache_updated, 1) if cache_updated else None,
        }
        out["web_control_ready"] = {"value": self.ready, "age": 0}
        return out

    def camera_frame(self):
        with self.lock:
            item = self.data.get("ai_camera_frame") if self.ai_mode == "object" else None
            if not item or time.time() - item["ts"] > 1.5:
                item = self.data.get("camera_frame")
            return item["value"] if item else None

    def camera_panel_frame(self):
        """Return a small cached JPEG sized for the 1024x600 CrowPanel."""
        now = time.time()
        with self.lock:
            source = self.data.get("camera_frame")
            if not source:
                return None
            source_jpeg = source["value"]
            source_ts = source["ts"]
            if (self.panel_camera_frame is not None and
                    self.panel_camera_source_ts == source_ts and
                    now - source_ts < 2.0):
                return self.panel_camera_frame
        try:
            encoded = np.frombuffer(source_jpeg, dtype=np.uint8)
            frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if frame is None:
                return source_jpeg
            # Mapping mode publishes the camera at the CrowPanel's native
            # viewport. Reuse that JPEG directly instead of performing a
            # costly decode-resize-encode cycle for every panel request.
            if frame.shape[1] == 656 and frame.shape[0] == 368:
                with self.lock:
                    self.panel_camera_frame = source_jpeg
                    self.panel_camera_source_ts = source_ts
                return source_jpeg
            # Exact live-camera viewport used by the approved 1024x600
            # CrowPanel Drive screen. Both dimensions are JPEG-HW aligned.
            frame = cv2.resize(frame, (656, 368), interpolation=cv2.INTER_AREA)
            ok, panel_jpeg = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 68]
            )
            if not ok:
                return source_jpeg
            result = panel_jpeg.tobytes()
            with self.lock:
                self.panel_camera_frame = result
                self.panel_camera_source_ts = source_ts
            return result
        except Exception:
            return source_jpeg

    def camera_overview_frame(self):
        """Return a cached native-size JPEG for CrowPanel Overview."""
        now = time.time()
        with self.lock:
            source = self.data.get("camera_frame")
            if not source:
                return None
            source_jpeg = source["value"]
            source_ts = source["ts"]
            if (self.overview_camera_frame is not None and
                    self.overview_camera_source_ts == source_ts and
                    now - source_ts < 2.0):
                return self.overview_camera_frame
        try:
            encoded = np.frombuffer(source_jpeg, dtype=np.uint8)
            frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if frame is None:
                return None
            frame = cv2.resize(frame, (272, 160), interpolation=cv2.INTER_AREA)
            ok, overview_jpeg = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70]
            )
            if not ok:
                return None
            result = overview_jpeg.tobytes()
            with self.lock:
                self.overview_camera_frame = result
                self.overview_camera_source_ts = source_ts
            return result
        except Exception:
            return None


ROS = AtlasRosNode()


def network_status():
    info = {"wifi_ip": "--", "cell_ip": "--", "tailscale_ip": "--", "route": "--", "ssh": "--"}
    for line in run(["ip", "-4", "-br", "addr"]).splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        iface, state, ip = parts[0], parts[1], parts[2].split("/")[0]
        if iface in ("wlan0", "wlP1p1s0") and state == "UP":
            info["wifi_ip"] = ip
        elif iface == "wwan0" or iface.startswith("enx"):
            info["cell_ip"] = ip
        elif iface == "tailscale0":
            info["tailscale_ip"] = ip
    route = run(["ip", "route", "show", "default"])
    if " dev wwan0 " in route or " dev enx" in route:
        info["route"] = "cellular"
    elif " dev wlan0 " in route or " dev wlP1p1s0 " in route:
        info["route"] = "Wi-Fi"
    peers = []
    for line in run(["ss", "-tn", "state", "established"]).splitlines():
        if ":22 " not in line:
            continue
        parts = line.split()
        if len(parts) >= 4:
            peer = parts[-1].rsplit(":", 1)[0].strip("[]")
            if peer and peer not in peers:
                peers.append(peer)
    if peers:
        peer = peers[-1]
        info["ssh"] = ("Wi-Fi LAN: " if peer.startswith("192.168.1.") else "Tailscale/cellular: " if peer.startswith("100.") else "") + peer
    return info


def services():
    # Query every dashboard unit in one systemd round-trip.  The previous
    # implementation spawned one process per unit on every cache refresh.
    output = run(
        ["systemctl", "--user", "show", "--property=Id", "--property=ActiveState", *SERVICES],
        timeout=2,
    )
    states = {name: "unknown" for name in SERVICES}
    unit = ""
    for line in output.splitlines():
        if line.startswith("Id="):
            unit = line[3:].removesuffix(".service")
        elif line.startswith("ActiveState=") and unit in states:
            states[unit] = line.split("=", 1)[1] or "unknown"
    return states


_cpu_sample_lock = threading.Lock()
_cpu_sample = None


def cpu_percent():
    global _cpu_sample
    try:
        fields = [int(value) for value in open("/proc/stat", encoding="utf-8").readline().split()[1:]]
        total = sum(fields)
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        with _cpu_sample_lock:
            previous = _cpu_sample
            _cpu_sample = (total, idle)
        if previous:
            delta_total = total - previous[0]
            delta_idle = idle - previous[1]
            if delta_total > 0:
                return f"{100.0 * (delta_total - delta_idle) / delta_total:.1f}"
    except (OSError, ValueError, IndexError):
        pass
    return "--"


def voice_usb_status():
    preferred = (
        "/dev/serial/by-id/"
        "usb-Espressif_USB_JTAG_serial_debug_unit_28:84:85:57:02:24-if00"
    )
    candidates = [preferred, "/dev/atlas-voice"]
    candidates.extend(sorted(glob.glob("/dev/serial/by-id/*Espressif*USB*JTAG*")))
    candidates.extend(sorted(glob.glob("/dev/serial/by-id/*ESP32*")))
    for candidate in dict.fromkeys(candidates):
        if candidate and os.path.exists(candidate):
            return {
                "voice_usb": True,
                "voice_usb_path": candidate,
                "voice_usb_reason": "ESP32-S3 voice controller connected",
            }
    return {
        "voice_usb": False,
        "voice_usb_path": "NOT ENUMERATED",
        "voice_usb_reason": "Reconnect the ESP32-S3 USB data cable",
    }


def system_status():
    cpu = cpu_percent()
    ram = "--"
    ram_percent = None
    try:
        memory = {}
        for line in open("/proc/meminfo", encoding="utf-8"):
            key, value = line.split(":", 1)
            memory[key] = int(value.strip().split()[0])
        total_mb = memory["MemTotal"] // 1024
        available_mb = memory.get("MemAvailable", memory.get("MemFree", 0)) // 1024
        used_mb = total_mb - available_mb
        ram_percent = round(100.0 * used_mb / total_mb) if total_mb else None
        ram = f"{used_mb} MB / {total_mb} MB ({ram_percent}%)"
    except (OSError, ValueError, KeyError):
        pass
    try:
        temp = open("/sys/class/thermal/thermal_zone0/temp", encoding="utf-8").read().strip()
    except OSError:
        temp = ""
    if temp.isdigit():
        temp = f"{int(temp) / 1000:.0f} C"
    return {
        "cpu_percent": cpu,
        "ram": ram,
        "ram_percent": ram_percent,
        "temp": temp or "--",
        **voice_usb_status(),
        "openai_configured": os.path.exists("/home/jetson/.config/project-atlas/openai.env"),
    }


_slow_cache_lock = threading.Lock()
_slow_cache = {"ts": 0.0, "network": {}, "system": {}, "services": {}}


def snapshot():
    # Network discovery, top/free and systemctl previously ran independently
    # for every connected dashboard.  CrowPanel + browser + diagnostics could
    # therefore launch dozens of subprocesses per second.  Share a short cache
    # while keeping ROS sensor values fresh on every response.
    now = time.monotonic()
    with _slow_cache_lock:
        if now - _slow_cache["ts"] >= 2.0:
            _slow_cache["network"] = network_status()
            _slow_cache["system"] = system_status()
            _slow_cache["services"] = services()
            _slow_cache["ts"] = now
        network = dict(_slow_cache["network"])
        system = dict(_slow_cache["system"])
        service_state = dict(_slow_cache["services"])
    return {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "network": network,
        "system": system,
        "services": service_state,
        "ros": ROS.snapshot(),
        "todo": TODO,
    }


def radar_snapshot():
    keys = (
        "radar",
        "radar_count",
        "radar_dist",
        "radar_x",
        "radar_y",
        "radar_speed",
        "radar_zone",
        "radar_link",
        "radar_decoder_status",
    )
    now = time.time()
    with ROS.lock:
        return {
            key: {
                "value": ROS.data[key]["value"],
                "age": round(now - ROS.data[key]["ts"], 3),
            }
            for key in keys
            if key in ROS.data
        }


def stop_rover():
    ok = ROS.publish(0.0, 0.0)
    return "published" if ok else "publisher not ready"


def drive_pulse(linear, angular):
    linear = max(-0.75, min(0.75, float(linear)))
    angular = max(-1.6, min(1.6, float(angular)))
    if not ROS.ready:
        return "publisher not ready"
    ROS.publish(linear, angular)
    return f"published linear={linear:.2f} angular={angular:.2f}"


def clean_json(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    return value

def json_response(handler, status, payload):
    body = json.dumps(clean_json(payload), indent=2, allow_nan=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def client_allowed(self):
        try:
            address = ipaddress.ip_address(self.client_address[0])
            return (
                address.is_loopback
                or address.is_private
                or address in ipaddress.ip_network("100.64.0.0/10")
            )
        except ValueError:
            return False

    def do_GET(self):
        if not self.client_allowed():
            self.send_error(403)
            return
        if self.path.startswith("/api/radar"):
            json_response(self, 200, {"radar": radar_snapshot()})
            return
        if self.path.startswith("/api/status"):
            json_response(self, 200, snapshot())
            return
        if self.path.startswith("/logo.png"):
            path = "/home/jetson/project_atlas/scripts/atlas_rover_logo_preferred.png"
            try:
                with open(path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_error(404)
            return
        if self.path.startswith("/manifest.webmanifest"):
            body = MANIFEST_JSON.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/camera_panel.jpg"):
            frame = ROS.camera_panel_frame()
            if frame:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
            else:
                self.send_error(404)
            return
        if self.path.startswith("/camera_overview.jpg"):
            frame = ROS.camera_overview_frame()
            if frame:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
            else:
                self.send_error(404)
            return
        if self.path.startswith("/camera.jpg"):
            frame = ROS.camera_frame()
            if frame:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
            else:
                self.send_error(404)
            return
        if self.path.startswith("/camera.mjpg"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            for _ in range(600):
                try:
                    frame = ROS.camera_frame()
                    if frame:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                        self.wfile.flush()
                    # The camera publisher is 10 FPS.  Sending the same JPEG at
                    # 20 FPS wastes CPU and Wi-Fi bandwidth without reducing
                    # visual latency.
                    time.sleep(0.10)
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    break
            return
        body = render_control_page().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.client_allowed():
            self.send_error(403)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        form = parse_qs(self.rfile.read(length).decode())
        action = form.get("action", [""])[0]
        if action == "stop":
            json_response(self, 200, {"ok": True, "message": "Drive stopped", "detail": stop_rover()})
        elif action == "e_stop":
            json_response(self, 200, {"ok": True, "message": "EMERGENCY STOP ACTIVE", "detail": stop_rover()})
        elif action == "drive":
            out = drive_pulse(form.get("linear", ["0"])[0], form.get("angular", ["0"])[0])
            json_response(self, 200, {"ok": True, "message": "Short safe drive pulse sent", "detail": out})
        elif action == "ai_mode":
            ok, msg = ROS.set_ai_mode(form.get("mode", ["eco"])[0])
            json_response(self, 200 if ok else 400, {"ok": ok, "message": msg})
        elif action == "camera":
            ok, msg = ROS.camera_move(
                form.get("axis", [""])[0],
                form.get("direction", ["0"])[0],
            )
            json_response(self, 200 if ok else 503, {"ok": ok, "message": msg})
        elif action in {"start_mapping", "stop_mapping", "set_home", "return_home", "auto_explore", "cancel_goal"}:
            # Keep the HTTP thread non-blocking.  atlas_mission_control owns the
            # ROS/Nav2 work and its safety checks; the panel only publishes the
            # same requests used by Foxglove and the voice companion.
            topic = {
                "start_mapping": "/atlas/start_exploration",
                "auto_explore": "/atlas/start_exploration",
                "stop_mapping": "/atlas/stop_exploration",
                "cancel_goal": "/atlas/stop_exploration",
                "set_home": "/atlas/set_home",
                "return_home": "/atlas/return_home",
            }[action]
            command = (
                "source /opt/ros/humble/setup.bash; "
                "source /home/jetson/project_atlas_ws/install/setup.bash 2>/dev/null || true; "
                f"timeout 5 ros2 topic pub --once {topic} std_msgs/msg/Empty '{{}}'"
            )
            subprocess.Popen(
                ["bash", "-lc", command], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
            json_response(self, 202, {"ok": True, "message": f"{action} requested", "topic": topic})
        elif action in {"restart", "start", "stop_service"}:
            svc = form.get("service", [""])[0]
            if svc not in SERVICES:
                json_response(self, 400, {"ok": False, "message": "service not allowed"})
                return
            verb = {"restart": "restart", "start": "start", "stop_service": "stop"}[action]
            ok, detail = run_quiet(["systemctl", "--user", verb, svc], timeout=8)
            json_response(self, 200 if ok else 500, {"ok": ok, "message": f"{verb} {svc}", "detail": detail})
        elif action == "reboot":
            subprocess.Popen(["bash", "-lc", "sleep 1; echo password | sudo -S reboot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            json_response(self, 200, {"ok": True, "message": "Reboot requested"})
        elif action == "shutdown":
            subprocess.Popen(["bash", "-lc", "sleep 1; echo password | sudo -S shutdown -h now"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            json_response(self, 200, {"ok": True, "message": "Shutdown requested"})
        else:
            json_response(self, 400, {"ok": False, "message": "unknown action"})

    def log_message(self, fmt, *args):
        return


def render_page():
    return r"""<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>ATLAS Rover Web App</title>
<meta http-equiv="Cache-Control" content="no-store">
<meta name="theme-color" content="#07111f">
<link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/logo.png">
<style>
:root{--bg:#07111f;--panel:#111c2c;--panel2:#0d1824;--line:#1d334a;--muted:#8aa0b8;--blue:#1da1ff;--green:#24d446;--red:#ff4444;--orange:#ff982c}*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;height:100%;background:var(--bg);font-family:Arial,Helvetica,sans-serif;overflow:hidden;color:#fff}.app{display:grid;grid-template-rows:52px 1fr 30px;height:100vh;gap:6px;padding:6px 8px;background:var(--bg)}header{display:flex;align-items:center;gap:8px}.logo{width:38px;height:38px;object-fit:contain;flex-shrink:0}.title h1{font-size:14px;margin:0;color:#fff}.title p{font-size:10px;margin:0;color:var(--muted)}.topStats{margin-left:auto;display:flex;align-items:center;gap:6px;flex-shrink:0}.pill{padding:2px 8px;border:1px solid var(--line);background:#0f2134;border-radius:10px;font-size:11px;color:var(--muted)}.pill b{color:#fff}.pill b.alarm{color:var(--red)}.main{display:grid;grid-template-columns:230px 1fr 255px;gap:6px;min-height:0;overflow:hidden}.left-col,.right-col{overflow-y:auto;display:flex;flex-direction:column;gap:6px}.left-col::-webkit-scrollbar,.right-col::-webkit-scrollbar{width:3px}.left-col::-webkit-scrollbar-thumb,.right-col::-webkit-scrollbar-thumb{background:var(--line)}.center-col{display:flex;flex-direction:column;gap:6px;min-height:0;overflow:hidden}.panel{background:var(--panel);border-radius:6px;padding:8px 10px;flex-shrink:0}.panel h3{margin:0 0 7px;font-size:11px;color:var(--blue);letter-spacing:.6px;text-transform:uppercase;border-bottom:1px solid var(--line);padding-bottom:4px}.cameraBox{position:relative;background:#000;border:1px solid var(--line);border-radius:6px;flex:1;min-height:180px;overflow:hidden}.camera{width:100%;height:100%;object-fit:cover;display:block}.camOverlay{position:absolute;right:6px;bottom:6px;display:flex;gap:4px;flex-wrap:wrap;max-width:90%;justify-content:flex-end}.chip{padding:2px 6px;background:rgba(5,12,22,.82);border:1px solid rgba(255,255,255,.12);border-radius:3px;font-size:10px;color:var(--muted)}.driveGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-top:4px}.driveGrid button{padding:9px 2px;border:1px solid #31506e;background:#102942;color:#fff;border-radius:4px;font-size:11px;font-weight:bold;cursor:pointer;touch-action:none}.driveGrid button:active{background:#1a4a7c}.stop-center{background:#7a1c1c!important;border-color:#aa2a2a!important}.feature{display:grid;grid-template-columns:1fr 1fr;gap:5px}.feature button{padding:7px 4px;background:var(--panel2);border:1px solid var(--line);color:#fff;border-radius:4px;font-size:11px;cursor:pointer}.feature button.active{border-color:var(--green);color:var(--green);background:rgba(36,212,70,.08)}.cmdRow{display:flex;gap:4px}.cmdRow input{flex:1;background:var(--panel2);border:1px solid var(--line);color:#fff;padding:5px 7px;border-radius:4px;font-size:11px;outline:none}.cmdRow button{padding:5px 10px;background:#1a3a5c;border:1px solid var(--line);color:#fff;border-radius:4px;cursor:pointer;font-size:11px}.row{display:grid;grid-template-columns:90px 1fr;gap:4px;border-bottom:1px solid #1a2a3a;padding:4px 0;font-size:11px;color:var(--muted)}.row span:last-child{color:#cdd6e0;word-break:break-all;text-align:right}.cards{display:grid;grid-template-columns:1fr 1fr;gap:5px}.card{background:var(--panel2);border-radius:5px;padding:6px 8px}.card .lbl{font-size:10px;color:var(--muted);margin-bottom:1px}.card .val{font-size:14px;font-weight:bold;color:#fff;word-break:break-all}.card .sub{font-size:10px;color:var(--muted);margin-top:1px}.bar{height:3px;background:var(--line);border-radius:2px;margin-top:3px}.bar-fill{height:100%;background:var(--green);border-radius:2px;transition:width .4s}footer{display:flex;align-items:center;font-size:10px;color:var(--muted);padding:0 4px;overflow:hidden;white-space:nowrap}button{font-family:inherit}
</style>
</head>
<body>
<div class="app">
<header><img class="logo" src="/logo.png"><div class="title"><h1>PROJECT ATLAS</h1><p>RaspRover-style Web APP plus ATLAS sensors</p></div><div class="topStats"><div class="pill">IP <b id="ipTop">--</b></div><div class="pill">CPU <b id="cpuTop">--</b></div><div class="pill">5G <b id="cellTop">--</b></div><button style="padding:4px 14px;background:var(--red);color:#fff;border:none;border-radius:4px;font-weight:bold;cursor:pointer;font-size:13px" onclick="post({action:stop})">STOP</button></div></header>
<div class="main">
<div class="left-col">
<div class="panel"><h3>Chassis Control</h3><div class="driveGrid"><button data-lin="0" data-ang="1.0">LEFT</button><button data-lin="0.75" data-ang="0">FORWARD</button><button data-lin="0" data-ang="-1.0">RIGHT</button><button data-lin="-0.5" data-ang="1.0">BK-L</button><button class="stop-center" onclick="post({action:stop})">STOP</button><button data-lin="-0.5" data-ang="-1.0">BK-R</button><button style="visibility:hidden"></button><button data-lin="-0.75" data-ang="0">BACKWARD</button><button style="visibility:hidden"></button></div></div>
<div class="panel"><h3>Function Buttons</h3><div class="feature"><button data-ai="armed">ALON</button><button data-ai="eco">ALOFF</button><button onclick="var a=document.createElement(a);a.href=/camera.jpg?ts=+Date.now()+.jpg;document.body.appendChild(a);a.click();toast(Snapshot requested)">Snapshot</button><button onclick="document.getElementById(cmd).value=explore;runCmd()">Explore</button></div></div>
<div class="panel"><h3>Command Line</h3><div class="cmdRow"><input id="cmd" placeholder="type command..."><button onclick="runCmd()">Run</button></div><div id="aiTop" style="margin-top:6px;font-size:11px;color:var(--muted)">AI --</div><div id="aiList" style="font-size:10px;color:var(--muted);margin-top:3px;line-height:1.4"></div></div>
<div class="panel"><h3>Robot Feedback</h3><div id="statusCards" class="cards"></div></div>
</div>
<div class="center-col">
<div class="cameraBox"><img id="cam" class="camera" src="/camera.jpg"><div class="camOverlay"><span class="chip" id="camtxt">NO CAMERA</span></div></div>
<div class="panel" style="flex-shrink:0"><h3>Sensors</h3><div id="rangeCards" class="cards"></div><div class="card" style="padding:6px;text-align:center"><span style="font-size:10px;color:var(--muted)">RADAR SWEEP</span><canvas id="radarVis" width="200" height="130" style="display:block;width:100%;margin-top:4px;border-radius:4px"></canvas></div></div>
</div>
<div class="right-col">
<div class="panel"><h3>Power</h3><div id="powerCards" class="cards"></div></div>
<div class="panel"><h3>Network</h3><div id="netRows"></div></div>
<div class="panel"><h3>System</h3><div id="sysRows"></div><div class="card" style="padding:6px"><span style="font-size:10px;color:var(--muted)">CPU TEMP</span><canvas id="tempCanvas" width="220" height="50" style="display:block;width:100%;margin-top:3px;border-radius:3px"></canvas></div></div>
</div>
</div>
<footer id="footRoute">route --</footer>
</div>
<div style=\"display:none\"><span id=\"radarTxt\"></span><canvas id=\"radarCanvas\" width=\"200\" height=\"200\"></canvas></div><script>

var thermalHist=[];function val(r,k,d='--'){return r[k]&&r[k].value!==undefined?r[k].value:d}function num(v,d=0){v=Number(v);return Number.isFinite(v)?v.toFixed(d):'--'}function row(a,b){return `<div class="row"><span>${a}</span><span>${b}</span></div>`}function bar(v){var n=Math.max(0,Math.min(100,Number(v)||0));return `<div class="bar"><div class="fill" style="width:${n}%"></div></div>`}function card(a,b,c=''){return `<div class="card"><div class="label">${a}</div><div class="value">${b}</div><div class="sub">${c}</div></div>`}function toast(t){document.getElementById('footReady').textContent=t}
async function post(data){var res=await fetch('/',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(data)});var j=await res.json();toast(j.message||'done');return j}function act(action,service){var d={action};if(service)d.service=service;post(d)}
function parseRadar(raw){return (raw||'').toString().split('|').map((p,i)=>{var x=(p.match(/x=(-?\d+)mm/)||[])[1],y=(p.match(/y=(-?\d+)mm/)||[])[1],s=(p.match(/spd=(-?\d+)cm\/s/)||[])[1];if(x===undefined||y===undefined)return null;return {name:(p.split(':')[0]||`T${i+1}`).trim(),x:Number(x),y:Number(y),speed:Number(s||0),dist:Math.hypot(Number(x),Number(y))}}).filter(Boolean)}
function drawRadar(r){var c=document.getElementById('radarCanvas'),ctx=c.getContext('2d'),w=c.width,h=c.height,cx=w/2,cy=h/2,rad=Math.min(w,h)*.43,max=3000;ctx.clearRect(0,0,w,h);ctx.fillStyle='#050b12';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#1d5f80';ctx.lineWidth=1;for(var i=1;i<=3;i++){ctx.beginPath();ctx.arc(cx,cy,rad*i/3,0,Math.PI*2);ctx.stroke()}ctx.strokeStyle='#1da1ff';ctx.beginPath();ctx.moveTo(cx-rad,cy);ctx.lineTo(cx+rad,cy);ctx.moveTo(cx,cy-rad);ctx.lineTo(cx,cy+rad);ctx.stroke();ctx.fillStyle='#24d46b';ctx.beginPath();ctx.arc(cx,cy,5,0,Math.PI*2);ctx.fill();var targets=parseRadar(val(r,'radar',''));targets.slice(0,8).forEach(t=>{if(t.y<0)return;var x=cx+t.x*rad/max,y=cy-t.y*rad/max;if((x-cx)**2+(y-cy)**2>rad**2)return;ctx.fillStyle=t.dist<500?'#ff4655':t.dist<1000?'#ffd23f':'#24d46b';ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);ctx.fill();ctx.fillStyle='#fff';ctx.font='11px Arial';ctx.fillText(`${t.name} ${Math.round(t.dist)}mm`,x+9,y-7)});document.getElementById('radarTxt').textContent=targets.length?`${targets.length} target, nearest ${num(val(r,'radar_dist',0),0)}mm, ${val(r,'radar_zone','--')}`:'NO DETECTION'}
function heat(v,mn,mx){var t=Math.max(0,Math.min(1,(Number(v)-mn)/Math.max(.1,mx-mn)));var rr=t<.5?Math.round(20+t*120):Math.round(80+(t-.5)*350),gg=t<.5?Math.round(70+t*260):Math.round(200-(t-.5)*160),bb=t<.5?Math.round(180+t*90):Math.round(225-(t-.5)*420);return `rgb(${rr},${gg},${Math.max(0,bb)})`}var c2=document.getElementById('radarVis');if(c2){var ctx2=c2.getContext('2d'),w2=c2.width,h2=c2.height;ctx2.drawImage(document.getElementById('radarCanvas'),0,0,w2,h2);}function drawThermal(r){var d={};try{d=JSON.parse(val(r,'thermal_json','{}')||'{}')}catch(e){}var pix=Array.isArray(d.pixels_c)?d.pixels_c:(Array.isArray(d.pixels)?d.pixels:[]),live=d.ok&&pix.length==64,mn=Number(d.min_c||0),mx=Number(d.max_c||0),avg=Number(d.avg_c||0),box=document.getElementById('thermalMap');if(live){var now=Date.now();if(!thermalHist.length||now-thermalHist.at(-1).t>3500){thermalHist.push({t:now,min:mn,max:mx,avg});thermalHist=thermalHist.slice(-80)}}box.innerHTML='';var hot=live?pix.indexOf(Math.max(...pix)):-1;for(var i=0;i<64;i++){var e=document.createElement('div');e.className='heat';e.style.background=live?heat(pix[i],mn,mx):'#101a28';if(i==hot)e.style.outline='2px solid #fff';box.appendChild(e)}var c=document.getElementById('thermalChart'),ctx=c.getContext('2d'),w=c.width,h=c.height;ctx.clearRect(0,0,w,h);ctx.fillStyle='#050b12';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#24435d';ctx.strokeRect(.5,.5,w-1,h-1);if(thermalHist.length>1){var vals=thermalHist.flatMap(p=>[p.min,p.max]),lo=Math.min(...vals),hi=Math.max(...vals);if(hi<=lo)hi=lo+1;var pt=(i,v)=>[8+i*(w-16)/(thermalHist.length-1),h-10-(v-lo)*(h-24)/(hi-lo)];ctx.lineWidth=2;ctx.strokeStyle='#ff982c';ctx.beginPath();thermalHist.forEach((p,i)=>{var q=pt(i,p.max);i?ctx.lineTo(...q):ctx.moveTo(...q)});ctx.stroke();ctx.strokeStyle='#1da1ff';ctx.beginPath();thermalHist.forEach((p,i)=>{var q=pt(i,p.min);i?ctx.lineTo(...q):ctx.moveTo(...q)});ctx.stroke()}document.getElementById('thermalTxt').textContent=live?`MIN ${mn.toFixed(1)}C AVG ${avg.toFixed(1)}C MAX ${mx.toFixed(1)}C`:(val(r,'thermal_status','AMG waiting'))}
function refreshCamera(){var img=document.getElementById('cam');if(img)img.src='/camera.jpg?ts='+Date.now()}
function refresh(){fetch('/api/status',{cache:'no-store'}).then(x=>x.json()).then(d=>{var r=d.ros,n=d.network,s=d.system;document.getElementById('ipTop').textContent=n.wifi_ip;document.getElementById('cpuTop').textContent=s.cpu_percent+'%';document.getElementById('cellTop').textContent=val(r,'cell_signal','--')+'%';document.getElementById('footRoute').textContent=`route ${n.route} wifi ${n.wifi_ip} 5g ${n.cell_ip}`;var brain={};try{brain=JSON.parse(val(r,'atlas_health','{}')||'{}')}catch(e){}document.getElementById('stateTop').textContent=(brain.state||'--')+' / '+val(r,'atlas_readiness','--');var cam=val(r,'camera_info',{});document.getElementById('camtxt').textContent=cam.bytes?`camera ${cam.source||'live'} ${cam.bytes} bytes`:'NO CAMERA';document.getElementById('aiTop').textContent=val(r,'ai_status','AI --');var aiMode=val(r,'ai_mode','eco');document.querySelectorAll('button[data-ai]').forEach(b=>b.classList.toggle('active',b.dataset.ai==aiMode));var objs=[];try{objs=JSON.parse(val(r,'ai_objects','[]')||'[]')}catch(e){}document.getElementById('aiList').textContent=objs.length?objs.map(o=>`${o.label} ${o.conf}`).join(' | '):val(r,'ai_status','AI waiting');drawRadar(r);drawThermal(r);drawTempChart(s.temp||0);drawTempChart(s.temp||0);var lidar=val(r,'lidar',{}),od=val(r,'odom',{}),cmd=val(r,'cmd_vel',{});document.getElementById('rangeCards').innerHTML=card('LiDAR',num(lidar.nearest_m||0,2)+' m',`${lidar.points||0}/${lidar.total||0} pts`)+card('Ultrasonic',val(r,'us_front','--')+' mm',`L ${val(r,'us_left','--')} R ${val(r,'us_right','--')}`)+card('Radar',val(r,'radar_count','--'),`${num(val(r,'radar_dist',0),0)}mm ${val(r,'radar_zone','--')}`)+card('Compass',num(val(r,'imu_heading',0),0)+' deg',`R ${num(val(r,'imu_roll',0),1)} P ${num(val(r,'imu_pitch',0),1)}`);document.getElementById('statusCards').innerHTML=card('Odom',`${num(od.x,2)}, ${num(od.y,2)}`,`vx ${num(od.vx,2)} wz ${num(od.wz,2)}`)+card('Encoders',`${val(r,'enc_m1','--')} ${val(r,'enc_m2','--')}`,`${val(r,'enc_m3','--')} ${val(r,'enc_m4','--')}`)+card('Steering',`F ${num(val(r,'front_steer',0),0)} R ${num(val(r,'rear_steer',0),0)}`,val(r,'steer_mode','--'))+card('Motion',val(r,'motion_state','--'),val(r,'motion_percent','--')+'%');document.getElementById('powerCards').innerHTML=card('Main BMS',val(r,'bms_percent','--')+'%',`${num(val(r,'bms_voltage',0),3)}V ${num(val(r,'bms_current',0),2)}A`+bar(val(r,'bms_percent',0)))+card('Motor Board',num(val(r,'bat_voltage',0),3)+'V',num(val(r,'bat_current',0),2)+'A')+card('Pi UPS',val(r,'ups_bat_percent','--')+'%',`${num(val(r,'ups_bat_voltage',0),3)}V ${num(val(r,'ups_bat_current',0),2)}A`+bar(val(r,'ups_bat_percent',0)))+card('5G Hat',num(val(r,'hat_power',0),2)+'W',`${num(val(r,'hat_voltage',0),3)}V ${num(val(r,'hat_current',0),2)}A`);document.getElementById('netRows').innerHTML=row('WiFi/AP',n.wifi_ip)+row('5G',`${n.cell_ip} ${val(r,'cell_tech','--')} ${val(r,'cell_operator','')}`)+row('Tailscale',n.tailscale_ip)+row('SSH',n.ssh);document.getElementById('sysRows').innerHTML=row('CPU',s.cpu_percent+'%')+row('RAM',s.ram)+row('Temp',s.temp)+row('Voice',val(r,'voice_status','--'))+row('UPS',val(r,'ups_status','--'));}).catch(e=>toast('web data error '+e))}
var holdTimer=null;function drive(l,a){post({action:'drive',linear:l,angular:a})}function startHold(b){drive(b.dataset.lin,b.dataset.ang);holdTimer=setInterval(()=>drive(b.dataset.lin,b.dataset.ang),100)}function stopHold(){if(holdTimer){clearInterval(holdTimer);holdTimer=null}act('stop')}document.querySelectorAll('button[data-lin]').forEach(b=>{b.addEventListener('mousedown',()=>startHold(b));b.addEventListener('touchstart',e=>{e.preventDefault();startHold(b)},{passive:false});['mouseup','mouseleave','touchend','touchcancel'].forEach(ev=>b.addEventListener(ev,stopHold))});document.querySelectorAll('button[data-ai]').forEach(b=>b.onclick=()=>post({action:'ai_mode',mode:b.dataset.ai}));function snapshot(){var a=document.createElement('a');a.href='/camera.jpg?ts='+Date.now();a.download='atlas_snapshot_'+Date.now()+'.jpg';document.body.appendChild(a);a.click();a.remove();toast('Snapshot requested')}function runCmd(){var c=document.getElementById('cmd').value.trim().toLowerCase();if(!c)return;if(c=='stop')act('stop');else if(['object','face','gesture','color','line','follow','eco'].includes(c))post({action:'ai_mode',mode:c});else if(c=='forward')drive(.5,0);else if(c=='back')drive(-.4,0);else if(c=='left')drive(0,1.0);else if(c=='right')drive(0,-1.0);else toast('unknown command')}
refreshCamera();setInterval(refreshCamera,900);refresh();setInterval(refresh,3000);

var tempHist=[];function drawTempChart(temp){var c=document.getElementById('tempCanvas');if(!c)return;tempHist.push(Number(temp)||0);if(tempHist.length>60)tempHist.shift();var ctx=c.getContext('2d'),w=c.width,h=c.height;ctx.fillStyle='#050b12';ctx.fillRect(0,0,w,h);if(tempHist.length<2)return;var mn=Math.min.apply(null,tempHist)-1,mx=Math.max.apply(null,tempHist)+1;if(mx-mn<2){mn=mn-1;mx=mx+1;}ctx.strokeStyle='#f77';ctx.lineWidth=2;ctx.beginPath();for(var i=0;i<tempHist.length;i++){var x=i/(tempHist.length-1)*(w-2)+1;var y=h-2-(tempHist[i]-mn)/(mx-mn)*(h-4);i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);}ctx.stroke();ctx.fillStyle='#f77';ctx.font='11px monospace';ctx.fillText(temp.toFixed(1)+String.fromCharCode(176)+'C',3,12);}</script>
<div style="display:none"><span id="footReady"></span><span id="radarTxt"></span></div><span id="stateTop" style="display:none"></span><span id="thermalTxt" style="display:none"></span><canvas id="thermalChart" style="display:none"></canvas><div id="thermalMap" style="display:none"></div></body></html>"""


def render_control_page():
    return r"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<meta name="theme-color" content="#06101d"><link rel="manifest" href="/manifest.webmanifest">
<title>ATLAS Command Center</title>
<style>
:root{--bg:#040a12;--panel:#0b1724;--line:#1c405d;--cyan:#17d5ff;--green:#34e58b;--red:#ff4655;--muted:#8ca6bb}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}body{margin:0;overflow-x:hidden;background:radial-gradient(circle at 50% -20%,#12354e 0,#07131f 38%,var(--bg) 75%);color:#eef7ff;font:14px system-ui,Arial}
header{height:58px;display:flex;align-items:center;gap:10px;padding:7px 12px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#071421;z-index:3}
header img{width:42px;height:42px;object-fit:contain}h1{font-size:16px;margin:0;color:var(--cyan)}.sub{font-size:11px;color:var(--muted)}
.live{margin-left:auto;color:var(--green);font-weight:700}.headerBtn{display:flex;align-items:center;gap:6px;padding:8px 11px;border:1px solid #24d98a;border-radius:18px;background:#0b3a2a;color:#eafff6;text-decoration:none;font-size:11px;font-weight:900;white-space:nowrap;box-shadow:0 0 14px rgba(36,217,138,.18)}.headerBtn.cloud{border-color:var(--cyan);background:#0a3047;color:#e9faff;box-shadow:0 0 14px rgba(23,213,255,.18)}.headerBtn:active{background:#126344;transform:scale(.98)}.headerBtn.cloud:active{background:#15527b}.headerIcon{font-size:17px;line-height:1}.grid{display:grid;grid-template-columns:minmax(270px,21vw) minmax(430px,1fr) minmax(310px,24vw);gap:8px;padding:8px;height:calc(100vh - 58px)}
.col{min-height:0;overflow:auto;display:flex;flex-direction:column;gap:8px}.panel{background:linear-gradient(145deg,rgba(15,34,51,.96),rgba(7,19,31,.96));border:1px solid #183b55;border-radius:10px;padding:10px;box-shadow:0 8px 24px rgba(0,0,0,.22)}
h2{font-size:11px;letter-spacing:.8px;color:var(--cyan);margin:0 0 7px}.camera{width:100%;height:min(56vh,560px);object-fit:contain;background:#000;border-radius:7px}
.drive,.camctl{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.btn{border:1px solid #315a78;background:#102b42;color:#fff;border-radius:7px;padding:13px 5px;font-weight:700;touch-action:none;user-select:none}
.btn:active,.btn.on{background:#15527b;border-color:var(--cyan);box-shadow:0 0 14px rgba(23,213,255,.25)}.stop{background:#8b1521;border-color:#ff5966;font-size:16px}.ai-off{background:#54420d}.ai-on{background:#0c6542}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:6px}.card{background:#081522;border-radius:7px;padding:8px}.card.touch{border:1px solid #214761;cursor:pointer;touch-action:manipulation}.card.touch:active{border-color:var(--cyan);background:#0d2b40}.label{font-size:10px;color:var(--muted)}.value{font-size:16px;font-weight:750;margin-top:2px}.detail{font-size:10px;color:#aac0d1;margin-top:2px;word-break:break-word}
.row{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-bottom:1px solid #173047;min-width:0}.row span:first-child{color:var(--muted)}.row span:last-child{text-align:right;overflow-wrap:anywhere;min-width:0}
.envgrid{display:grid;grid-template-columns:130px 1fr;gap:8px}.heatmap{display:grid;grid-template-columns:repeat(8,1fr);gap:2px;aspect-ratio:1}.heat{border-radius:2px;background:#112436}.chart{width:100%;height:82px;background:#06101a;border:1px solid #18364d;border-radius:6px}
.radarScope{width:100%;height:min(36vh,340px);background:#020b09;border:1px solid #146044;border-radius:8px;box-shadow:inset 0 0 28px rgba(24,255,143,.08)}
.radarViewBar{display:flex;align-items:center;gap:6px;margin-bottom:7px}.radarViewBar .btn{padding:7px 11px;font-size:10px}.radarViewBar .btn.active{background:#15527b;border-color:var(--cyan);box-shadow:0 0 14px rgba(23,213,255,.22)}.radarViewNote{margin-left:auto;color:var(--muted);font-size:9px;text-align:right}.radarHidden{display:none}
.healthhead{display:flex;align-items:center;justify-content:space-between;gap:8px}.healthsummary{font-size:11px;font-weight:800}
.healthgrid{display:grid;grid-template-columns:1fr 1fr;gap:6px}.healthitem{border:1px solid #24435d;border-left:5px solid #8ca6bb;border-radius:7px;background:#07131f;padding:7px;min-width:0}
.healthitem.ok{border-left-color:#34e58b}.healthitem.warn{border-left-color:#ffcc3d}.healthitem.fail{border-left-color:#ff4655;background:#211017}
.healthname{font-size:11px;font-weight:800;display:flex;justify-content:space-between;gap:4px}.healthstate{font-size:9px}.healthhint{font-size:9px;color:#aac0d1;margin-top:3px;line-height:1.25}
.constellation-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:7px}.constellation{padding:6px;border-radius:6px;background:#07131f;border:1px solid #1d3c54}
.constellation-top{display:flex;justify-content:space-between;font-size:10px;font-weight:800}.satbar{height:7px;margin-top:5px;background:#1a2a39;border-radius:5px;overflow:hidden}.satfill{height:100%;border-radius:5px}.constellation-note{font-size:9px;color:#8ca6bb;margin-top:6px}
.companion{border-color:#216f8d;background:linear-gradient(145deg,rgba(10,43,60,.97),rgba(6,19,31,.98));box-shadow:0 0 22px rgba(23,213,255,.08)}
.companionHead{display:flex;align-items:center;justify-content:space-between;gap:8px}.companionState{font-size:10px;font-weight:900;padding:4px 8px;border:1px solid var(--cyan);border-radius:12px;color:var(--cyan)}
.companionGrid{display:grid;grid-template-columns:1.25fr .75fr;gap:7px}.speech{background:#06131f;border:1px solid #1d4863;border-radius:8px;padding:8px;min-height:62px}.speech.you{border-left:4px solid #18c7ff}.speech.atlas{border-left:4px solid #34e58b}.speechText{font-size:14px;line-height:1.3;margin-top:3px;overflow-wrap:anywhere}
.thoughts{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:7px}.thought{background:#071522;border-radius:6px;padding:6px;min-width:0}.thought strong{display:block;font-size:9px;color:var(--muted);margin-bottom:2px}.thought span{font-size:11px;overflow-wrap:anywhere}
.companionStatus{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-top:7px}.pill{text-align:center;background:#071522;border:1px solid #24435d;border-radius:6px;padding:5px 3px;font-size:9px}.rgbDot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;background:#198dff;box-shadow:0 0 8px currentColor}
.voiceLedGuide{margin-top:7px;padding:7px;background:#06131f;border:1px solid #214761;border-radius:7px}.voiceLedTitle{display:flex;justify-content:space-between;gap:8px;font-size:9px;font-weight:900;color:#bcd3e5}.voiceLedNow{color:#ffcc3d;text-align:right;overflow-wrap:anywhere}.voiceLedStates{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin-top:6px}.voiceLedState{font-size:8px;color:#9fb8ca;line-height:1.2;white-space:nowrap}.voiceLedState b{display:block;color:#eef7ff;font-size:8px}.voiceSwatch{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:3px;box-shadow:0 0 6px currentColor}.voiceUsbReason{margin-top:6px;color:#aac0d1;font-size:9px;line-height:1.25;overflow-wrap:anywhere}
section.col:nth-of-type(3) .panel:has(#heatmap){order:-3;border-color:#34e58b}
section.col:nth-of-type(3) .panel:has(#healthGrid){order:-2}
section.col:nth-of-type(3) .panel:has(#power){order:-1}
#toast{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);background:#122b40;border:1px solid var(--cyan);padding:8px 14px;border-radius:20px;display:none;z-index:8}
.sensorModal{display:none;position:fixed;inset:0;z-index:20;background:rgba(0,5,10,.88);padding:3vh 3vw}.sensorModal.open{display:flex}.sensorSheet{width:min(980px,94vw);max-height:94vh;margin:auto;overflow:auto;background:#07131f;border:2px solid var(--cyan);border-radius:14px;padding:14px;box-shadow:0 0 38px rgba(23,213,255,.28)}.sensorHead{display:flex;align-items:center;gap:10px;border-bottom:1px solid #214761;padding-bottom:9px;margin-bottom:10px}.sensorHead h2{font-size:18px;margin:0}.closeDetail{margin-left:auto;background:#7f1722;border:1px solid #ff5966;color:#fff;border-radius:8px;padding:10px 18px;font-weight:800}.detailGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.detailTile{background:#0b1d2c;border:1px solid #214761;border-radius:9px;padding:10px}.detailTile b{display:block;color:var(--cyan);font-size:11px}.detailTile strong{display:block;font-size:22px;margin-top:5px}.rangeBar{height:18px;background:#13283a;border-radius:9px;overflow:hidden;margin-top:8px}.rangeFill{height:100%;background:linear-gradient(90deg,#ff4655,#ffcc3d,#34e58b);transition:width .25s}.modalCamera{width:100%;max-height:65vh;object-fit:contain;background:#000;border-radius:8px}.modalHeat{display:grid;grid-template-columns:repeat(8,1fr);gap:3px;max-width:460px;aspect-ratio:1;margin:auto}.modalHeat i{display:block;border-radius:3px}.rawData{font:12px ui-monospace,monospace;white-space:pre-wrap;color:#bcd3e5;background:#040a12;border-radius:8px;padding:10px;margin-top:9px}.sensorHint{color:#8ca6bb;font-size:11px;margin-top:8px}
@media(max-width:700px){.detailGrid{grid-template-columns:1fr}.sensorModal{padding:1vh 2vw}.sensorSheet{max-height:98vh}}
@media(max-width:900px){.grid{display:block;height:auto;width:100%;overflow:hidden}.col,.panel{overflow:visible;margin-bottom:8px;min-width:0}.camera{height:42vh}.envgrid{grid-template-columns:1fr}.heatmap{max-width:180px}canvas{max-width:100%}header .sub{display:none}.headerBtn{padding:7px 9px}.headerText{display:none}}
@media(min-width:1500px){body{font-size:15px}.grid{grid-template-columns:minmax(300px,20vw) minmax(600px,1fr) minmax(350px,23vw)}.camera{height:min(52vh,610px)}.speechText{font-size:16px}}
@media(max-width:1150px) and (min-width:901px){.grid{grid-template-columns:265px minmax(390px,1fr) 295px}.companionGrid{grid-template-columns:1fr}.companionStatus{grid-template-columns:1fr 1fr}.voiceLedStates{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<header><img src="/logo.png"><div><h1>PROJECT ATLAS COMMAND CENTER</h1><div class="sub">Headless rover control • hold-to-drive • automatic stop watchdog</div></div><div class="live" id="online">CONNECTING</div><a class="headerBtn cloud" href="https://project-atlas-jetson.tail12f5ff.ts.net:8443/" title="Open the read-only ATLAS Visual Cloud live ROS observability dashboard."><span class="headerIcon">◈</span><span class="headerText">VISUAL CLOUD</span></a><a class="headerBtn" href="https://project-atlas-jetson.tail12f5ff.ts.net/" title="Open two-way ATLAS intercom. The camera stream closes to preserve call quality and AI Voice pauses during the call."><span class="headerIcon">☎</span><span class="headerText">TALK / LISTEN</span></a></header>
<main class="grid">
<section class="col">
 <div class="panel"><h2>ROVER DRIVE — HOLD BUTTON</h2><div class="drive">
  <button class="btn" data-l=".45" data-a=".90">↖ FWD-L</button><button class="btn" data-l=".65" data-a="0">▲ FORWARD</button><button class="btn" data-l=".45" data-a="-.90">FWD-R ↗</button>
  <button class="btn" data-l="-.65" data-a=".90">BACK-L</button><button class="btn stop" id="stop">E-STOP</button><button class="btn" data-l="-.65" data-a="-.90">BACK-R</button>
  <span></span><button class="btn" data-l="-.65" data-a="0">▼ BACK</button><span></span>
 </div></div>
 <div class="panel"><h2>CAMERA PAN / TILT</h2><div class="camctl">
  <span></span><button class="btn" data-cam="tilt" data-dir="-1">▲ UP</button><span></span>
  <button class="btn" data-cam="pan" data-dir="-1">◀ LEFT</button><button class="btn" data-cam="center" data-dir="0">CENTER</button><button class="btn" data-cam="pan" data-dir="1">RIGHT ▶</button>
  <span></span><button class="btn" data-cam="tilt" data-dir="1">▼ DOWN</button><span></span>
 </div></div>
 <div class="panel"><h2>JETSON AI POWER</h2><div class="cards">
  <button class="btn ai-on" data-ai="object">AI ON</button><button class="btn ai-off" data-ai="eco">AI ECO / OFF</button>
 </div><div class="detail" id="ai">AI status waiting</div></div>
 <div class="panel"><h2>MOTION / ENCODERS</h2><div id="motion"></div></div>
</section>
<section class="col">
 <div class="panel"><h2>LIVE CAMERA — 720P LOW LATENCY <button class="btn" style="float:right;padding:5px 9px" onclick="openDetail('camera')">OPEN DATA</button></h2><img class="camera" id="camera" src="/camera.mjpg" onclick="openDetail('camera')"></div>
 <div class="panel companion"><div class="companionHead"><h2>ATLAS COMPANION / DEVELOPER</h2><div class="companionState" id="companionState">STANDBY</div></div>
  <div class="companionGrid">
   <div class="speech you"><div class="label">YOU SAID / HEARD</div><div class="speechText" id="companionHeard">Waiting for voice service</div></div>
   <div class="speech atlas"><div class="label">ATLAS SAYS</div><div class="speechText" id="companionReply">Voice bridge is being prepared</div></div>
  </div>
  <div class="thoughts">
   <div class="thought"><strong>UNDERSTOOD INTENT</strong><span id="companionIntent">None</span></div>
   <div class="thought"><strong>ACTION / TOOL SELECTED</strong><span id="companionAction">No action selected</span></div>
  </div>
  <div class="companionStatus">
   <div class="pill" id="companionMode">LOCAL SAFETY</div><div class="pill" id="companionConfirm">NO CONFIRMATION</div>
   <div class="pill" id="companionCloud">CLOUD OFFLINE</div><div class="pill"><span class="rgbDot" id="rgbDot"></span><span id="companionRgb">BLUE</span></div>
  </div>
  <div class="voiceLedGuide">
   <div class="voiceLedTitle"><span>VOICE LED MEANING</span><span class="voiceLedNow" id="companionLedNow">CHECKING</span></div>
   <div class="voiceLedStates">
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#198dff;background:#198dff"></i>BLUE</b>Ready / idle</div>
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#34e58b;background:#34e58b"></i>GREEN</b>Listening</div>
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#eef7ff;background:#eef7ff"></i>WHITE</b>Thinking</div>
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#17d5ff;background:#17d5ff"></i>BLUE PULSE</b>Speaking</div>
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#ff4655;background:#ff4655"></i>RED</b>Error / USB offline</div>
   </div>
   <div class="voiceUsbReason" id="voiceUsbReason">Checking ESP32-S3 voice USB connection</div>
  </div>
  <div class="detail" style="margin-top:8px;color:#34e58b">☎ Use TALK / LISTEN in the top bar for a secure two-way call. AI Voice pauses automatically during the call.</div>
 </div>
 <div class="panel"><h2>RANGE & ATTITUDE</h2><div class="cards" id="sensors"></div></div>
 <div class="panel"><h2>RD-03D LIVE MOTION RADAR</h2><div class="radarViewBar"><button class="btn" id="radar2dBtn" onclick="setRadarView('2d')">2D RADAR</button><button class="btn active" id="radar3dBtn" onclick="setRadarView('3d')">3D PEOPLE</button><span class="radarViewNote">LIVE RD-03D DATA<br>UP TO 3 TARGETS</span></div><canvas class="radarScope radarHidden" id="radarScope" width="720" height="340"></canvas><canvas class="radarScope" id="radarTwin" width="720" height="340"></canvas><div class="detail" id="radarCaption">WAITING FOR RADAR UART DATA</div></div>
</section>
<section class="col">
 <div class="panel"><div class="healthhead"><h2>HARDWARE HEALTH / FAULT FINDER</h2><div class="healthsummary" id="healthSummary">CHECKING</div></div><div class="healthgrid" id="healthGrid"></div></div>
 <div class="panel"><h2>POWER</h2><div class="cards" id="power"></div></div>
 <div class="panel"><h2>ENVIRONMENT — INSIDE / OUTSIDE</h2>
  <div class="envgrid"><div class="card touch" onclick="openDetail('thermal')"><div class="heatmap" id="heatmap"></div><div class="detail" id="thermalStats">Inside thermal waiting</div><div class="detail">TOUCH FOR 64-PIXEL DATA</div></div>
  <div class="card touch" onclick="openDetail('environment')"><div class="detail" id="outsideStats">Outside sensor waiting</div><canvas class="chart" id="insideChart" width="300" height="82"></canvas><canvas class="chart" id="outsideChart" width="300" height="82" style="margin-top:6px"></canvas><div class="detail">TOUCH FOR GAS / PRESSURE / IAQ</div></div></div>
 </div>
 <div class="panel"><h2>NETWORK</h2><div id="network"></div></div>
 <div class="panel"><h2>GNSS / CELLULAR</h2><div id="gnss"></div><div class="constellation-grid" id="constellationGrid"></div><div class="constellation-note">L76K supports GPS, GLONASS, BeiDou and QZSS. DETECTED means that constellation's NMEA stream is present; the accurate combined fix count is shown above. Galileo/NavIC remain visible for future receivers.</div></div>
 <div class="panel"><h2>SYSTEM</h2><div id="system"></div></div>
</section></main><div id="toast"></div>
<div class="sensorModal" id="sensorModal" role="dialog" aria-modal="true"><div class="sensorSheet"><div class="sensorHead"><h2 id="detailTitle">LIVE SENSOR</h2><span class="live" id="detailFresh">LIVE</span><button class="closeDetail" onclick="closeDetail()">CLOSE</button></div><div id="detailBody"></div></div></div>
<script>
const $=id=>document.getElementById(id), val=(r,k,d='--')=>r[k]&&r[k].value!==undefined?r[k].value:d;
const n=(v,d=1)=>Number.isFinite(Number(v))?Number(v).toFixed(d):'--';
const card=(a,b,c='',key='')=>`<div class="card ${key?'touch':''}" ${key?`onclick="openDetail('${key}')"`:''}><div class="label">${a}</div><div class="value">${b}</div><div class="detail">${c}${key?' • TOUCH FOR LIVE DATA':''}</div></div>`;
const row=(a,b)=>`<div class="row"><span>${a}</span><span>${b}</span></div>`;
const age=(r,k)=>r[k]&&Number.isFinite(Number(r[k].age))?Number(r[k].age):9999;
const recent=(r,k,seconds)=>age(r,k)<seconds;
function cellGeneration(raw){let t=String(raw||'').toLowerCase();if(t.includes('5g')||t.includes('nr'))return '5G';if(t.includes('lte'))return '4G';if(t.includes('umts')||t.includes('hspa'))return '3G';if(t.includes('gsm')||t.includes('edge')||t.includes('gprs'))return '2G';return 'CELLULAR'}
function healthItem(name,state,hint,seconds=null){
 let ageText=seconds===null?'':seconds<60?`${seconds.toFixed(1)}s`:`${Math.round(seconds/60)}m`;
 return `<div class="healthitem ${state}"><div class="healthname"><span>${name}</span><span class="healthstate">${state.toUpperCase()} ${ageText}</span></div><div class="healthhint">${hint}</div></div>`;
}
function renderHealth(r,net){
 let thermal={};try{thermal=JSON.parse(val(r,'thermal_json','{}')||'{}')}catch(e){}
 let carrier={};try{carrier=JSON.parse(val(r,'carrier_json','{}')||'{}')}catch(e){}
 let brain={};try{brain=JSON.parse(val(r,'atlas_health','{}')||'{}')}catch(e){}
 let ultrasonicEnabled=brain.ultrasonic_enabled!==false;
 let cellGen=cellGeneration(val(r,'cell_tech',''));
 let gpsStatusKey=recent(r,'gps_receiver_status',12)?'gps_receiver_status':'gps_arduino_status',gpsStatus=String(val(r,gpsStatusKey,'')),gpsUartLive=recent(r,gpsStatusKey,12),gpsLive=recent(r,'gps_sats',12),gpsSats=Number(val(r,'gps_sats',0))||0,gpsNoBytes=gpsUartLive&&gpsStatus.includes('NO_UART_BYTES'),gpsBadNmea=gpsUartLive&&gpsStatus.includes('NO_VALID_NMEA');
 let i2c=i2cInfo(r);
 let items=[
  ['CAMERA',recent(r,'camera_info',4)?'ok':'fail',recent(r,'camera_info',4)?'IMX708 video frames live':'No frames: check CSI ribbon and camera service','camera_info'],
  ['MOTOR / ENCODERS',recent(r,'enc_m1',4)?'ok':'fail',recent(r,'enc_m1',4)?'Yahboom serial telemetry live':'Check /dev/yahboom USB and motor-board power','enc_m1'],
  ['XBOX REMOTE',recent(r,'joy',8)?'ok':'warn',recent(r,'joy',8)?'Controller input received':'Wake controller, then press a stick or button','joy'],
  ['IMU / COMPASS',recent(r,'imu_heading',4)?'ok':'fail',recent(r,'imu_heading',4)?'Calibrated Yahboom motor-board IMU live':'Check Yahboom USB, motor-board power and base service','imu_heading'],
  ['RPLIDAR',recent(r,'lidar',4)?'ok':'fail',recent(r,'lidar',4)?'Laser scan live':'Check LiDAR USB, motor and cable','lidar'],
  ['RD-03D RADAR',recent(r,'radar',3)?'ok':'fail',recent(r,'radar',3)?'Valid 30-byte target frames live':(recent(r,'radar_link',3)?`UNO bytes received, but no valid target frame • ${val(r,'radar_decoder_status','decoder checking')}`:'No radar UART bytes: check power, GND, TX → D12 and RX → D11'),'radar'],
  ['ULTRASONIC',!ultrasonicEnabled?'warn':(recent(r,'us_status',4)||recent(r,'us_front',4)?'ok':'fail'),!ultrasonicEnabled?'Intentionally disabled; LiDAR is primary':(recent(r,'us_status',4)||recent(r,'us_front',4)?'Arduino range data live':'Check Arduino USB and sensor power'),ultrasonicEnabled?(recent(r,'us_status',4)?'us_status':'us_front'):null],
  ['I2C SENSOR BUS',i2c.liveCount?'ok':(i2c.bridgeLive?'warn':'fail'),i2c.liveCount?`${i2c.liveCount}/3 sensor${i2c.liveCount===1?'':'s'} live through ${i2c.route}`:(i2c.bridgeLive?'UNO R4 bridge live, but sensor data is stale':'No live I2C sensor telemetry'),i2c.freshestKey],
  ['INSIDE IR 8x8',thermal.ok&&recent(r,'thermal_json',5)?'ok':'fail',thermal.ok?'AMG8833 heatmap live':'Not detected: check 3.3V, GND, SDA pin 3, SCL pin 5','thermal_json'],
  ['OUTSIDE TEMP',recent(r,'outside_temperature',9)?'ok':'fail',recent(r,'outside_temperature',9)?'BME680 ambient temperature live':'Check BME680 wiring/address 0x77','outside_temperature'],
  ['DALY BMS',recent(r,'bms_status',20)?'ok':'fail',recent(r,'bms_status',20)?'Battery telemetry live':'Check BMS Bluetooth connection','bms_status'],
  ['ORIN IO BASE',recent(r,'carrier_status',25)&&carrier.ok?'ok':'fail',carrier.ok?`${carrier.power_mode} • NVMe ${carrier.nvme.free_gb}GB free • ${carrier.usb_devices} USB devices`:'Carrier health service offline','carrier_status'],
  [`${cellGen} MODEM`,recent(r,'cell_signal',20)?'ok':'fail',recent(r,'cell_signal',20)?`${n(val(r,'cell_signal'),0)}% ${val(r,'cell_tech','')}`:'Check SIM8230G USB and power','cell_signal'],
  ['GNSS',gpsSats>0?'ok':(gpsNoBytes||!gpsUartLive?'fail':'warn'),gpsSats>0?`${gpsSats} satellites used in fix`:(gpsNoBytes?'GPS UART has 0 bytes: check 5V, common GND and GPS TX → Jetson pin 10/RX':gpsBadNmea?'UART bytes present but no valid NMEA: check 9600 8N1 and signal level':gpsUartLive?'GPS receiver link live; waiting for satellite fix':'No GPS receiver heartbeat'),gpsStatusKey],
  ['WEB / TAILSCALE',net&&net.tailscale_ip!='--'?'ok':'warn',net&&net.tailscale_ip!='--'?`Reachable at ${net.tailscale_ip}`:'Tailscale address unavailable',null]
 ];
 let ok=items.filter(x=>x[1]=='ok').length,warn=items.filter(x=>x[1]=='warn').length,fail=items.filter(x=>x[1]=='fail').length;
 $('healthSummary').textContent=`${ok} OK / ${warn} WARN / ${fail} FAULT`;
 $('healthSummary').style.color=fail?'#ff4655':warn?'#ffcc3d':'#34e58b';
 $('healthGrid').innerHTML=items.map(x=>healthItem(x[0],x[1],x[2],x[3]?age(r,x[3]):null)).join('');
}
function renderConstellations(raw){
 let counts={GPS:0,GLONASS:0,BEIDOU:0,GALILEO:0,QZSS:0,NAVIC:0};
 let detected=new Set(),text=String(raw||'').trim();
 // Accept both publishers used on ATLAS.  The modem publisher sends numeric
 // totals (GPS:4|GLONASS:2), while the L76K NMEA driver sends NMEA talker IDs
 // (BD,GN,GP). A talker ID proves reception from that constellation but
 // does not contain a trustworthy per-system satellite count.
 if(text.includes(':'))text.split('|').forEach(part=>{let p=part.split(':'),name=String(p.shift()||'').trim().toUpperCase(),value=p.join(':');if(name in counts){counts[name]=Math.max(0,Number(value)||0);if(counts[name]>0)detected.add(name)}else if(name==='TALKERS'){let talkers={GP:'GPS',GL:'GLONASS',BD:'BEIDOU',GB:'BEIDOU',GA:'GALILEO',GQ:'QZSS',QZ:'QZSS',GI:'NAVIC',IR:'NAVIC'};value.split(',').map(x=>x.trim().toUpperCase()).forEach(code=>{if(talkers[code])detected.add(talkers[code])})}});
 else {
  let talkers={GP:'GPS',GL:'GLONASS',BD:'BEIDOU',GB:'BEIDOU',GA:'GALILEO',GQ:'QZSS',QZ:'QZSS',GI:'NAVIC',IR:'NAVIC'};
  text.split(',').map(x=>x.trim().toUpperCase()).forEach(code=>{if(talkers[code])detected.add(talkers[code])});
 }
 let systems=[
  ['GPS','USA','#34e58b'],['GLONASS','RUSSIA','#46b4ff'],
  ['BEIDOU','CHINA','#ff9d3d'],['GALILEO','EUROPE','#aa78ff'],
  ['QZSS','JAPAN','#ffd34d'],['NAVIC','INDIA','#ff5078']
 ];
 $('constellationGrid').innerHTML=systems.map(([name,country,color])=>{
   let count=counts[name],seen=detected.has(name),width=count?Math.min(100,count/12*100):(seen?22:0),label=count?`${count} SAT`:(seen?'DETECTED':'0 SAT');
   return `<div class="constellation"><div class="constellation-top"><span>${name} / ${country}</span><span style="color:${seen?color:'#71869a'}">${label}</span></div><div class="satbar"><div class="satfill" style="width:${width}%;background:${color}"></div></div></div>`;
 }).join('');
}
function toast(t){let e=$('toast');e.textContent=t;e.style.display='block';clearTimeout(window.tt);window.tt=setTimeout(()=>e.style.display='none',2200)}
async function post(data,loud=true){try{let q=await fetch('/',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(data)});let j=await q.json();if(loud)toast(j.message||'done');return j}catch(e){if(loud)toast('CONTROL LINK LOST')}}
let latestStatus=null,activeDetail='';
function tile(label,value,unit=''){return `<div class="detailTile"><b>${label}</b><strong>${value}${unit}</strong></div>`}
function rangeTile(label,value){let mm=Number(value),pct=Number.isFinite(mm)?Math.max(0,Math.min(100,mm/30)):0;return `<div class="detailTile"><b>${label}</b><strong>${Number.isFinite(mm)?mm.toFixed(0):'--'} mm</strong><div class="rangeBar"><div class="rangeFill" style="width:${pct}%"></div></div><div class="sensorHint">${Number.isFinite(mm)?(mm<250?'NEAR — STOP ZONE':mm<500?'CAUTION':'CLEAR'):'NO CURRENT READING'}</div></div>`}
function heatCells(r){let t={};try{t=JSON.parse(val(r,'thermal_json','{}')||'{}')}catch(e){}let p=Array.isArray(t.pixels_c)?t.pixels_c:(Array.isArray(t.pixels)?t.pixels:[]),mn=Number(t.min_c),mx=Number(t.max_c);return `<div class="modalHeat">${Array.from({length:64},(_,i)=>{let v=Number(p[i]),q=Number.isFinite(v)?Math.max(0,Math.min(1,(v-mn)/Math.max(.2,mx-mn))):0;return `<i title="${Number.isFinite(v)?v.toFixed(1)+'°C':'--'}" style="background:${Number.isFinite(v)?`hsl(${220-q*220} 88% ${28+q*28}%)`:'#112436'}"></i>`}).join('')}</div><div class="detailGrid" style="margin-top:10px">${tile('MIN',n(t.min_c,1),'°C')}${tile('AVERAGE',n(t.avg_c,1),'°C')}${tile('MAX / HOTSPOT',n(t.max_c,1),'°C')}</div>`}
function i2cInfo(r){
 let raw=String(val(r,'i2c_status','')),pcaRaw=String(val(r,'pca_status','')),cameraRaw=String(val(r,'camera_servo_status','')),arduinoBus=(raw.match(/(?:^|,)BUS=([^,]*)/i)||[])[1]||'UNO R4 A4/A5',arduinoAddresses=raw.match(/0x[0-9a-f]{2}/gi)||[];
 arduinoAddresses=[...new Set(arduinoAddresses.map(x=>x.toUpperCase()))];
  let thermalLive=recent(r,'thermal_json',5)||recent(r,'thermal_status',5);
 let outsideLive=recent(r,'outside_temperature',9)||recent(r,'bme680_json',9)||recent(r,'outside_status',9);
 let pcaLive=(recent(r,'pca_status',5)&&(/pca=1|ACK,PCA,1|PCA=1/i.test(pcaRaw)))||recent(r,'camera_servo_status',5);
 let bridgeLive=recent(r,'i2c_status',8)||thermalLive||outsideLive||pcaLive;
  let sensors=[
   {name:'PCA9685 CAMERA',address:'0x40',live:pcaLive,key:pcaLive?'pca_status':'i2c_status'},
   {name:'AMG8833 8x8',address:'0x69',live:thermalLive,key:thermalLive?'thermal_json':'i2c_status'},
   {name:'BME680 AIR',address:'0x77',live:outsideLive,key:outsideLive?'outside_temperature':'i2c_status'}
  ];
 let liveSensors=sensors.filter(x=>x.live),freshest=liveSensors.map(x=>x.key).sort((a,b)=>age(r,a)-age(r,b))[0]||'i2c_status';
  return {raw,pcaRaw,cameraRaw,arduinoBus,arduinoAddresses,arduinoLive:recent(r,'i2c_status',8),bridgeLive,route:'UNO R4 USB/I2C hub',thermalLive,outsideLive,pcaLive,sensors,liveSensors,liveCount:liveSensors.length,freshestKey:freshest};
}
function renderDetail(){if(!activeDetail||!latestStatus)return;let r=latestStatus.ros,body='',title='LIVE SENSOR',fresh='LIVE';
 if(activeDetail==='ultrasonic'){title='FOUR ULTRASONIC SENSORS';body=`<div class="detailGrid">${rangeTile('LEFT',val(r,'us_left'))}${rangeTile('FRONT',val(r,'us_front'))}${rangeTile('RIGHT',val(r,'us_right'))}${rangeTile('REAR',val(r,'us_rear'))}</div><div class="rawData">STATUS: ${val(r,'us_status','waiting')}\nREFRESH: live ROS values, approximately 5–10 updates/second\nROLE: secondary near-field safety layer; LiDAR remains the primary navigation sensor.</div>`;fresh=Math.max(age(r,'us_left'),age(r,'us_front'),age(r,'us_right'),age(r,'us_rear'))<3?'● LIVE':'STALE';}
 else if(activeDetail==='camera'){title='IMX708 CAMERA — LIVE OUTPUT';let c=val(r,'camera_info',{});body=`<img id="modalCamera" class="modalCamera" src="/camera.mjpg"><div class="detailGrid" style="margin-top:10px">${tile('SOURCE',c.source||'--')}${tile('JPEG FRAME',c.bytes||'--',' bytes')}${tile('AGE',n(age(r,'camera_info'),1),' s')}</div><div class="rawData">AI: ${val(r,'ai_status','--')}\nMOTION: ${val(r,'motion_state','--')} (${n(val(r,'motion_percent'),1)}%)\nCamera processing remains single-source; this window does not start another detector.</div>`;fresh=age(r,'camera_info')<3?'● LIVE':'STALE';}
 else if(activeDetail==='imu'){title='YAHBOOM MOTOR-BOARD IMU — PRIMARY';let f=val(r,'imu_full',{});body=`<div class="detailGrid">${tile('ROLL',n(val(r,'imu_roll'),2),'°')}${tile('PITCH',n(val(r,'imu_pitch'),2),'°')}${tile('RELATIVE YAW',n(val(r,'imu_yaw'),2),'°')}${tile('ACCEL X',n(f.ax,3),' m/s²')}${tile('ACCEL Y',n(f.ay,3),' m/s²')}${tile('ACCEL Z',n(f.az,3),' m/s²')}${tile('GYRO X',n(f.gx,3),' rad/s')}${tile('GYRO Y',n(f.gy,3),' rad/s')}${tile('GYRO Z',n(f.gz,3),' rad/s')}${tile('MAG X RAW',n(f.mx_raw,2))}${tile('MAG Y RAW',n(f.my_raw,2))}${tile('MAG Z RAW',n(f.mz_raw,2))}</div><div class="rawData">SOURCE: ${f.source||'yahboom_motor_controller'}\nROLE: PRIMARY SYSTEM IMU\nORIENTATION QUATERNION: x ${n(f.qx,5)}  y ${n(f.qy,5)}  z ${n(f.qz,5)}  w ${n(f.qw,5)}\nHEADING MODE: ${f.heading_reference_mode||'startup_relative'}\nNAVIGATION FUSION: ${f.navigation_fusion||'disabled pending dynamic yaw validation'}\n\nThe magnetic values are controller-native raw units; they are not mislabeled as µT.</div>`;fresh=age(r,'imu_full')<3?'● LIVE':'STALE';}
 else if(activeDetail==='thermal'){title='AMG8833 8×8 THERMAL ARRAY';let thermalLive=age(r,'thermal_json')<4;body=heatCells(r)+`<div class="rawData">${thermalLive?'STATUS: LIVE via UNO R4 I²C hub':val(r,'thermal_status','Thermal sensor waiting')}\nEach square is one live infrared temperature pixel. Brightest square is the current hotspot.</div>`;fresh=thermalLive?'● LIVE':'STALE';}
 else if(activeDetail==='environment'){title='BME680 OUTSIDE AIR / GAS';let j={};try{j=JSON.parse(val(r,'bme680_json','{}')||'{}')}catch(e){}body=`<div class="detailGrid">${tile('TEMPERATURE',n(val(r,'outside_temperature'),2),'°C')}${tile('HUMIDITY',n(val(r,'outside_humidity'),1),'% RH')}${tile('PRESSURE',n(val(r,'outside_pressure'),1),' hPa')}${tile('GAS RESISTANCE',n(Number(val(r,'outside_gas'))/1000,1),' kΩ')}${tile('IAQ ESTIMATE',n(j.iaq,0))}${tile('HEATER',j.heat_stable?'STABLE':'WARMING')}</div><div class="rawData">STATUS: ${val(r,'outside_status','waiting')}\nGas resistance is a relative VOC/air-quality signal, not a calibrated safety alarm. Compare its trend and IAQ estimate after the heater becomes stable.</div>`;fresh=age(r,'outside_gas')<8?'● LIVE':'STALE';}
 else if(activeDetail==='i2c'){title='ATLAS I²C ROUTES — LIVE INVENTORY';let q=i2cInfo(r),sensorText=q.sensors.map(x=>`${x.live?'LIVE   ':'OFFLINE'} ${x.name}  ${x.address}`).join('\n'),arduinoText=q.arduinoAddresses.length?q.arduinoAddresses.join(', '):'not present in latest status frame';body=`<div class="detailGrid">${tile('UNO R4 I2C HUB',q.liveCount+'/3 LIVE')}${tile('PCA9685',q.pcaLive?'0x40 LIVE':'OFFLINE')}${tile('AMG8833',q.thermalLive?'0x69 LIVE':'OFFLINE')}${tile('BME680',q.outsideLive?'0x77 LIVE':'OFFLINE')}${tile('USB BRIDGE',q.bridgeLive?'ONLINE':'OFFLINE')}</div><div class="rawData">LIVE SENSOR ROUTE: Jetson USB → UNO R4 → I²C A4/A5\n${sensorText}\n\nYAHBOOM IMU ROUTE: motor controller USB → rover-base-telemetry → /imu/*\n\nI²C STATUS:\n${q.raw||'waiting for /arduino/i2c/status'}\nPCA STATUS:\n${q.pcaRaw||q.cameraRaw||'waiting for PCA9685 feedback'}\nSCANNED ADDRESSES: ${arduinoText}\n\nEach LIVE/OFFLINE result is calculated from that sensor's own fresh ROS data. One failed sensor no longer hides the working sensors.</div>`;fresh=q.liveCount?`● ${q.liveCount}/3 LIVE`:(q.bridgeLive?'● BRIDGE ONLY':'STALE');}
 $('detailTitle').textContent=title;$('detailFresh').textContent=fresh;$('detailFresh').style.color=fresh.includes('LIVE')?'#34e58b':'#ff4655';$('detailBody').innerHTML=body;
}
function openDetail(key){activeDetail=key;$('sensorModal').classList.add('open');renderDetail()}
function closeDetail(){activeDetail='';$('sensorModal').classList.remove('open');$('detailBody').innerHTML=''}
$('sensorModal').addEventListener('click',e=>{if(e.target===$('sensorModal'))closeDetail()});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDetail()});
async function stop(){await post({action:'stop'},false)}
let hold=null;function beginDrive(b){stopDrive(false);b.classList.add('on');let send=()=>post({action:'drive',linear:b.dataset.l,angular:b.dataset.a},false);send();hold=setInterval(send,120)}
function stopDrive(send=true){if(hold){clearInterval(hold);hold=null}document.querySelectorAll('[data-l]').forEach(b=>b.classList.remove('on'));if(send)stop()}
document.querySelectorAll('[data-l]').forEach(b=>{b.onpointerdown=e=>{e.preventDefault();b.setPointerCapture(e.pointerId);beginDrive(b)};b.onpointerup=()=>stopDrive();b.onpointercancel=()=>stopDrive();b.onlostpointercapture=()=>stopDrive()});
$('stop').onclick=()=>post({action:'e_stop'});window.addEventListener('blur',()=>stopDrive());document.addEventListener('visibilitychange',()=>{if(document.hidden)stopDrive()});
document.querySelectorAll('[data-cam]').forEach(b=>{let timer;b.onpointerdown=e=>{e.preventDefault();let send=()=>post({action:'camera',axis:b.dataset.cam,direction:b.dataset.dir});send();timer=setInterval(send,160)};let end=()=>{clearInterval(timer)};b.onpointerup=end;b.onpointercancel=end;b.onpointerleave=end});
document.querySelectorAll('[data-ai]').forEach(b=>b.onclick=()=>post({action:'ai_mode',mode:b.dataset.ai}));
let insideHistory=[],outsideHistory=[];
const radarTrails={T1:[],T2:[],T3:[]};let radarSweep=0,lastRadarRaw='',radarView='3d',lastRadarTargets=[],lastRadarLive=false,lastRadarLink='';
function parseRadarTargets(raw){return String(raw||'').split('|').map(part=>{let m=part.trim().match(/^(T\d+):x=(-?\d+)mm,y=(-?\d+)mm,spd=(-?\d+)cm\/s$/);return m?{id:m[1],x:Number(m[2]),y:Number(m[3]),speed:Number(m[4])}:null}).filter(Boolean)}
function setRadarView(view){radarView=view==='3d'?'3d':'2d';$('radarScope').classList.toggle('radarHidden',radarView!=='2d');$('radarTwin').classList.toggle('radarHidden',radarView!=='3d');$('radar2dBtn').classList.toggle('active',radarView==='2d');$('radar3dBtn').classList.toggle('active',radarView==='3d');if(radarView==='3d')drawRadarTwins(lastRadarTargets,lastRadarLive)}
function radarColor(t){let d=Math.hypot(t.x,t.y);return d<750?'#ff4655':d<1500?'#ffcf3c':t.id==='T2'?'#19cfff':'#38ff9b'}
function drawPerson(g,x,y,scale,color,label,detail){let head=Math.max(5,8*scale),body=Math.max(17,28*scale),arm=Math.max(10,17*scale),leg=Math.max(12,21*scale);g.save();g.strokeStyle=color;g.fillStyle=color;g.lineWidth=Math.max(2,4*scale);g.shadowColor=color;g.shadowBlur=12;g.beginPath();g.arc(x,y-body-head-3,head,0,Math.PI*2);g.fill();g.beginPath();g.moveTo(x,y-body);g.lineTo(x,y);g.moveTo(x-arm,y-body*.68);g.lineTo(x,y-body*.82);g.lineTo(x+arm,y-body*.68);g.moveTo(x,y);g.lineTo(x-leg*.62,y+leg);g.moveTo(x,y);g.lineTo(x+leg*.62,y+leg);g.stroke();g.shadowBlur=0;g.fillStyle='#eefaff';g.font='bold 12px system-ui';g.textAlign='center';g.fillText(label,x,y+leg+18);g.font='10px system-ui';g.fillStyle='#a9c7d9';g.fillText(detail,x,y+leg+31);g.restore()}
function drawRadarTwins(targets,live){let c=$('radarTwin'),g=c.getContext('2d'),w=c.width,h=c.height,cx=w/2,horizon=66,floor=h-27;g.clearRect(0,0,w,h);let bg=g.createLinearGradient(0,0,0,h);bg.addColorStop(0,'#061628');bg.addColorStop(.42,'#07131d');bg.addColorStop(1,'#020806');g.fillStyle=bg;g.fillRect(0,0,w,h);g.strokeStyle='rgba(23,213,255,.22)';g.lineWidth=1;for(let i=-6;i<=6;i++){g.beginPath();g.moveTo(cx+i*22,horizon);g.lineTo(cx+i*70,floor);g.stroke()}for(let m=1;m<=8;m++){let q=m/8,y=horizon+(floor-horizon)*q*q;g.beginPath();g.moveTo(30+(1-q)*cx*.76,y);g.lineTo(w-30-(1-q)*cx*.76,y);g.stroke()}g.fillStyle='#17d5ff';g.font='bold 12px system-ui';g.textAlign='left';g.fillText('RD-03D DIGITAL TWIN ROOM',14,22);g.fillStyle='#8ca6bb';g.font='10px system-ui';g.fillText('AVATARS REPRESENT LIVE RADAR X/Y — NOT A BODY SCAN',14,38);let visible=targets.filter(t=>t.y>=0).slice(0,3).sort((a,b)=>b.y-a.y);visible.forEach(t=>{let depth=Math.max(0,Math.min(1,t.y/8000)),py=floor-(floor-horizon)*Math.pow(depth,.62),spread=54+(1-depth)*270,px=cx+Math.max(-1,Math.min(1,t.x/4000))*spread,scale=.55+(1-depth)*.62,d=Math.hypot(t.x,t.y);drawPerson(g,px,py,scale,radarColor(t),t.id,`${(d/1000).toFixed(2)}m  ${t.speed>0?'+':''}${t.speed}cm/s`)});g.fillStyle='#eefaff';g.font='bold 12px system-ui';g.textAlign='right';g.fillText(`${visible.length}/3 PEOPLE`,w-14,22);if(!live){g.fillStyle='rgba(2,8,12,.76)';g.fillRect(0,0,w,h);g.fillStyle='#ff5966';g.font='bold 18px system-ui';g.textAlign='center';g.fillText('RADAR OFFLINE — NO LIVE TARGET FRAMES',cx,h/2)}else if(!visible.length){g.fillStyle='#8ca6bb';g.font='bold 16px system-ui';g.textAlign='center';g.fillText('NO PERSON MOTION DETECTED',cx,h/2)}}
function drawRadar(raw,live){let c=$('radarScope'),g=c.getContext('2d'),w=c.width,h=c.height,cx=w/2,base=h-18,maxY=4000,maxX=2400,targets=parseRadarTargets(raw);g.fillStyle='#020b09';g.fillRect(0,0,w,h);g.lineWidth=1;for(let meters=1;meters<=4;meters++){let ry=meters*1000/maxY*(h-42);g.strokeStyle=meters===1?'rgba(255,187,45,.35)':'rgba(44,224,143,.20)';g.beginPath();g.ellipse(cx,base,meters*1000/maxX*(w*.46),ry,0,Math.PI,Math.PI*2);g.stroke();g.fillStyle='#6fae94';g.font='11px system-ui';g.fillText(`${meters}m`,cx+5,base-ry+12)}g.strokeStyle='rgba(44,224,143,.28)';g.beginPath();g.moveTo(cx,base);g.lineTo(cx,18);g.moveTo(20,base);g.lineTo(w-20,base);g.stroke();radarSweep=(radarSweep+0.09)%(Math.PI*2);let grad=g.createLinearGradient(cx,base,cx+Math.sin(radarSweep)*w,base-Math.cos(radarSweep)*h);grad.addColorStop(0,'rgba(43,255,149,.32)');grad.addColorStop(1,'rgba(43,255,149,0)');g.strokeStyle=grad;g.lineWidth=2;g.beginPath();g.moveTo(cx,base);g.lineTo(cx+Math.sin(radarSweep)*w,base-Math.cos(radarSweep)*h);g.stroke();if(live&&raw!==lastRadarRaw){targets.forEach(t=>{let trail=radarTrails[t.id]||(radarTrails[t.id]=[]),previous=trail.at(-1);if(!previous||previous.x!==t.x||previous.y!==t.y)trail.push({x:t.x,y:t.y,at:Date.now()});radarTrails[t.id]=trail.filter(p=>Date.now()-p.at<12000).slice(-60)});lastRadarRaw=raw}let colors={T1:'#38ff9b',T2:'#19cfff',T3:'#ffcf3c'};Object.entries(radarTrails).forEach(([id,trail])=>{if(trail.length<2)return;g.strokeStyle=colors[id]||'#fff';g.lineWidth=2;g.beginPath();trail.forEach((p,i)=>{let px=cx+p.x/maxX*(w*.46),py=base-p.y/maxY*(h-42);i?g.lineTo(px,py):g.moveTo(px,py)});g.stroke()});targets.forEach(t=>{let px=cx+t.x/maxX*(w*.46),py=base-t.y/maxY*(h-42),color=colors[t.id]||'#fff';g.fillStyle=color;g.shadowColor=color;g.shadowBlur=14;g.beginPath();g.arc(px,py,9,0,Math.PI*2);g.fill();g.shadowBlur=0;g.fillStyle='#eafff5';g.font='bold 12px system-ui';g.fillText(`${t.id} ${Math.hypot(t.x,t.y).toFixed(0)}mm`,px+13,py-4);g.font='11px system-ui';g.fillText(`${t.speed>0?'+':''}${t.speed}cm/s`,px+13,py+11)});if(!live){g.fillStyle='#ff5966';g.font='bold 18px system-ui';g.textAlign='center';g.fillText('RADAR OFFLINE — NO VALID TARGET FRAMES',cx,h/2);g.textAlign='left'}$('radarCaption').textContent=live?`${targets.length} MOVING TARGET${targets.length===1?'':'S'} • trails show last 12 seconds • forward range 4m`:'Check RD-03D power, common GND, radar TX → UNO D12 and radar RX → UNO D11'}
function drawRadarHubWaiting(status){
 for(const id of ['radarScope','radarTwin']){let c=$(id),g=c.getContext('2d');g.fillStyle='rgba(2,8,12,.88)';g.fillRect(0,c.height/2-38,c.width,76);g.fillStyle='#ffcf3c';g.font='bold 17px system-ui';g.textAlign='center';g.fillText('UNO R4 ONLINE — RADAR FRAMES INVALID',c.width/2,c.height/2-7);g.fillStyle='#9bb9ca';g.font='11px system-ui';g.fillText(status,c.width/2,c.height/2+16)}
 $('radarCaption').textContent=status+' • bytes arrive, but no AA FF 03 00 … 55 CC frame decodes • radar TX → UNO D12, radar RX → UNO D11';
}
async function pollRadar(){try{let d=await fetch('/api/radar',{cache:'no-store'}).then(x=>x.json()),r=d.radar||{},raw=val(r,'radar',''),live=!!r.radar&&r.radar.age<1,linkFresh=!!r.radar_link&&r.radar_link.age<2.5,decoder=String(val(r,'radar_decoder_status','decoder checking'));lastRadarLink=linkFresh?String(val(r,'radar_link','')):'';lastRadarTargets=parseRadarTargets(raw);lastRadarLive=live;drawRadar(raw,live);if(radarView==='3d')drawRadarTwins(lastRadarTargets,live);if(!live&&linkFresh)drawRadarHubWaiting(decoder)}catch(e){lastRadarTargets=[];lastRadarLive=false;lastRadarLink='';drawRadar('',false);if(radarView==='3d')drawRadarTwins([],false)}}setInterval(pollRadar,125);pollRadar();
function graph(id,history,color,label){let c=$(id),x=c.getContext('2d'),w=c.width,h=c.height;x.clearRect(0,0,w,h);x.fillStyle='#06101a';x.fillRect(0,0,w,h);x.strokeStyle='#18364d';for(let i=1;i<4;i++){x.beginPath();x.moveTo(0,i*h/4);x.lineTo(w,i*h/4);x.stroke()}if(!history.length)return;let lo=Math.min(...history),hi=Math.max(...history);if(hi-lo<2){lo-=1;hi+=1}x.strokeStyle=color;x.lineWidth=2;x.beginPath();history.forEach((v,i)=>{let px=8+i*(w-16)/Math.max(1,history.length-1),py=h-10-(v-lo)*(h-24)/(hi-lo);i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke();x.fillStyle=color;x.font='11px system-ui';x.fillText(`${label} ${history.at(-1).toFixed(1)}°C  MIN ${Math.min(...history).toFixed(1)}  MAX ${Math.max(...history).toFixed(1)}`,7,13)}
function environment(r){let t={};try{t=JSON.parse(val(r,'thermal_json','{}')||'{}')}catch(e){}let pix=Array.isArray(t.pixels_c)?t.pixels_c:(Array.isArray(t.pixels)?t.pixels:[]),mn=Number(t.min_c),mx=Number(t.max_c),avg=Number(t.avg_c),map=$('heatmap');map.innerHTML='';for(let i=0;i<64;i++){let d=document.createElement('div');d.className='heat';if(pix.length===64){let q=Math.max(0,Math.min(1,(Number(pix[i])-mn)/Math.max(.2,mx-mn)));d.style.background=`hsl(${220-q*220} 88% ${28+q*28}%)`}map.appendChild(d)}let outside=Number(val(r,'outside_temperature',NaN)),humidity=Number(val(r,'outside_humidity',NaN));if(Number.isFinite(avg)){insideHistory.push(avg);insideHistory=insideHistory.slice(-90)}if(Number.isFinite(outside)){outsideHistory.push(outside);outsideHistory=outsideHistory.slice(-90)}$('thermalStats').textContent=Number.isFinite(avg)?`INSIDE AVG ${avg.toFixed(1)}°C • MIN ${mn.toFixed(1)} • MAX ${mx.toFixed(1)}`:val(r,'thermal_status','Inside sensor waiting');$('outsideStats').textContent=Number.isFinite(outside)?`OUTSIDE ${outside.toFixed(1)}°C • HUMIDITY ${n(humidity,0)}%`:`OUTSIDE SENSOR ${val(r,'outside_status','WAITING')}`;graph('insideChart',insideHistory,'#ff8c42','INSIDE');graph('outsideChart',outsideHistory,'#17d5ff','OUTSIDE')}
function companion(r,s){
 let state=String(val(r,'companion_state','STANDBY')),rgb=String(val(r,'companion_rgb','BLUE')).toUpperCase();
 $('companionState').textContent=state;$('companionHeard').textContent=val(r,'companion_transcript','Waiting for voice service');
 $('companionReply').textContent=val(r,'companion_response','Voice bridge is being prepared');
 $('companionIntent').textContent=val(r,'companion_intent','None');$('companionAction').textContent=val(r,'companion_action','No action selected');
 $('companionMode').textContent=val(r,'companion_mode','LOCAL SAFETY');$('companionConfirm').textContent=val(r,'companion_confirmation','NOT REQUIRED');
 $('companionCloud').textContent=val(r,'companion_cloud',s.openai_configured?'KEY READY':'NOT CONNECTED');$('companionRgb').textContent=rgb;
 let colors={BLUE:'#198dff','BLUE PULSE':'#17d5ff',GREEN:'#34e58b',RED:'#ff4655',YELLOW:'#ffcc3d',PURPLE:'#b275ff',WHITE:'#eef7ff'},color=colors[rgb]||'#71869a';
 $('rgbDot').style.background=color;$('rgbDot').style.color=color;
 $('companionLedNow').textContent=`${rgb} NOW`;
 $('companionLedNow').style.color=color;
 if(!s.voice_usb){
  $('companionState').textContent='VOICE USB OFFLINE';$('companionState').style.color='#ff4655';$('companionState').style.borderColor='#ff4655';
  $('voiceUsbReason').textContent=`RED: ${s.voice_usb_reason||'Reconnect the ESP32-S3 USB data cable'} • ${s.voice_usb_path||'NOT ENUMERATED'}`;
  $('voiceUsbReason').style.color='#ff8b94';
 }else{
  $('companionState').style.color='#17d5ff';$('companionState').style.borderColor='#17d5ff';
  $('voiceUsbReason').textContent=`VOICE USB ONLINE • ${s.voice_usb_path||'ESP32-S3 connected'}`;
  $('voiceUsbReason').style.color='#34e58b';
 }
}
async function refresh(){try{let d=await fetch('/api/status',{cache:'no-store'}).then(x=>x.json()),r=d.ros,net=d.network,s=d.system;latestStatus=d;
 let cellGen=cellGeneration(val(r,'cell_tech',''));
 renderHealth(r,net);
 companion(r,s);
 $('online').textContent='● ONLINE';$('online').style.color='#34e58b';
 $('ai').textContent=val(r,'ai_status','AI waiting');
 $('motion').innerHTML=row('Web drive',val(r,'web_drive','STOP'))+row('Odometry',JSON.stringify(val(r,'odom',{})))+row('Encoders',`${val(r,'enc_m1')} / ${val(r,'enc_m2')} / ${val(r,'enc_m3')} / ${val(r,'enc_m4')}`);
 let li=val(r,'lidar',{}),radarLive=!!r.radar_count&&r.radar_count.age<2.0,radarHub=!!r.radar_link&&r.radar_link.age<3.0,i2c=i2cInfo(r);
 let radarTitle=radarLive?`${val(r,'radar_count')} targets`:(radarHub?'UART INVALID':'OFFLINE');
 let radarDetail=radarLive?`${n(val(r,'radar_dist'),0)} mm • ${val(r,'radar_zone')} • X ${n(val(r,'radar_x'),0)} Y ${n(val(r,'radar_y'),0)} • ${n(val(r,'radar_speed'),0)} cm/s`:(radarHub?String(val(r,'radar_decoder_status','Bytes received; no valid frame')):'Check power/GND • radar TX → UNO D12 • radar RX → UNO D11');
 let imuLive=recent(r,'imu_full',4)||recent(r,'imu_heading',4);
 $('sensors').innerHTML=card('LiDAR',`${n(li.nearest_m,2)} m`,`${li.points||0} points`)+card('Ultrasonic',`${val(r,'us_front')} mm`,`L ${val(r,'us_left')} • R ${val(r,'us_right')} • B ${val(r,'us_rear')}`,'ultrasonic')+card('RD-03D Radar',radarTitle,radarDetail)+card('Yahboom IMU',imuLive?`${n(val(r,'imu_yaw'),0)}° REL`:'OFFLINE',imuLive?`PRIMARY • roll ${n(val(r,'imu_roll'))} pitch ${n(val(r,'imu_pitch'))}`:'Check Yahboom USB, motor-board power and base service','imu')+card('I²C Sensor Bus',i2c.liveCount?`${i2c.liveCount}/3 LIVE`:(i2c.bridgeLive?'BRIDGE ONLY':'OFFLINE'),i2c.liveCount?`${i2c.route} • ${i2c.liveSensors.map(x=>x.address).join(' • ')}`:(i2c.bridgeLive?'UNO R4 live; sensor data stale':'No fresh sensor telemetry'),'i2c');
 $('power').innerHTML=card('Main BMS',`${n(val(r,'bms_percent'),0)}%`,`${n(val(r,'bms_voltage'),2)}V ${n(val(r,'bms_current'),2)}A ${n(val(r,'bms_power'),1)}W • CELLS ${n(val(r,'bms_cell1'),3)} / ${n(val(r,'bms_cell2'),3)} / ${n(val(r,'bms_cell3'),3)} / ${n(val(r,'bms_cell4'),3)}`)+card('Motor board',`${n(val(r,'bat_voltage'),2)}V`,`${n(val(r,'bat_current'),2)}A`)+card('Jetson INA3221',`${n(val(r,'jetson_power'),1)}W`,`${n(val(r,'jetson_voltage'),3)}V ${n(val(r,'jetson_current'),2)}A • CPU/GPU ${n(val(r,'jetson_cpu_gpu_power'),1)}W • SoC ${n(val(r,'jetson_soc_power'),1)}W`)+card('Jetson / UPS',`${n(val(r,'ups_bat_percent'),0)}%`,`${n(val(r,'ups_bat_voltage'),2)}V ${n(val(r,'ups_bat_power'),1)}W`)+card(`${cellGen} HAT`,`${n(val(r,'hat_power'),1)}W`,`${n(val(r,'hat_voltage'),2)}V ${n(val(r,'hat_current'),2)}A`);
 environment(r);
 $('network').innerHTML=row('Wi-Fi',net.wifi_ip)+row(`${cellGen} data`,`${net.cell_ip} • ${val(r,'cell_operator','--')} • ${n(val(r,'cell_signal'),0)}%`)+row('Tailscale',net.tailscale_ip)+row('Active route',net.route);
 let fix=val(r,'gps_fix',{}),gpsStatusKey=recent(r,'gps_receiver_status',12)?'gps_receiver_status':'gps_arduino_status',gpsStatus=String(val(r,gpsStatusKey,'NO GPS HEARTBEAT'));$('gnss').innerHTML=row('Cell signal',`${n(val(r,'cell_signal'),0)}% ${val(r,'cell_tech')} ${val(r,'cell_operator')}`)+row('GPS route',gpsStatusKey==='gps_receiver_status'?'JETSON J12 PINS 8/10':'UNO R4 D0/D1')+row('GPS UART',gpsStatus.includes('NO_UART_BYTES')?'OFFLINE — 0 BYTES':gpsStatus.includes('NMEA_LIVE')||gpsStatus.includes('NMEA_STREAMING')?'LIVE — NMEA STREAM':gpsStatus.includes('NO_VALID_NMEA')?'BYTES / INVALID NMEA':'NO HEARTBEAT')+row('Satellites used in fix',val(r,'gps_sats',0))+row('GPS fix',fix.status>=0?`${n(fix.lat,6)}, ${n(fix.lon,6)}`:'NO FIX')+`<div class="constellation-note">${gpsStatus}</div>`;renderConstellations(val(r,'gps_const',''));
 let agent={};try{agent=JSON.parse(val(r,'agent_state','{}')||'{}')}catch(e){}
 let carrier={};try{carrier=JSON.parse(val(r,'carrier_json','{}')||'{}')}catch(e){}
 $('system').innerHTML=row('CPU',`${s.cpu_percent}%`)+row('RAM',s.ram)+row('Jetson temp',s.temp)+row('Carrier',carrier.board||'--')+row('Power mode',carrier.power_mode||'--')+row('NVMe',carrier.nvme?`${carrier.nvme.free_gb} GB free / ${carrier.nvme.total_gb} GB`:'--')+row('Carrier I/O',carrier.ok?`${carrier.usb_devices} USB • ${carrier.i2c_buses} I²C • ${carrier.csi_video_devices} CSI video`:'--')+row('Mission AI',`${agent.mode||'--'} / ${agent.phase||'--'}`)+row('Agent team',val(r,'agent_team_status','starting'))+row('Experience memory',val(r,'experience_status','starting'))+row('Agent decision',val(r,'agent_decision','No mission selected'))+row('Time',d.time);renderDetail();
 }catch(e){$('online').textContent='● OFFLINE';$('online').style.color='#ff4655'}}
refresh();setInterval(refresh,2000);
</script></body></html>"""


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True

    def stop_server(_signum, _frame):
        # HTTPServer.shutdown() must run outside serve_forever's thread.
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        ROS.close()


if __name__ == "__main__":
    main()
