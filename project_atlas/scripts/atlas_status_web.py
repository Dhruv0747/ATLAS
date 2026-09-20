#!/usr/bin/env python3
import html
import glob
import ipaddress
import os
import json
import math
import re
import socket
import atlas_wifi_web
import subprocess
import threading
SHUTDOWN_PENDING = threading.Event()
import time
import signal
from collections import deque
from atlas_web_diagnostics import DiagnosticCache, service_logs
from atlas_commissioning import Console, hardware_check
import sqlite3

import cv2
import numpy as np
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import rclpy
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import NavSatFix, LaserScan, CompressedImage, Joy
from std_msgs.msg import Bool, Float32, String, Int32, Empty

PORT = 8088
CAMERA_PAN_STEP_US = 150
CAMERA_TILT_STEP_US = 150
CAMERA_PAN_HOME_US = 1725
CAMERA_TILT_HOME_US = 1500
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
SERVICES = ["rover-base-telemetry", "rover-teleop", "atlas-uno-r4-sensor-hub", "rover-cellular", "rover-daly-bms", "rover-atlas-supervisor", "rover-status-web"]
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
        self.update_times = {}
        self.lock = threading.Lock()
        # HTTP requests are handled concurrently. Serialize incremental camera
        # updates so a touch hold cannot race itself and jump several steps.
        self.camera_lock = threading.Lock()
        self.node = None
        self.pub = None
        self.pan_pub = None
        self.tilt_pub = None
        self.camera_tracking_pub = None
        self.ai_pub = None
        self.voice_mute_pub = None
        self.commissioning_stop_pub = None
        self.steering_cal_pub = None
        self.pan_us = CAMERA_PAN_HOME_US
        self.tilt_us = CAMERA_TILT_HOME_US
        self.actual_pan_us = CAMERA_PAN_HOME_US
        self.actual_tilt_us = CAMERA_TILT_HOME_US
        self.last_camera_manual = 0.0
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
            samples = self.update_times.setdefault(key, deque(maxlen=128))
            samples.append(time.monotonic())

    def _spin(self):
        try:
            rclpy.init(args=None)
            self.node = rclpy.create_node("atlas_web_control")
            self.pub = self.node.create_publisher(Twist, "/cmd_vel_web", 10)
            self.voice_mute_pub = self.node.create_publisher(Bool, '/atlas/voice/mic_mute', 10)
            # Reuse the existing mux latch; never create a second motor path.
            self.commissioning_stop_pub = self.node.create_publisher(Empty, '/atlas/voice/stop', 10)
            self.steering_cal_pub = self.node.create_publisher(String, '/atlas/steering_calibration/request', 10)
            self.node.create_subscription(String, '/atlas/steering_calibration/status', lambda m: self._set('steering_calibration', m.data), 10)
            self.node.create_subscription(String, '/atlas/control_policy', lambda m: self._set('control_policy', m.data), 10)
            self.pan_pub = self.node.create_publisher(
                Int32, "/camera/bottom_servo_cmd_us", 10
            )
            self.tilt_pub = self.node.create_publisher(
                Int32, "/camera/second_servo_cmd_us", 10
            )
            self.camera_tracking_pub = self.node.create_publisher(
                Bool, "/atlas/camera_tracking/enabled", 10
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
            n.create_subscription(
                String,
                "/atlas/camera_tracking/status",
                lambda m: self._set("camera_tracking_status", m.data),
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
            n.create_subscription(Float32, "/jetson/power/input_voltage", lambda m: self._set("jetson_voltage", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/input_current", lambda m: self._set("jetson_current", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/input_power", lambda m: self._set("jetson_power", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/cpu_gpu_power", lambda m: self._set("jetson_cpu_gpu_power", m.data), 10)
            n.create_subscription(Float32, "/jetson/power/soc_power", lambda m: self._set("jetson_soc_power", m.data), 10)
            n.create_subscription(String, "/jetson/power/status", lambda m: self._set("jetson_power_status", m.data), 10)
            n.create_subscription(String, "/jetson/carrier/json", lambda m: self._set("carrier_json", m.data), 10)
            n.create_subscription(String, "/jetson/carrier/status", lambda m: self._set("carrier_status", m.data), 10)
            n.create_subscription(Float32, "/cellular/signal_percent", lambda m: self._set("cell_signal", m.data), 10)
            n.create_subscription(String, "/cellular/access_tech", lambda m: self._set("cell_tech", m.data), 10)
            n.create_subscription(String, "/cellular/operator", lambda m: self._set("cell_operator", m.data), 10)
            n.create_subscription(String, "/cellular/registration", lambda m: self._set("cell_registration", m.data), 10)
            n.create_subscription(Bool, "/cellular/connected", lambda m: self._set("cell_connected", m.data), 10)
            n.create_subscription(Float32, "/gps/satellites", lambda m: self._set("gps_sats", m.data), 10)
            n.create_subscription(Float32, "/gps/hdop", lambda m: self._set("gps_hdop", m.data), 10)
            n.create_subscription(String, "/gps/constellations", lambda m: self._set("gps_const", m.data), 10)
            n.create_subscription(String, "/gps/arduino_status", lambda m: self._set("gps_arduino_status", m.data), 10)
            n.create_subscription(String, "/gps/receiver_status", lambda m: self._set("gps_receiver_status", m.data), 10)
            n.create_subscription(String, "/gps/diagnostics", lambda m: self._set("gps_diagnostics", m.data), 10)
            n.create_subscription(String, "/im10a/dashboard_json", self._imu_dashboard_cb, 10)
            n.create_subscription(Float32, "/yahboom/imu/roll", lambda m: self._set("board_imu_roll", m.data), 10)
            n.create_subscription(Float32, "/yahboom/imu/pitch", lambda m: self._set("board_imu_pitch", m.data), 10)
            n.create_subscription(Float32, "/yahboom/imu/heading", lambda m: self._set("board_imu_heading", m.data), 10)
            n.create_subscription(Float32, "/motor_speed", lambda m: self._set("motor_speed", m.data), 10)
            n.create_subscription(Int32, "/yahboom/encoder/m1", lambda m: self._set("enc_m1", m.data), 10)
            n.create_subscription(Int32, "/yahboom/encoder/m2", lambda m: self._set("enc_m2", m.data), 10)
            n.create_subscription(Int32, "/yahboom/encoder/m3", lambda m: self._set("enc_m3", m.data), 10)
            n.create_subscription(Int32, "/yahboom/encoder/m4", lambda m: self._set("enc_m4", m.data), 10)
            n.create_subscription(String, "/atlas/encoder_health", lambda m: self._set("encoder_health", m.data), 10)
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
            n.create_subscription(String, '/atlas/voice/privacy', lambda m: self._set('companion_privacy', m.data), 10)
            n.create_subscription(String, '/atlas/voice/alert', lambda m: self._set('companion_alert', m.data), 10)
            n.create_subscription(Joy, "/joy", lambda m: self._set("joy", {
                "axes": len(m.axes), "buttons": len(m.buttons)
            }), 10)
            n.create_subscription(
                Int32,
                "/camera/bottom_servo_us",
                lambda m: setattr(self, "actual_pan_us", int(m.data)),
                10,
            )
            n.create_subscription(
                Int32,
                "/camera/second_servo_us",
                lambda m: setattr(self, "actual_tilt_us", int(m.data)),
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

    def camera_move(self, axis, direction, step_us=None):
        if step_us is not None and (type(step_us) is not int or step_us not in (25, 50, 100)):
            return False, 'Invalid camera step'
        with self.lock:
            feedback = dict(self.data.get('camera_servo_status', {}))
        age = time.time() - feedback.get('ts', 0)
        if not (0 <= age <= 2.0 and str(feedback.get('value', '')).startswith('online ')):
            return False, 'Camera controller offline/stale — check UNO USB link; no movement sent'
        direction = max(-1, min(1, int(direction)))
        # A manual touch always takes ownership before changing an axis. This
        # prevents the face tracker from immediately undoing the operator's
        # command and makes dashboard direction deterministic.
        if self.camera_tracking_pub is not None:
            self.camera_tracking_pub.publish(Bool(data=False))
        with self.camera_lock:
            now = time.monotonic()
            # Start a new tap/gesture from the latest reported pulse, but do
            # not let delayed feedback erase steps during a continuous hold.
            if now - self.last_camera_manual > 0.75:
                self.pan_us = self.actual_pan_us
                self.tilt_us = self.actual_tilt_us
            self.last_camera_manual = now
            if axis == "pan":
                self.pan_us = max(
                    700, min(2300, self.pan_us + direction * (step_us or CAMERA_PAN_STEP_US))
                )
                ros_sent = self.pan_pub is not None
                if ros_sent:
                    self.pan_pub.publish(Int32(data=self.pan_us))
                # Use the socket only as a startup/discovery fallback. Sending
                # the same command over ROS and the socket doubled the UNO
                # serial queue and made held-button movement lag behind touch.
                socket_sent = (
                    self._send_sensor_hub_camera(0, self.pan_us)
                    if not ros_sent else False
                )
                if ros_sent or socket_sent:
                    return True, f"manual pan {self.pan_us}us"
            if axis == "tilt":
                # The web UI's screen-space direction is opposite the installed
                # B0283 servo pulse direction: a lower pulse points the camera
                # down, while a higher pulse points it up. Translate here so even
                # an already-open/cached dashboard controls the physical direction.
                direction = -direction
                self.tilt_us = max(
                    700, min(2300, self.tilt_us + direction * (step_us or CAMERA_TILT_STEP_US))
                )
                ros_sent = self.tilt_pub is not None
                if ros_sent:
                    self.tilt_pub.publish(Int32(data=self.tilt_us))
                socket_sent = (
                    self._send_sensor_hub_camera(1, self.tilt_us)
                    if not ros_sent else False
                )
                if ros_sent or socket_sent:
                    return True, f"manual tilt {self.tilt_us}us"
            if axis == "center":
                self.pan_us = CAMERA_PAN_HOME_US
                self.tilt_us = CAMERA_TILT_HOME_US
                ros_sent = self.pan_pub is not None and self.tilt_pub is not None
                if self.pan_pub is not None:
                    self.pan_pub.publish(Int32(data=self.pan_us))
                if self.tilt_pub is not None:
                    self.tilt_pub.publish(Int32(data=self.tilt_us))
                socket_sent = False
                if not ros_sent:
                    socket_sent = self._send_sensor_hub_camera(0, self.pan_us)
                    socket_sent = self._send_sensor_hub_camera(1, self.tilt_us) or socket_sent
                if ros_sent or socket_sent:
                    return True, "manual camera centred"
        return False, "camera command path unavailable"

    def set_camera_tracking(self, enabled):
        if self.camera_tracking_pub is None:
            return False, "camera tracker control unavailable"
        self.camera_tracking_pub.publish(Bool(data=bool(enabled)))
        if enabled:
            # The tracker becomes the position owner until the next manual
            # camera gesture, which will resynchronise from live feedback.
            self.last_camera_manual = 0.0
        mode = "FACE FOLLOW" if enabled else "MANUAL"
        self._set("camera_tracking_status", f"{mode} requested")
        return True, f"camera mode: {mode}"

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
            now_mono = time.monotonic()
            rates = {}
            for key, times in self.update_times.items():
                samples = [stamp for stamp in times if now_mono - stamp < 10]
                rates[key] = round((len(samples) - 1) / (samples[-1] - samples[0]), 2) if len(samples) > 1 and samples[-1] > samples[0] else None
        fallback = sensor_hub_cache_snapshot()
        for key, item in fallback["data"].items():
            direct = data.get(key)
            if direct is None or item["ts"] > direct["ts"]:
                data[key] = {**item, "source": "UNO R4 local fallback"}
        out = {}
        now = time.time()
        for k, v in data.items():
            if k in {"camera_frame", "ai_camera_frame"}:
                continue
            out[k] = {"value": v["value"], "age": round(max(0, now - v["ts"]), 1),
                      "sample_time": v["ts"],
                      "source": v.get("source", "web telemetry callback"),
                      "observed_hz": rates.get(k) if "source" not in v else None}
            if k == 'bat_current':
                out[k]['note'] = 'Yahboom driver placeholder 0; motor current is NOT MEASURED'
            elif k == 'bat_percent':
                out[k]['note'] = 'Voltage-derived estimate; use bms_percent for main battery SOC'
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
DIAGNOSTICS = DiagnosticCache()
COMMISSIONING = Console(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    os.environ.get('ATLAS_COMMISSIONING_DB', '/home/jetson/project_atlas/data/commissioning/results.sqlite3'),
    ROS.snapshot,
)


def network_status():
    info = {"wifi_ip": "--", "cell_ip": "--", "tailscale_ip": "--", "route": "--", "ssh": "--"}
    for line in run(["ip", "-4", "-br", "addr"]).splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        iface, state, ip = parts[0], parts[1], parts[2].split("/")[0]
        if iface in ("wlan0", "wlP1p1s0") and state == "UP":
            info["wifi_ip"] = ip
        elif iface in ("wwan0", "usb0") or iface.startswith("enx"):
            info["cell_ip"] = ip
        elif iface == "tailscale0":
            info["tailscale_ip"] = ip
    # Kernel route lookup sends no packets. An assigned modem IP is not proof
    # of mobile registration or Internet connectivity.
    try:
        route = json.loads(run(["ip", "-j", "route", "get", "1.1.1.1"]) or '[]')
        iface = route[0].get("dev", "") if route else ""
        kind = "Wi-Fi" if iface.startswith("wl") else "cellular" if iface in ("usb0", "wwan0") or iface.startswith("enx") else iface
        info["route"] = f"{kind} ({iface})" if iface else "unavailable"
        info["route_note"] = "Selected route only; Internet access not tested"
    except (ValueError, TypeError):
        pass
    try:
        with open('/run/atlas-network/status.json', encoding='utf-8') as stream:
            fallback = json.load(stream)
        fallback['age_s'] = round(max(0, time.time() - fallback['time']), 1)
        fallback['fresh'] = fallback['age_s'] < 45
        info['fallback'] = fallback
    except (OSError, ValueError, KeyError, TypeError):
        info['fallback'] = {'fresh': False, 'mode': 'UNAVAILABLE'}
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
    # Diagnostic inventory is independent of the existing control allowlist.
    # One background query per 10s, shared with the workbench.
    return {item['unit']: item['active'] for item in DIAGNOSTICS.snapshot()['services']}


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
        commissioning_assets = {'/commissioning': ('atlas_commissioning.html', 'text/html'),
                                '/commissioning.js': ('atlas_commissioning_ui.js', 'application/javascript'),
                                '/steering-commissioning.js': ('atlas_steering_ui.js', 'application/javascript'),
                                '/commissioning-evidence.js': ('atlas_evidence_ui.js', 'application/javascript')}
        if self.path in commissioning_assets:
            name, mime = commissioning_assets[self.path]
            try:
                with open(os.path.join(os.path.dirname(__file__), name), 'rb') as stream:
                    body = stream.read()
                self.send_response(200)
                self.send_header('Content-Type', mime + '; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_error(404)
            return
        if self.path == '/api/commissioning':
            data = ROS.snapshot()
            json_response(self, 200, {'ros': data, 'configuration': COMMISSIONING.config,
                                     'check': hardware_check(data), 'state': COMMISSIONING.state()})
            return
        if self.path == '/api/commissioning/history':
            try:
                json_response(self, 200, {'history': COMMISSIONING.history(),
                                         'evidence': COMMISSIONING.ledger.history() if COMMISSIONING.ledger else [],
                                         'evidence_error': COMMISSIONING.evidence_error})
            except Exception:
                json_response(self, 503, {'error': 'History storage unavailable'})
            return
        if self.path == '/api/commissioning/evidence':
            try:
                json_response(self, 200, COMMISSIONING.evidence())
            except Exception:
                json_response(self, 503, {'error': 'Evidence unavailable — autonomy blocked; restore evidence storage before testing'})
            return
        if self.path == '/wifi':
            body = atlas_wifi_web.PAGE.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/api/wifi':
            try:
                json_response(self, 200, atlas_wifi_web.request({'action': 'status'}))
            except Exception:
                json_response(self, 503, {'error': 'Wi-Fi setup service unavailable'})
            return
        if self.path.startswith("/api/radar"):
            json_response(self, 200, {"radar": radar_snapshot()})
            return
        if self.path.startswith("/api/diagnostics/logs?"):
            unit = parse_qs(self.path.split('?', 1)[1]).get('unit', [''])[0]
            try:
                json_response(self, 200, service_logs(unit))
            except ValueError as exc:
                json_response(self, 400, {"error": str(exc)})
            return
        if self.path == "/api/diagnostics":
            json_response(self, 200, DIAGNOSTICS.snapshot())
            return
        if self.path == "/diagnostics.js":
            try:
                with open(os.path.join(os.path.dirname(__file__), 'atlas_diagnostics_ui.js'), 'rb') as stream:
                    body = stream.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_error(404)
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
        if self.path.startswith('/api/commissioning'):
            if self.path != '/api/commissioning' or not atlas_wifi_web.same_origin(self.headers):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid request')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('Expected object')
                if payload.get('action') == 'stop':
                    if ROS.commissioning_stop_pub is None or not ROS.ready:
                        json_response(self, 503, {'error': 'Stop publisher unavailable; use remote stop'})
                    else:
                        ROS.commissioning_stop_pub.publish(Empty())
                        json_response(self, 202, {'message': 'Mux latch requested, not physical stop confirmation'})
                elif payload.get('action') == 'camera':
                    if SHUTDOWN_PENDING.is_set():
                        raise ValueError('Shutdown pending')
                    axis, direction = payload.get('axis'), payload.get('direction')
                    if axis not in ('pan', 'tilt', 'center') or type(direction) is not int or direction not in (-1, 0, 1):
                        raise ValueError('Invalid camera direction')
                    ok, message = ROS.camera_move(axis, direction, payload.get('step_us', 25))
                    json_response(self, 200 if ok else 503, {'ok': ok, 'message': message})
                elif payload.get('action') == 'steering':
                    if SHUTDOWN_PENDING.is_set() or not ROS.ready or ROS.steering_cal_pub is None:
                        raise ValueError('Steering owner unavailable')
                    command = payload.get('command')
                    if not isinstance(command, dict) or command.get('op') not in ('enter','heartbeat','jog','mark','save','exit','reset_draft'):
                        raise ValueError('Invalid steering request')
                    ROS.steering_cal_pub.publish(String(data=json.dumps(command)))
                    json_response(self, 202, {'message': 'Requested; check owner acknowledgement, not physical feedback'})
                elif payload.get('action') == 'test':
                    if SHUTDOWN_PENDING.is_set():
                        raise ValueError('Shutdown pending')
                    result = COMMISSIONING.start(payload.get('kind'), payload.get('side'), payload.get('known_mm'))
                    json_response(self, 202, result)
                elif payload.get('action') == 'verify_steering':
                    result = COMMISSIONING.confirm_steering(payload.get('side'), payload.get('configuration_hash'), payload.get('confirmation'))
                    json_response(self, 200, result)
                elif payload.get('action') == 'invalidate_evidence':
                    if COMMISSIONING.ledger is None or COMMISSIONING.evidence_error:
                        raise ValueError('Evidence storage unavailable')
                    result = COMMISSIONING.ledger.invalidate(payload.get('gate'), payload.get('reason'), payload.get('test_id'))
                    json_response(self, 200, result)
                else:
                    json_response(self, 403, {'error': 'Actuator commissioning and calibration writes are locked; no command sent'})
            except (ValueError, TypeError) as exc:
                json_response(self, 400, {'error': str(exc)[:300] or 'Invalid commissioning request'})
            except (OSError, sqlite3.Error):
                json_response(self, 503, {'error': 'Evidence/configuration storage unavailable; nothing authorized'})
            return
        if self.path == '/api/voice':
            if not atlas_wifi_web.same_origin(self.headers):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 256 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid voice request')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or type(payload.get('muted')) is not bool:
                    raise ValueError('muted must be boolean')
                if ROS.voice_mute_pub is None:
                    json_response(self, 503, {'ok': False, 'message': 'ROS voice control unavailable'})
                    return
                ROS.voice_mute_pub.publish(Bool(data=payload['muted']))
                json_response(self, 202, {'ok': True, 'message': 'Mute preference requested; wait for live privacy acknowledgement below.'})
            except (ValueError, TypeError):
                json_response(self, 400, {'ok': False, 'message': 'Invalid voice request'})
            return
        if self.path == '/api/wifi':
            if not atlas_wifi_web.same_origin(self.headers):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid Wi-Fi request')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or payload.get('action') not in ('scan', 'connect'):
                    raise ValueError('Invalid Wi-Fi operation')
                result = atlas_wifi_web.request(payload)
                json_response(self, 400 if result.get('error') else 200, result)
            except ValueError:
                json_response(self, 400, {'error': 'Invalid Wi-Fi request'})
            except Exception:
                json_response(self, 503, {'error': 'Wi-Fi setup service unavailable'})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        form = parse_qs(self.rfile.read(length).decode())
        action = form.get("action", [""])[0]
        if SHUTDOWN_PENDING.is_set():
            json_response(self, 409, {"ok": False, "message": "Shutdown already requested; controls disabled"})
            return
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
        elif action == "camera_tracking":
            enabled = form.get("enabled", ["0"])[0].strip().lower() in {
                "1", "true", "yes", "on"
            }
            ok, msg = ROS.set_camera_tracking(enabled)
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
            if form.get('confirm', [''])[0] != 'POWER_OFF_ATLAS' or not atlas_wifi_web.same_origin(self.headers):
                json_response(self, 403, {"ok": False, "message": "Shutdown requires dashboard confirmation"})
                return
            ok, detail = run_quiet(['sudo', '-n', '-l', '/sbin/shutdown', '-h', 'now'], timeout=3)
            if not ok:
                json_response(self, 503, {"ok": False, "message": "Shutdown permission unavailable"})
                return
            SHUTDOWN_PENDING.set()
            stop_rover()
            def power_off():
                time.sleep(2)
                ok, detail = run_quiet(['sudo', '-n', '/sbin/shutdown', '-h', 'now'], timeout=8)
                if not ok:
                    SHUTDOWN_PENDING.clear()
                    print('Dashboard shutdown failed: '+str(detail), flush=True)
            threading.Thread(target=power_off, daemon=True).start()
            json_response(self, 202, {"ok": True, "message": "Shutdown requested. Wait for Jetson to power off before disconnecting power."})
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

var thermalHist=[];function val(r,k,d='--'){return r[k]&&r[k].value!==undefined&&r[k].value!==null?r[k].value:d}function num(v,d=0){v=Number(v);return Number.isFinite(v)?v.toFixed(d):'--'}function row(a,b){return `<div class="row"><span>${a}</span><span>${b}</span></div>`}function bar(v){var n=Math.max(0,Math.min(100,Number(v)||0));return `<div class="bar"><div class="fill" style="width:${n}%"></div></div>`}function card(a,b,c=''){return `<div class="card"><div class="label">${a}</div><div class="value">${b}</div><div class="sub">${c}</div></div>`}function toast(t){document.getElementById('footReady').textContent=t}
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
.healthname{font-size:11px;font-weight:800;display:flex;justify-content:space-between;gap:4px}.healthstate{font-size:9px}.healthhint{font-size:9px;color:#aac0d1;margin-top:3px;line-height:1.25}.healthitem.touch{cursor:pointer}.healthitem.touch:hover{border-color:var(--cyan);box-shadow:0 0 14px rgba(23,213,255,.16)}
.constellation-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:7px}.constellation{padding:6px;border-radius:6px;background:#07131f;border:1px solid #1d3c54}
.constellation-top{display:flex;justify-content:space-between;font-size:10px;font-weight:800}.satbar{height:7px;margin-top:5px;background:#1a2a39;border-radius:5px;overflow:hidden}.satfill{height:100%;border-radius:5px}.constellation-note{font-size:9px;color:#8ca6bb;margin-top:6px}
.companion{border-color:#216f8d;background:linear-gradient(145deg,rgba(10,43,60,.97),rgba(6,19,31,.98));box-shadow:0 0 22px rgba(23,213,255,.08)}
.companionHead{display:flex;align-items:center;justify-content:space-between;gap:8px}.companionState{font-size:10px;font-weight:900;padding:4px 8px;border:1px solid var(--cyan);border-radius:12px;color:var(--cyan)}
.companionGrid{display:grid;grid-template-columns:1.25fr .75fr;gap:7px}.speech{background:#06131f;border:1px solid #1d4863;border-radius:8px;padding:8px;min-height:62px}.speech.you{border-left:4px solid #18c7ff}.speech.atlas{border-left:4px solid #34e58b}.speechText{font-size:14px;line-height:1.3;margin-top:3px;overflow-wrap:anywhere}
.thoughts{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:7px}.thought{background:#071522;border-radius:6px;padding:6px;min-width:0}.thought strong{display:block;font-size:9px;color:var(--muted);margin-bottom:2px}.thought span{font-size:11px;overflow-wrap:anywhere}
.companionStatus{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-top:7px}.pill{text-align:center;background:#071522;border:1px solid #24435d;border-radius:6px;padding:5px 3px;font-size:9px}.rgbDot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;background:#198dff;box-shadow:0 0 8px currentColor}
.voiceLedGuide{margin-top:7px;padding:7px;background:#06131f;border:1px solid #214761;border-radius:7px}.voiceLedTitle{display:flex;justify-content:space-between;gap:8px;font-size:9px;font-weight:900;color:#bcd3e5}.voiceLedNow{color:#ffcc3d;text-align:right;overflow-wrap:anywhere}.voiceLedStates{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin-top:6px}.voiceLedState{font-size:8px;color:#9fb8ca;line-height:1.2;white-space:nowrap}.voiceLedState b{display:block;color:#eef7ff;font-size:8px}.voiceSwatch{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:3px;box-shadow:0 0 6px currentColor}.voiceUsbReason{margin-top:6px;color:#aac0d1;font-size:9px;line-height:1.25;overflow-wrap:anywhere}
/* ATLAS glass cockpit: 30% surface opacity = 70% transparent. */
body{position:relative;background:
 linear-gradient(rgba(23,213,255,.075) 1px,transparent 1px),linear-gradient(90deg,rgba(23,213,255,.075) 1px,transparent 1px),
 radial-gradient(circle at 14% 10%,rgba(23,213,255,.48),transparent 33%),
 radial-gradient(circle at 86% 18%,rgba(52,229,139,.36),transparent 31%),
 radial-gradient(circle at 48% 88%,rgba(105,78,255,.42),transparent 39%),#02070d;background-size:34px 34px,34px 34px,auto,auto,auto,auto;background-attachment:fixed}
body:before{content:"";position:fixed;inset:58px 0 0;pointer-events:none;background:url('/logo.png') center/48vmin no-repeat;opacity:.13;filter:drop-shadow(0 0 45px rgba(23,213,255,.65));z-index:0}
body>*{position:relative;z-index:1}
header{background:rgba(5,20,32,.22);backdrop-filter:blur(18px) saturate(155%);-webkit-backdrop-filter:blur(18px) saturate(155%);box-shadow:0 8px 28px rgba(0,0,0,.25)}
.panel,.companion{background:linear-gradient(145deg,rgba(14,39,59,.20),rgba(2,12,23,.16));backdrop-filter:blur(13px) saturate(155%);-webkit-backdrop-filter:blur(13px) saturate(155%);border-color:rgba(62,181,231,.58);box-shadow:0 10px 32px rgba(0,0,0,.22),inset 0 1px 0 rgba(255,255,255,.09)}
.card,.healthitem,.constellation,.speech,.thought,.pill,.voiceLedGuide,.detailTile{background:rgba(4,18,31,.20);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);text-shadow:0 1px 2px #000}
.healthitem.fail{background:rgba(70,12,23,.38)}
.btn{background:rgba(16,43,66,.54);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.cameraStatus{display:inline-block;margin-left:8px;font-size:9px;color:var(--muted);font-weight:800}.cameraStatus.ok{color:var(--green)}.cameraStatus.warn{color:#ffcc3d}.cameraStatus.fail{color:var(--red)}
.selfTestStamp{font-size:9px;color:var(--muted);margin:0 0 7px;line-height:1.35}
.bootBanner{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:7px 8px 0;padding:8px 12px;border:1px solid rgba(23,213,255,.72);border-radius:10px;background:rgba(4,20,33,.18);backdrop-filter:blur(13px) saturate(160%);-webkit-backdrop-filter:blur(13px) saturate(160%);box-shadow:0 0 24px rgba(23,213,255,.18);font-size:11px;font-weight:800}.bootBanner b{color:var(--cyan)}.bootBanner span{color:#ffcc3d}.buildTag{margin-left:auto;color:#b4d7e9;font:9px ui-monospace,monospace}
.grid{height:calc(100vh - 99px)}
.batteryBadge{display:flex;align-items:center;gap:9px;flex-shrink:0;border:1px solid #45809a;border-radius:12px;background:#0b2236aa;color:white;padding:6px 10px;cursor:pointer;text-align:left}.batteryBadge strong{font-size:18px}.batteryBadge small{display:block;font-size:9px;letter-spacing:.4px}.batteryShell{position:relative;display:block;width:38px;height:20px;border:2px solid #d4e6ef;border-radius:5px;padding:2px;margin-right:3px}.batteryShell:after{content:'';position:absolute;right:-5px;top:5px;width:3px;height:7px;background:#d4e6ef;border-radius:0 2px 2px 0}.batteryFill{display:block;height:100%;border-radius:2px;transition:width .5s}.batteryBolt{position:absolute;inset:-3px 0;text-align:center;color:white;text-shadow:0 1px 3px #000;font-size:24px;font-weight:bold}header{height:auto;min-height:58px;flex-wrap:wrap}@media(max-width:700px){header h1{font-size:13px}.batteryBadge{padding:5px 8px}.grid{height:auto}}
section.col:nth-of-type(3) .panel:has(#heatmap){order:-3;border-color:#34e58b}
section.col:nth-of-type(3) .panel:has(#healthGrid){order:-2}
section.col:nth-of-type(3) .panel:has(#power){order:-1}
#toast{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);background:#122b40;border:1px solid var(--cyan);padding:8px 14px;border-radius:20px;display:none;z-index:8}
.diagTable{width:100%;border-collapse:collapse;font-size:12px}.diagTable th,.diagTable td{text-align:left;padding:9px;border-bottom:1px solid #25475b;vertical-align:top}.diagTable th{color:#17d5ff}.diagTable tr:hover{background:#122b3d}.rawData{overflow-wrap:anywhere}.sensorModal{display:none;position:fixed;inset:0;z-index:20;background:rgba(0,5,10,.88);padding:3vh 3vw}.sensorModal.open{display:flex}.sensorSheet{width:min(980px,94vw);max-height:94vh;margin:auto;overflow:auto;background:#07131f;border:2px solid var(--cyan);border-radius:14px;padding:14px;box-shadow:0 0 38px rgba(23,213,255,.28)}.sensorHead{display:flex;align-items:center;gap:10px;border-bottom:1px solid #214761;padding-bottom:9px;margin-bottom:10px}.sensorHead h2{font-size:18px;margin:0}.closeDetail{margin-left:auto;background:#7f1722;border:1px solid #ff5966;color:#fff;border-radius:8px;padding:10px 18px;font-weight:800}.detailGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.detailTile{background:#0b1d2c;border:1px solid #214761;border-radius:9px;padding:10px}.detailTile b{display:block;color:var(--cyan);font-size:11px}.detailTile strong{display:block;font-size:22px;margin-top:5px}.rangeBar{height:18px;background:#13283a;border-radius:9px;overflow:hidden;margin-top:8px}.rangeFill{height:100%;background:linear-gradient(90deg,#ff4655,#ffcc3d,#34e58b);transition:width .25s}.modalCamera{width:100%;max-height:65vh;object-fit:contain;background:#000;border-radius:8px}.modalHeat{display:grid;grid-template-columns:repeat(8,1fr);gap:3px;max-width:460px;aspect-ratio:1;margin:auto}.modalHeat i{display:block;border-radius:3px}.rawData{font:12px ui-monospace,monospace;white-space:pre-wrap;color:#bcd3e5;background:#040a12;border-radius:8px;padding:10px;margin-top:9px}.sensorHint{color:#8ca6bb;font-size:11px;margin-top:8px}
@media(max-width:700px){.detailGrid{grid-template-columns:1fr}.sensorModal{padding:1vh 2vw}.sensorSheet{max-height:98vh}}
@media(max-width:900px){.grid{display:block;height:auto;width:100%;overflow:hidden}.col,.panel{overflow:visible;margin-bottom:8px;min-width:0}.camera{height:42vh}.envgrid{grid-template-columns:1fr}.heatmap{max-width:180px}canvas{max-width:100%}header .sub{display:none}.headerBtn{padding:7px 9px}.headerText{display:none}}
@media(min-width:1500px){body{font-size:15px}.grid{grid-template-columns:minmax(300px,20vw) minmax(600px,1fr) minmax(350px,23vw)}.camera{height:min(52vh,610px)}.speechText{font-size:16px}}
@media(max-width:1150px) and (min-width:901px){.grid{grid-template-columns:265px minmax(390px,1fr) 295px}.companionGrid{grid-template-columns:1fr}.companionStatus{grid-template-columns:1fr 1fr}.voiceLedStates{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<header><img src="/logo.png"><div><h1>PROJECT ATLAS COMMAND CENTER</h1><div class="sub">Headless rover control • hold-to-drive • automatic stop watchdog</div></div><div class="live" id="online">CONNECTING</div><a class="headerBtn cloud" href="https://project-atlas-jetson.tail12f5ff.ts.net:8443/" title="Open the read-only ATLAS Visual Cloud live ROS observability dashboard."><span class="headerIcon">◈</span><span class="headerText">VISUAL CLOUD</span></a><a class="headerBtn" href="https://project-atlas-jetson.tail12f5ff.ts.net/" title="Open two-way ATLAS intercom. The camera stream closes to preserve call quality and AI Voice pauses during the call."><span class="headerIcon">☎</span><span class="headerText">TALK / LISTEN</span></a></header>
<div class="bootBanner"><b>LIVE TELEMETRY CHECK</b><a class="btn" href="/commissioning">COMMISSIONING / HARDWARE CHECK</a><a class="btn" href="#diagnosticsPanel" onclick="document.getElementById('diagnosticsPanel').open=true;refreshDiagnostics(true)">DIAGNOSTICS / LOGS</a><button class="btn" id="shutdownButton" style="border-color:#ff5966;color:#ffbdc4" onclick="shutdownAtlas()">⏻ SHUT DOWN</button><span id="bootBannerState">COLLECTING LIVE DATA…</span><div class="buildTag">WEB DIAGNOSTICS v4</div></div>
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
 </div><div class="cards" style="margin-top:8px"><button class="btn" data-track="0">MANUAL CONTROL</button><button class="btn" data-track="1">FACE FOLLOW</button></div><div class="detail" id="cameraTracking">Camera mode checking</div></div>
 <div class="panel"><h2>JETSON AI POWER</h2><div class="cards">
  <button class="btn ai-on" data-ai="object">AI ON</button><button class="btn ai-off" data-ai="eco">AI ECO / OFF</button>
 </div><div class="detail" id="ai">AI status waiting</div></div>
 <div class="panel card touch" onclick="openDetail('encoders')"><h2>MOTION / ENCODERS — TOUCH FOR ALL FOUR</h2><div id="motion"></div></div>
</section>
<section class="col">
 <div class="panel"><h2>LIVE CAMERA — LATEST FRAME / NO BUFFER <span class="cameraStatus warn" id="cameraStatus">CONNECTING</span><button class="btn" style="float:right;padding:5px 9px" onclick="openDetail('camera')">OPEN DATA</button></h2><img class="camera" id="camera" src="/camera.jpg?latest=boot" onclick="openDetail('camera')"></div>
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
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#198dff;background:#198dff"></i>BLUE</b>Voice idle, not drive readiness</div>
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#34e58b;background:#34e58b"></i>GREEN</b>Listening</div>
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#eef7ff;background:#eef7ff"></i>WHITE</b>Thinking</div>
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#17d5ff;background:#17d5ff"></i>BLUE PULSE</b>Speaking</div>
    <div class="voiceLedState"><b><i class="voiceSwatch" style="color:#ff4655;background:#ff4655"></i>RED</b>Muted / error / live call: read status</div>
   </div>
   <div class="voiceUsbReason" id="voiceUsbReason">Checking ESP32-S3 voice USB connection</div>
  </div>
  <div class="detail" style="margin-top:8px" id="companionPrivacy">Privacy status unavailable</div>
  <div class="detail" id="companionAlert">No recent announcement</div>
  <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px"><button class="btn" onclick="voiceMute(true)">MUTE AI MIC</button><button class="btn" onclick="voiceMute(false)">ENABLE AI MIC</button></div>
  <div class="detail" style="margin-top:8px;color:#34e58b">☎ TALK / LISTEN opens a separate live call and pauses AI Voice. Software mute is not a physical microphone disconnect. English + Hindi speech is AI-generated. Spoken questions use cloud transcription; automatic alerts use local speech. Use remote B for an immediate stop, not voice.</div>
 </div>
 <div class="panel"><h2>RANGE & ATTITUDE</h2><div class="cards" id="sensors"></div></div>
 <div class="panel"><h2>RD-03D LIVE MOTION RADAR — TOUCH DISPLAY FOR DETAILS</h2><div class="radarViewBar"><button class="btn" id="radar2dBtn" onclick="setRadarView('2d')">2D RADAR</button><button class="btn active" id="radar3dBtn" onclick="setRadarView('3d')">3D PEOPLE</button><span class="radarViewNote">LIVE RD-03D DATA<br>UP TO 3 TARGETS</span></div><canvas class="radarScope radarHidden" id="radarScope" width="720" height="340" onclick="openDetail('radar')"></canvas><canvas class="radarScope" id="radarTwin" width="720" height="340" onclick="openDetail('radar')"></canvas><div class="detail" id="radarCaption">WAITING FOR RADAR UART DATA</div></div>
</section>
<section class="col">
 <div class="panel"><div class="healthhead"><h2>LIVE HARDWARE HEALTH — TOUCH FOR DETAILS</h2><div class="healthsummary" id="healthSummary">CHECKING</div></div><div class="selfTestStamp" id="selfTestStamp">Waiting for live sensor messages after dashboard startup…</div><div class="healthgrid" id="healthGrid"></div></div>
 <div class="panel"><h2>POWER</h2><div class="cards" id="power"></div></div>
 <div class="panel"><h2>ENVIRONMENT — INSIDE / OUTSIDE</h2>
  <div class="envgrid"><div class="card touch" onclick="openDetail('thermal')"><div class="heatmap" id="heatmap"></div><div class="detail" id="thermalStats">Inside thermal waiting</div><div class="detail">TOUCH FOR 64-PIXEL DATA</div></div>
  <div class="card touch" onclick="openDetail('environment')"><div class="detail" id="outsideStats">Outside sensor waiting</div><canvas class="chart" id="insideChart" width="300" height="82"></canvas><canvas class="chart" id="outsideChart" width="300" height="82" style="margin-top:6px"></canvas><div class="detail">TOUCH FOR GAS / PRESSURE / IAQ</div></div></div>
 </div>
 <div class="panel"><h2>NETWORK</h2><div id="network"></div></div>
 <div class="panel"><h2>GNSS / CELLULAR</h2><div id="gnss"></div><div class="constellation-grid" id="constellationGrid"></div><div class="constellation-note">Primary: Hiwonder GPS V1 USB. Bars show receiver-reported satellites in view, NOT signal strength. Zero means zero reported satellites. NMEA labels alone do not mean satellites detected. No report does not mean unsupported constellation. Touch GPS diagnostics for source, age and errors.</div></div>
 <div class="panel"><h2>SYSTEM</h2><div id="system"></div></div>
</section></main>
<details class="panel" id="diagnosticsPanel" style="margin:10px" ontoggle="if(this.open){renderDiagnostics();refreshDiagnostics(true)}">
<summary style="padding:12px;font-size:18px;color:#17d5ff;cursor:pointer">DIAGNOSTIC WORKBENCH — SERVICES / LIVE DATA / LOGS / USB</summary>
<div class="detail" id="diagState">Open to collect diagnostics</div>
<p class="detail">Read-only. Active service does not prove a working sensor. Recent telemetry is not a mechanical test pass. Mapping services may be inactive when not selected. Safety stays on the Jetson.</p>
<button class="btn" onclick="refreshDiagnostics(true)">REFRESH HEALTH</button>
<button class="btn" onclick="downloadDiagnostics()">EXPORT DIAGNOSTIC SNAPSHOT</button>
<a class="btn" href="https://project-atlas-jetson.tail12f5ff.ts.net:8443/">VISUAL CLOUD / ROS GRAPH</a>
<h2>SERVICE STATUS &amp; RESTARTS</h2><div style="overflow:auto;max-height:420px"><table class="diagTable"><thead><tr><th>Subsystem</th><th>State / mode</th><th>Restarts</th><th>Result / exit</th><th>Read log</th></tr></thead><tbody id="diagServices"></tbody></table></div>
<pre class="rawData" id="diagLog" style="max-height:300px;overflow:auto">Select LOGS beside a service. No service is restarted.</pre>
<h2>ALL DASHBOARD TELEMETRY</h2>
<input id="diagFilter" type="search" placeholder="Filter: gps, enc, imu, bms, radar…" oninput="renderDiagnostics()" style="padding:10px;width:min(100%,480px)">
<p class="detail">Age = last update received by this web server. Observed Hz = recent callback rate, not source ROS topic Hz. Cached values have no measured Hz. OLDER means at least 10s; slow status topics can normally be older. Click a key for its full current value.</p>
<div style="overflow:auto;max-height:480px"><table class="diagTable"><thead><tr><th>Telemetry key</th><th>Freshness / age</th><th>Observed Hz</th><th>Source</th><th>Latest value</th></tr></thead><tbody id="diagTelemetry"></tbody></table></div>
<h2>USB SERIAL IDENTITY (READ-ONLY)</h2><pre class="rawData" id="diagPorts"></pre>
<h2>DEPLOYED WEB FILE FINGERPRINTS</h2><pre class="rawData" id="diagVersions"></pre>
</details><div id="toast"></div>
<div class="sensorModal" id="sensorModal" role="dialog" aria-modal="true"><div class="sensorSheet"><div class="sensorHead"><h2 id="detailTitle">LIVE SENSOR</h2><span class="live" id="detailFresh">LIVE</span><button class="closeDetail" onclick="closeDetail()">CLOSE</button></div><div id="detailBody"></div></div></div>
<script src="/diagnostics.js"></script>
<script>
const $=id=>document.getElementById(id), val=(r,k,d='--')=>r[k]&&r[k].value!==undefined?r[k].value:d;
const n=(v,d=1)=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v).toFixed(d):'--';
const card=(a,b,c='',key='')=>`<div class="card ${key?'touch':''}" ${key?`onclick="openDetail('${key}')"`:''}><div class="label">${a}</div><div class="value">${b}</div><div class="detail">${c}${key?' • TOUCH FOR LIVE DATA':''}</div></div>`;
const row=(a,b)=>`<div class="row"><span>${a}</span><span>${b}</span></div>`;
const age=(r,k)=>r[k]&&r[k].age!==null&&Number.isFinite(Number(r[k].age))?Number(r[k].age):9999;
const dashboardStarted=Date.now();
const recent=(r,k,seconds)=>age(r,k)<seconds;
function cellGeneration(raw){let t=String(raw||'').toLowerCase();if(t.includes('5g')||t.includes('nr'))return '5G';if(t.includes('lte'))return '4G';if(t.includes('umts')||t.includes('hspa'))return '3G';if(t.includes('gsm')||t.includes('edge')||t.includes('gprs'))return '2G';return 'CELLULAR'}
function healthItem(name,state,hint,seconds=null,detailKey=''){
 let ageText=seconds===null?'':seconds<60?`${seconds.toFixed(1)}s`:`${Math.round(seconds/60)}m`;
 return `<div class="healthitem ${state} ${detailKey?'touch':''}" ${detailKey?`onclick="openDetail('${detailKey}')"`:''}><div class="healthname"><span>${name}</span><span class="healthstate">${state.toUpperCase()} ${ageText}</span></div><div class="healthhint">${hint}${detailKey?' • TOUCH FOR DETAILS':''}</div></div>`;
}
function renderHealth(r,net){
 const sys=latestStatus.system||{},cellRegistered=recent(r,'cell_registration',20)&&['home','roaming','registered'].includes(String(val(r,'cell_registration','')).toLowerCase());
 let thermal={};try{thermal=JSON.parse(val(r,'thermal_json','{}')||'{}')}catch(e){}
 let carrier={};try{carrier=JSON.parse(val(r,'carrier_json','{}')||'{}')}catch(e){}
 let brain={};try{brain=JSON.parse(val(r,'atlas_health','{}')||'{}')}catch(e){}
 let encoderHealth={};try{encoderHealth=JSON.parse(val(r,'encoder_health','{}')||'{}')}catch(e){}
 let ultrasonicEnabled=brain.ultrasonic_enabled!==false;
 let cellGen=cellGeneration(val(r,'cell_tech',''));
 const gpsCheck=gnssInfo(r);
 let i2c=i2cInfo(r);
 let items=[
  ['CAMERA',recent(r,'camera_info',4)?'ok':'fail',recent(r,'camera_info',4)?'IMX708 video frames live':'No frames: check CSI ribbon and camera service','camera_info','camera'],
  ['MOTOR BOARD LINK',recent(r,'encoder_health',3)&&encoderHealth.packet_fresh===true?'ok':'fail',recent(r,'encoder_health',3)&&encoderHealth.packet_fresh===true?`Encoder packets live • age ${n(encoderHealth.packet_age_s,2)} s`:'No fresh encoder packets: check board power / serial link','encoder_health','encoders'],
  ['ENCODER SAFETY',recent(r,'encoder_health',3)?(encoderHealth.autonomy_ready===true?'ok':(['DEGRADED','QUALIFYING','READY','HEALTHY'].includes(encoderHealth.state)?'warn':'fail')):'fail',recent(r,'encoder_health',3)?`${encoderHealth.state||'UNKNOWN'} • ${encoderHealth.reason||encoderHealth.faults?.join(', ')||'Validation pending'}`:'Safety heartbeat stale — autonomy blocked','encoder_health','encoders'],
  ['ENCODER M1 • BACK LEFT',recent(r,'enc_m1',4)?'ok':'fail',recent(r,'enc_m1',4)?`Live count ${val(r,'enc_m1')} • zero is valid while stopped`:'No current M1 reading','enc_m1','encoders'],
  ['ENCODER M2 • BACK RIGHT',recent(r,'enc_m2',4)?'ok':'fail',recent(r,'enc_m2',4)?`Live count ${val(r,'enc_m2')} • zero is valid while stopped`:'No current M2 reading','enc_m2','encoders'],
  ['ENCODER M3 • FRONT LEFT',recent(r,'enc_m3',4)?'ok':'fail',recent(r,'enc_m3',4)?`Live count ${val(r,'enc_m3')} • zero is valid while stopped`:'No current M3 reading','enc_m3','encoders'],
  ['ENCODER M4 • FRONT RIGHT',(encoderHealth.excluded_encoders||[]).includes(4)?'warn':(recent(r,'enc_m4',4)?'ok':'fail'),(encoderHealth.excluded_encoders||[]).includes(4)?`EXCLUDED / FAULTY • raw ${val(r,'enc_m4','--')} • motor remains enabled`:(recent(r,'enc_m4',4)?`Raw count ${val(r,'enc_m4')}`:'No current M4 reading'),'enc_m4','encoders'],
  ['XBOX REMOTE',recent(r,'joy',8)?'ok':'warn',recent(r,'joy',8)?'Controller input received':'Wake controller, then press a stick or button','joy'],
  ['IMU / COMPASS',recent(r,'imu_heading',4)?'warn':'fail',recent(r,'imu_heading',4)?'Hiwonder IM10A live — navigation fusion not validated':'IM10A USB data stale or disconnected','imu_heading','imu'],
  ['RPLIDAR',recent(r,'lidar',4)?'ok':'fail',recent(r,'lidar',4)?'Laser scan live':'Check LiDAR USB, motor and cable','lidar','lidar'],
  ['RD-03D RADAR',recent(r,'radar',3)?'ok':'fail',recent(r,'radar',3)?'Valid 30-byte target frames live':(recent(r,'radar_link',3)?`UNO bytes received, but no valid target frame • ${val(r,'radar_decoder_status','decoder checking')}`:'No radar UART bytes: check power, GND, TX → D12 and RX → D11'),'radar','radar'],
  ['ULTRASONIC',!ultrasonicEnabled?'warn':(['us_front','us_left','us_right','us_rear'].every(k=>recent(r,k,4)&&Number(val(r,k,-1))>0)?'ok':'warn'),'Each range checked separately; -1 means no valid echo, NOT clear space. Uninstalled sensors are expected to be unavailable.','us_status','ultrasonic'],
  ['I2C SENSOR BUS',i2c.liveCount?'ok':(i2c.bridgeLive?'warn':'fail'),i2c.liveCount?`${i2c.liveCount}/3 sensor${i2c.liveCount===1?'':'s'} live through ${i2c.route}`:(i2c.bridgeLive?'UNO R4 bridge live, but sensor data is stale':'No live I2C sensor telemetry'),i2c.freshestKey,'i2c'],
  ['INSIDE IR 8x8',thermal.ok&&recent(r,'thermal_json',5)?'ok':'fail',thermal.ok?'AMG8833 heatmap live':'Not detected: check 3.3V, GND, SDA pin 3, SCL pin 5','thermal_json','thermal'],
  ['OUTSIDE TEMP',recent(r,'outside_temperature',9)?'ok':'fail',recent(r,'outside_temperature',9)?'BME680 ambient temperature live':'Check BME680 wiring/address 0x77','outside_temperature','environment'],
  ['CAMERA SERVOS',cameraControlLive(r)?'ok':'fail',cameraControlLive(r)?`${val(r,'camera_servo_status','')} — commanded pulses, not position feedback`:`Camera control unavailable: ${val(r,'camera_servo_status','no heartbeat')}`,'camera_servo_status'],
  ['DALY BMS',recent(r,'bms_status',20)?'ok':'fail',recent(r,'bms_status',20)?'Battery telemetry live':'Check BMS Bluetooth connection','bms_status'],
  ['ORIN IO BASE',recent(r,'carrier_status',25)&&carrier.ok?'ok':'fail',carrier.ok?`${carrier.power_mode} • NVMe ${carrier.nvme.free_gb}GB free • ${carrier.usb_devices} USB devices`:'Carrier health service offline','carrier_status'],
  [`${cellGen} MODEM`,cellRegistered?'ok':recent(r,'cell_registration',20)?'warn':'fail',`Registration: ${val(r,'cell_registration','NO HEARTBEAT')} • signal report is not an Internet test`,'cell_registration','cellular'],
  ['VOICE USB',sys.voice_usb?'ok':'fail',sys.voice_usb?'ESP32-S3 enumerated; check voice service for response':(sys.voice_usb_reason||'Voice USB not enumerated'),null,'diagnostics'],
  ['GNSS',gpsCheck.fixed?'ok':gpsCheck.live?'warn':'fail',gpsCheck.fixed?'Current position fix valid':gpsCheck.live?'NMEA communication live, but NO position fix':'No fresh valid NMEA — open diagnostics','gps_diagnostics','gps'],
  ['WEB / TAILSCALE',net&&net.tailscale_ip!='--'?'ok':'warn',net&&net.tailscale_ip!='--'?`Reachable at ${net.tailscale_ip}`:'Tailscale address unavailable',null]
 ];
 let ok=items.filter(x=>x[1]=='ok').length,warn=items.filter(x=>x[1]=='warn').length,fail=items.filter(x=>x[1]=='fail').length;
 $('healthSummary').textContent=`${ok} OK / ${warn} WARN / ${fail} FAULT`;
 $('healthSummary').style.color=fail?'#ff4655':warn?'#ffcc3d':'#34e58b';
 let elapsed=(Date.now()-dashboardStarted)/1000;
 $('selfTestStamp').textContent=elapsed<8?`TELEMETRY CHECK • collecting messages for ${Math.ceil(8-elapsed)} more seconds`:`LIVE TELEMETRY ONLY • no physical motor test • ${items.length} channels • ${new Date().toLocaleTimeString()}`;
 let banner=$('bootBannerState');banner.textContent=elapsed<8?`RUNNING • ${Math.ceil(8-elapsed)}s • ${ok} LIVE`:`COMPLETE • ${ok} OK / ${warn} WARN / ${fail} FAULT`;banner.style.color=fail?'#ff4655':warn?'#ffcc3d':'#34e58b';
 $('healthGrid').innerHTML=items.map(x=>healthItem(x[0],x[1],x[2],x[3]?age(r,x[3]):null,x[4]||(x[3]?'telemetry:'+x[3]:'diagnostics'))).join('');
}
function renderConstellations(r){$('constellationGrid').innerHTML=diagnosticConstellations(r)}

function toast(t){let e=$('toast');e.textContent=t;e.style.display='block';clearTimeout(window.tt);window.tt=setTimeout(()=>e.style.display='none',2200)}
async function post(data,loud=true){try{let q=await fetch('/',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(data)});let j=await q.json();if(loud)toast(j.message||'done');return j}catch(e){if(loud)toast('CONTROL LINK LOST')}}
let latestStatus=null,activeDetail='';
function tile(label,value,unit=''){return `<div class="detailTile"><b>${label}</b><strong>${value}${unit}</strong></div>`}
function rangeTile(label,value,seconds){let mm=Number(value),valid=Number.isFinite(mm)&&mm>0&&seconds<4,pct=valid?Math.max(0,Math.min(100,mm/30)):0;return `<div class="detailTile"><b>${label}</b><strong>${valid?mm.toFixed(0)+' mm':'UNAVAILABLE'}</strong><div class="rangeBar"><div class="rangeFill" style="width:${pct}%"></div></div><div class="sensorHint">${valid?(mm<250?'NEAR':mm<500?'CAUTION':'VALID ECHO — not a driving clearance approval'):seconds>=4?'STALE / NOT INSTALLED':'NO VALID ECHO / NOT INSTALLED'} • age ${seconds<9999?seconds+'s':'--'}</div></div>`}
function heatCells(r){let t={};try{t=JSON.parse(val(r,'thermal_json','{}')||'{}')}catch(e){}let p=Array.isArray(t.pixels_c)?t.pixels_c:(Array.isArray(t.pixels)?t.pixels:[]),mn=Number(t.min_c),mx=Number(t.max_c);return `<div class="modalHeat">${Array.from({length:64},(_,i)=>{let v=Number(p[i]),q=Number.isFinite(v)?Math.max(0,Math.min(1,(v-mn)/Math.max(.2,mx-mn))):0;return `<i title="${Number.isFinite(v)?v.toFixed(1)+'°C':'--'}" style="background:${Number.isFinite(v)?`hsl(${220-q*220} 88% ${28+q*28}%)`:'#112436'}"></i>`}).join('')}</div><div class="detailGrid" style="margin-top:10px">${tile('MIN',n(t.min_c,1),'°C')}${tile('AVERAGE',n(t.avg_c,1),'°C')}${tile('MAX / HOTSPOT',n(t.max_c,1),'°C')}</div>`}
function cameraControlLive(r){return recent(r,'camera_servo_status',2)&&/^online /.test(String(val(r,'camera_servo_status','')))}
function i2cInfo(r){
 let raw=String(val(r,'i2c_status','')),pcaRaw=String(val(r,'pca_status','')),cameraRaw=String(val(r,'camera_servo_status','')),arduinoBus=(raw.match(/(?:^|,)BUS=([^,]*)/i)||[])[1]||'UNO R4 A4/A5',arduinoAddresses=raw.match(/0x[0-9a-f]{2}/gi)||[];
 arduinoAddresses=[...new Set(arduinoAddresses.map(x=>x.toUpperCase()))];
  let thermalLive=recent(r,'thermal_json',5)||recent(r,'thermal_status',5);
 let outsideLive=recent(r,'outside_temperature',9)||recent(r,'bme680_json',9)||recent(r,'outside_status',9);
 let pcaLive=(recent(r,'pca_status',5)&&(/pca=1|ACK,PCA,1|PCA=1/i.test(pcaRaw)))||cameraControlLive(r);
 let bridgeLive=(recent(r,'i2c_status',8)&&!/^offline/i.test(raw))||thermalLive||outsideLive||pcaLive;
  let sensors=[
   {name:'PCA9685 CAMERA',address:'0x40',live:pcaLive,key:pcaLive?'pca_status':'i2c_status'},
   {name:'AMG8833 8x8',address:'0x69',live:thermalLive,key:thermalLive?'thermal_json':'i2c_status'},
   {name:'BME680 AIR',address:'0x77',live:outsideLive,key:outsideLive?'outside_temperature':'i2c_status'}
  ];
 let liveSensors=sensors.filter(x=>x.live),freshest=liveSensors.map(x=>x.key).sort((a,b)=>age(r,a)-age(r,b))[0]||'i2c_status';
  return {raw,pcaRaw,cameraRaw,arduinoBus,arduinoAddresses,arduinoLive:recent(r,'i2c_status',8),bridgeLive,route:'UNO R4 USB/I2C hub',thermalLive,outsideLive,pcaLive,sensors,liveSensors,liveCount:liveSensors.length,freshestKey:freshest};
}
function renderDetail(){if(!activeDetail||!latestStatus)return;let r=latestStatus.ros,body='',title='LIVE SENSOR',fresh='LIVE';
 if(activeDetail==='ultrasonic'){title='FOUR ULTRASONIC SENSORS';body=`<div class="detailGrid">${rangeTile('LEFT',val(r,'us_left'),age(r,'us_left'))}${rangeTile('FRONT',val(r,'us_front'),age(r,'us_front'))}${rangeTile('RIGHT',val(r,'us_right'),age(r,'us_right'))}${rangeTile('REAR',val(r,'us_rear'),age(r,'us_rear'))}</div><div class="rawData">STATUS: ${val(r,'us_status','waiting')}\nREFRESH: latest received telemetry; measured callback rates are in Diagnostics\nROLE: secondary near-field safety layer; LiDAR remains the primary navigation sensor.</div>`;fresh=Math.max(age(r,'us_left'),age(r,'us_front'),age(r,'us_right'),age(r,'us_rear'))<3?'● LIVE':'STALE';}
 else if(activeDetail==='cellular'){title='CELLULAR / INTERNET DIAGNOSTICS';body=cellularDetails(r,latestStatus.network);fresh=recent(r,'cell_registration',20)?'● TELEMETRY LIVE':'STALE';}
 else if(activeDetail==='gps'){title='PRIMARY GNSS / GLONASS DIAGNOSTICS';body=gnssDetails(r);fresh=gnssInfo(r).live?'● NMEA LIVE':'STALE / OFFLINE';}
 else if(activeDetail.startsWith('telemetry:')){let key=activeDetail.slice(10),item=r[key];title='TELEMETRY — '+key;body='<pre class="rawData">'+diagEscape(JSON.stringify(item||{error:'not received'},null,2))+'</pre>';fresh=item&&item.age!==null&&item.age<10?'● RECENT':'OLDER / UNKNOWN';}
 else if(activeDetail==='camera'){title='IMX708 CAMERA — LIVE OUTPUT';let c=val(r,'camera_info',{});body=`<img id="modalCamera" class="modalCamera" src="/camera.jpg?latest=${Date.now()}"><div class="detailGrid" style="margin-top:10px">${tile('SOURCE',c.source||'--')}${tile('JPEG FRAME',c.bytes||'--',' bytes')}${tile('AGE',n(age(r,'camera_info'),1),' s')}</div><div class="rawData">AI: ${val(r,'ai_status','--')}\nMOTION: ${val(r,'motion_state','--')} (${n(val(r,'motion_percent'),1)}%)\nLATEST-FRAME MODE: old video frames are discarded instead of buffered.\nCamera processing remains single-source; this window does not start another detector.</div>`;fresh=age(r,'camera_info')<3?'● LIVE':'STALE';}
 else if(activeDetail==='radar'){title='RD-03D RADAR — ALL LIVE TARGETS';let targets=parseRadarTargets(val(r,'radar','')),link=String(val(r,'radar_link','--')),targetTiles=targets.length?targets.map(t=>`${tile(t.id+' POSITION',`X ${t.x} / Y ${t.y}`,' mm')}${tile(t.id+' DISTANCE',n(Math.hypot(t.x,t.y)/1000,2),' m')}${tile(t.id+' SPEED',`${t.speed>0?'+':''}${t.speed}`,' cm/s')}`).join(''):tile('TARGETS','0',' detected');body=`<div class="detailGrid">${tile('TARGET COUNT',targets.length)}${tile('NEAREST',n(val(r,'radar_dist'),0),' mm')}${tile('SAFETY ZONE',val(r,'radar_zone','--'))}${targetTiles}</div><div class="rawData">TRACKS: ${val(r,'radar','NO CURRENT TARGETS')}\nUART LINK: ${link}\nDECODER: ${val(r,'radar_decoder_status','--')}\nDATA AGE: ${n(age(r,'radar'),1)} s\n\nT1/T2/T3 are current radar slots, not permanent person identities. Position is radar-relative X/Y; speed sign follows the installed decoder convention.</div>`;fresh=age(r,'radar')<3?'● LIVE':'STALE';}
 else if(activeDetail==='encoders'){
  title='MOTOR ENCODERS — SELECTED FEEDBACK';
  let odom=val(r,'odom',{}),eh={};try{eh=JSON.parse(val(r,'encoder_health','{}')||'{}')}catch(e){}
  const selected=eh.selected_encoders||[],excluded=eh.excluded_encoders||[];
  const live=recent(r,'encoder_health',3)&&eh.packet_fresh===true;
  body=`<div class="detailGrid">${tile('SAFETY STATE',live?(eh.state||'MISSING'):'STALE')}${tile('SELECTED',selected.map(i=>'M'+i).join(', ')||'UNKNOWN')}${tile('EXCLUDED',excluded.map(i=>'M'+i).join(', ')||'NONE')}${tile('AUTONOMY',live&&eh.autonomy_ready===true?'FEEDBACK QUALIFIED':'BLOCKED / VALIDATION')}${tile('FAILED SELECTED CHANNELS',(eh.faults||[]).join(', ')||'NONE')}${tile('ENCODER PACKET AGE',n(eh.packet_age_s,3),' s')}${tile('M1 • BACK LEFT',val(r,'enc_m1'))}${tile('M2 • BACK RIGHT',val(r,'enc_m2'))}${tile('M3 • FRONT LEFT',val(r,'enc_m3'))}${tile(excluded.includes(4)?'M4 • EXCLUDED / RAW ONLY':'M4 • FRONT RIGHT',val(r,'enc_m4'))}${tile('LINEAR VELOCITY',n(odom.vx,3),' m/s')}${tile('YAW RATE',n(odom.wz,3),' rad/s')}${tile('ODOM X',n(odom.x,3),' m')}${tile('ODOM Y',n(odom.y,3),' m')}${tile('IMU HEADING',n(val(r,'imu_heading'),2),'°')}</div><div class="rawData">REASON: ${eh.reason||'waiting'}\nSAFETY HEARTBEAT AGE: ${n(age(r,'encoder_health'),1)} s\nLAST CHANGE AGE M1–M4: ${(eh.last_change_age_s||[]).join(' / ')||'--'} s\nPOLICY: ${eh.policy||'waiting'}\nSTEERING: front ${n(val(r,'front_steer'),1)}° • rear ${n(val(r,'rear_steer'),1)}°\n\nExclusion applies to encoder feedback, NOT the motor. M4 can still drive. A selected encoder fault or stale shared packet blocks autonomous use. Three healthy encoders can support autonomy after measured distance/turn validation. Fresh packets at rest do not prove individual encoder operation.</div>`;
  fresh=live?`● ${selected.length}/4 SELECTED — ${eh.state||'UNKNOWN'}`:'STALE / NO FEEDBACK';
 }
 else if(activeDetail==='lidar'){title='RPLIDAR — LIVE SCAN DETAILS';let li=val(r,'lidar',{});body=`<div class="detailGrid">${tile('NEAREST RETURN',n(li.nearest_m,3),' m')}${tile('VALID POINTS',li.points||0)}${tile('TOTAL SAMPLES',li.total||0)}${tile('MAX RANGE',n(li.range_max,1),' m')}${tile('FRAME',li.frame||'--')}${tile('DATA AGE',n(age(r,'lidar'),1),' s')}</div><div class="rawData">ROLE: PRIMARY obstacle geometry and navigation ranging.\nTOPIC: /scan\nThe dashboard summary does not modify, filter, or replace the LaserScan used by Nav2.</div>`;fresh=age(r,'lidar')<3?'● LIVE':'STALE';}
 else if(activeDetail==='imu'){title='HIWONDER IM10A — LIVE MONITORING';let f=val(r,'imu_full',{});body=`<div class="detailGrid">${tile('ROLL',n(val(r,'imu_roll'),2),'°')}${tile('PITCH',n(val(r,'imu_pitch'),2),'°')}${tile('SENSOR YAW',n(val(r,'imu_yaw'),2),'°')}${tile('ACCEL X',n(f.ax,3),' m/s²')}${tile('ACCEL Y',n(f.ay,3),' m/s²')}${tile('ACCEL Z',n(f.az,3),' m/s²')}${tile('GYRO X',n(f.gx,3),' rad/s')}${tile('GYRO Y',n(f.gy,3),' rad/s')}${tile('GYRO Z',n(f.gz,3),' rad/s')}${tile('MAG X RAW',n(f.mx_raw,2))}${tile('MAG Y RAW',n(f.my_raw,2))}${tile('MAG Z RAW',n(f.mz_raw,2))}</div><div class="rawData">SOURCE: ${f.source||'Hiwonder IM10A'}\nROLE: PRIMARY DISPLAY SOURCE — NAVIGATION NOT VALIDATED\nORIENTATION QUATERNION: x ${n(f.qx,5)}  y ${n(f.qy,5)}  z ${n(f.qz,5)}  w ${n(f.qw,5)}\nHEADING MODE: ${f.heading_reference_mode||'sensor heading; mounting unvalidated'}\nNAVIGATION FUSION: ${f.navigation_fusion||'disabled pending dynamic yaw validation'}\n\nThe magnetic values are sensor-native raw units; they are not mislabeled as µT.</div>`;fresh=age(r,'imu_full')<3?'● LIVE':'STALE';}
 else if(activeDetail==='thermal'){title='AMG8833 8×8 THERMAL ARRAY';let thermalLive=age(r,'thermal_json')<4;body=heatCells(r)+`<div class="rawData">${thermalLive?'STATUS: LIVE via UNO R4 I²C hub':val(r,'thermal_status','Thermal sensor waiting')}\nEach square is one live infrared temperature pixel. Brightest square is the current hotspot.</div>`;fresh=thermalLive?'● LIVE':'STALE';}
 else if(activeDetail==='environment'){title='BME680 OUTSIDE AIR / GAS';let j={};try{j=JSON.parse(val(r,'bme680_json','{}')||'{}')}catch(e){}body=`<div class="detailGrid">${tile('TEMPERATURE',n(val(r,'outside_temperature'),2),'°C')}${tile('HUMIDITY',n(val(r,'outside_humidity'),1),'% RH')}${tile('PRESSURE',n(val(r,'outside_pressure'),1),' hPa')}${tile('GAS RESISTANCE',n(Number(val(r,'outside_gas'))/1000,1),' kΩ')}${tile('IAQ ESTIMATE',n(j.iaq,0))}${tile('HEATER',j.heat_stable?'STABLE':'WARMING')}</div><div class="rawData">STATUS: ${val(r,'outside_status','waiting')}\nGas resistance is a relative VOC/air-quality signal, not a calibrated safety alarm. Compare its trend and IAQ estimate after the heater becomes stable.</div>`;fresh=age(r,'outside_gas')<8?'● LIVE':'STALE';}
 else if(activeDetail==='i2c'){title='ATLAS I²C ROUTES — LIVE INVENTORY';let q=i2cInfo(r),sensorText=q.sensors.map(x=>`${x.live?'LIVE   ':'OFFLINE'} ${x.name}  ${x.address}`).join('\n'),arduinoText=q.arduinoAddresses.length?q.arduinoAddresses.join(', '):'not present in latest status frame';body=`<div class="detailGrid">${tile('UNO R4 I2C HUB',q.liveCount+'/3 LIVE')}${tile('PCA9685',q.pcaLive?'0x40 LIVE':'OFFLINE')}${tile('AMG8833',q.thermalLive?'0x69 LIVE':'OFFLINE')}${tile('BME680',q.outsideLive?'0x77 LIVE':'OFFLINE')}${tile('USB BRIDGE',q.bridgeLive?'ONLINE':'OFFLINE')}</div><div class="rawData">LIVE SENSOR ROUTE: Jetson USB → UNO R4 → I²C A4/A5\n${sensorText}\n\nIM10A ROUTE: dedicated USB → atlas-im10a → /im10a/* (EKF fusion disabled)\n\nI²C STATUS:\n${q.raw||'waiting for /arduino/i2c/status'}\nPCA STATUS:\n${q.pcaRaw||q.cameraRaw||'waiting for PCA9685 feedback'}\nSCANNED ADDRESSES: ${arduinoText}\n\nEach LIVE/OFFLINE result is calculated from that sensor's own fresh ROS data. One failed sensor no longer hides the working sensors.</div>`;fresh=q.liveCount?`● ${q.liveCount}/3 LIVE`:(q.bridgeLive?'● BRIDGE ONLY':'STALE');}
 $('detailTitle').textContent=title;$('detailFresh').textContent=fresh;$('detailFresh').style.color=fresh.includes('LIVE')?'#34e58b':'#ff4655';$('detailBody').innerHTML=body;
}
function openDetail(key){if(key==='diagnostics'){$('diagnosticsPanel').open=true;$('diagnosticsPanel').scrollIntoView({behavior:'smooth'});refreshDiagnostics(true);return}activeDetail=key;$('sensorModal').classList.add('open');renderDetail()}
function closeDetail(){activeDetail='';$('sensorModal').classList.remove('open');$('detailBody').innerHTML=''}
$('sensorModal').addEventListener('click',e=>{if(e.target===$('sensorModal'))closeDetail()});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDetail()});
async function stop(){await post({action:'stop'},false)}
let hold=null;function beginDrive(b){stopDrive(false);b.classList.add('on');let send=()=>post({action:'drive',linear:b.dataset.l,angular:b.dataset.a},false);send();hold=setInterval(send,120)}
function stopDrive(send=true){if(hold){clearInterval(hold);hold=null}document.querySelectorAll('[data-l]').forEach(b=>b.classList.remove('on'));if(send)stop()}
document.querySelectorAll('[data-l]').forEach(b=>{b.onpointerdown=e=>{e.preventDefault();b.setPointerCapture(e.pointerId);beginDrive(b)};b.onpointerup=()=>stopDrive();b.onpointercancel=()=>stopDrive();b.onlostpointercapture=()=>stopDrive()});
$('stop').onclick=()=>post({action:'e_stop'});window.addEventListener('blur',()=>stopDrive());document.addEventListener('visibilitychange',()=>{if(document.hidden)stopDrive()});
let cameraHold=null,cameraBusy=false;
function stopCameraHold(){if(cameraHold){clearInterval(cameraHold);cameraHold=null}document.querySelectorAll('[data-cam]').forEach(b=>b.classList.remove('on'))}
async function cameraStep(b){if(cameraBusy)return;cameraBusy=true;try{await post({action:'camera',axis:b.dataset.cam,direction:b.dataset.dir})}finally{cameraBusy=false}}
document.querySelectorAll('[data-cam]').forEach(b=>{b.onpointerdown=e=>{e.preventDefault();stopCameraHold();b.classList.add('on');b.setPointerCapture(e.pointerId);cameraStep(b);if(b.dataset.cam!=='center')cameraHold=setInterval(()=>cameraStep(b),90)};b.onpointerup=stopCameraHold;b.onpointercancel=stopCameraHold;b.onlostpointercapture=stopCameraHold});
window.addEventListener('pointerup',stopCameraHold);window.addEventListener('pointercancel',stopCameraHold);window.addEventListener('blur',stopCameraHold);document.addEventListener('visibilitychange',()=>{if(document.hidden)stopCameraHold()});
document.querySelectorAll('[data-track]').forEach(b=>b.onclick=()=>post({action:'camera_tracking',enabled:b.dataset.track}));
document.querySelectorAll('[data-ai]').forEach(b=>b.onclick=()=>post({action:'ai_mode',mode:b.dataset.ai}));
let cameraFrameBusy=false,cameraRequestStarted=0,cameraLastSuccess=0,cameraGeneration=0,cameraFailures=0;
function cameraState(text,state){let e=$('cameraStatus');if(!e)return;e.textContent=text;e.className=`cameraStatus ${state}`}
function pollLatestCameraFrame(force=false){
 if(document.hidden)return;
 let now=Date.now();
 // A request that never fires load/error previously froze this loop forever.
 // Expire it and start a newer generation; a late response cannot overwrite it.
 if(cameraFrameBusy&&!force&&now-cameraRequestStarted<2200)return;
 cameraFrameBusy=true;cameraRequestStarted=now;let generation=++cameraGeneration,next=new Image();next.decoding='async';
 let timer=setTimeout(()=>{if(generation!==cameraGeneration)return;cameraFrameBusy=false;cameraFailures++;cameraState('RECOVERING STREAM','warn');pollLatestCameraFrame(true)},2400);
 next.onload=()=>{if(generation!==cameraGeneration)return;clearTimeout(timer);let main=$('camera'),modal=$('modalCamera');if(main)main.src=next.src;if(modal)modal.src=next.src;cameraFrameBusy=false;cameraLastSuccess=Date.now();cameraFailures=0;cameraState('LIVE • AUTO REFRESH','ok')};
 next.onerror=()=>{if(generation!==cameraGeneration)return;clearTimeout(timer);cameraFrameBusy=false;cameraFailures++;cameraState(cameraFailures>3?'CAMERA OFFLINE':'RECONNECTING','fail')};
 next.src='/camera.jpg?latest='+now+'&generation='+generation;
}
setInterval(()=>pollLatestCameraFrame(false),125);
setInterval(()=>{let now=Date.now();if(!document.hidden&&now-cameraLastSuccess>3000&&(!cameraFrameBusy||now-cameraRequestStarted>2400))pollLatestCameraFrame(true)},1000);
window.addEventListener('online',()=>pollLatestCameraFrame(true));window.addEventListener('focus',()=>pollLatestCameraFrame(true));
document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollLatestCameraFrame(true)});pollLatestCameraFrame(true);
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
 $('companionPrivacy').textContent=age(r,'companion_privacy')<12?val(r,'companion_privacy','Unknown'):'VOICE PRIVACY STATUS STALE — do not assume the microphone is muted';
 $('companionAlert').textContent='LATEST ANNOUNCEMENT: '+val(r,'companion_alert','None');
 if(age(r,'companion_state')>=12){$('companionState').textContent='VOICE SERVICE STALE / POSSIBLY IN CALL'}
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
async function voiceMute(muted){try{let res=await fetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json','X-Atlas-Wifi':'1'},body:JSON.stringify({muted})}),d=await res.json();$('companionPrivacy').textContent=d.message}catch(e){$('companionPrivacy').textContent='Mute request failed. Current microphone state is unknown.'}}
async function refresh(){try{let d=await fetch('/api/status',{cache:'no-store'}).then(x=>x.json()),r=d.ros,net=d.network,s=d.system;latestStatus=d;
 updateBatteryBadge(r);
 let cellGen=cellGeneration(val(r,'cell_tech',''));
 renderHealth(r,net);
 companion(r,s);
 $('online').textContent='● ONLINE';$('online').style.color='#34e58b';
 $('ai').textContent=val(r,'ai_status','AI waiting');
 let cameraTracking=String(val(r,'camera_tracking_status','MANUAL CONTROL'));
 $('cameraTracking').textContent=cameraTracking;
 let trackingOn=/^(ON:|TRACKING|SEARCHING)/i.test(cameraTracking);
 document.querySelectorAll('[data-track]').forEach(b=>b.classList.toggle('on',(b.dataset.track==='1')===trackingOn));
 $('motion').innerHTML=row('Web drive',val(r,'web_drive','STOP'))+row('Odometry',JSON.stringify(val(r,'odom',{})))+row('Encoders',`${val(r,'enc_m1')} / ${val(r,'enc_m2')} / ${val(r,'enc_m3')} / ${val(r,'enc_m4')}`);
 let li=val(r,'lidar',{}),radarLive=!!r.radar_count&&r.radar_count.age<2.0,radarHub=!!r.radar_link&&r.radar_link.age<3.0,i2c=i2cInfo(r);
 let radarTitle=radarLive?`${val(r,'radar_count')} targets`:(radarHub?'UART INVALID':'OFFLINE');
 let radarDetail=radarLive?`${n(val(r,'radar_dist'),0)} mm • ${val(r,'radar_zone')} • X ${n(val(r,'radar_x'),0)} Y ${n(val(r,'radar_y'),0)} • ${n(val(r,'radar_speed'),0)} cm/s`:(radarHub?String(val(r,'radar_decoder_status','Bytes received; no valid frame')):'Check power/GND • radar TX → UNO D12 • radar RX → UNO D11');
 let imuLive=recent(r,'imu_full',4)||recent(r,'imu_heading',4);
 $('sensors').innerHTML=card('LiDAR',`${n(li.nearest_m,2)} m`,`${li.points||0} points`,'lidar')+card('Ultrasonic',`${val(r,'us_front')} mm`,`L ${val(r,'us_left')} • R ${val(r,'us_right')} • B ${val(r,'us_rear')}`,'ultrasonic')+card('RD-03D Radar',radarTitle,radarDetail,'radar')+card('Hiwonder IM10A',imuLive?`${n(val(r,'imu_yaw'),0)}° SENSOR`:'OFFLINE',imuLive?`MONITORING • roll ${n(val(r,'imu_roll'))} pitch ${n(val(r,'imu_pitch'))}`:'Check IM10A USB connection and atlas-im10a service','imu')+card('I²C Sensor Bus',i2c.liveCount?`${i2c.liveCount}/3 LIVE`:(i2c.bridgeLive?'BRIDGE ONLY':'OFFLINE'),i2c.liveCount?`${i2c.route} • ${i2c.liveSensors.map(x=>x.address).join(' • ')}`:(i2c.bridgeLive?'UNO R4 live; sensor data stale':'No fresh sensor telemetry'),'i2c');
 $('power').innerHTML=card('Main BMS',`${n(val(r,'bms_percent'),0)}%`,`${n(val(r,'bms_voltage'),2)}V ${n(val(r,'bms_current'),2)}A ${n(val(r,'bms_power'),1)}W • CELLS ${n(val(r,'bms_cell1'),3)} / ${n(val(r,'bms_cell2'),3)} / ${n(val(r,'bms_cell3'),3)} / ${n(val(r,'bms_cell4'),3)}`)+card('Motor board',`${n(val(r,'bat_voltage'),2)}V`,'Current NOT MEASURED • driver publishes a placeholder','telemetry:bat_current')+card('Jetson INA3221',`${n(val(r,'jetson_power'),1)}W`,`${n(val(r,'jetson_voltage'),3)}V ${n(val(r,'jetson_current'),2)}A • CPU/GPU ${n(val(r,'jetson_cpu_gpu_power'),1)}W • SoC ${n(val(r,'jetson_soc_power'),1)}W`)+card(`${cellGen} MODEM`,val(r,'cell_registration','--'),`${n(val(r,'cell_signal'),0)}% reported signal • not an Internet test`,'cellular');
 environment(r);
 $('network').innerHTML=row('Wi-Fi / AP',net.wifi_ip)+row(`${cellGen} data`,`${net.cell_ip} • ${val(r,'cell_operator','--')} • ${n(val(r,'cell_signal'),0)}%`)+row('Tailscale',net.tailscale_ip)+row('Active route',net.route)+networkFallbackSummary(net)+`<button class="btn" onclick="openDetail('cellular')">CELLULAR / ROUTE DETAILS</button><a class="btn" href="/wifi">WI-FI SETUP / SAVED NETWORKS</a>`;
 $('gnss').innerHTML=gnssSummary(r);renderConstellations(r);renderDiagnostics();refreshDiagnostics();
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
