#!/usr/bin/env python3
"""Bounded Project ATLAS fault diagnosis and safe peripheral recovery.

This node never publishes velocity, servo, navigation-goal, or mission commands.
Motor control and Nav2 are diagnosis-only because restarting either while the
rover may be moving is unsafe. Peripheral restarts are serialized, rate-limited,
and stop after repeated failures so hardware faults cannot create restart loops.
"""

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Imu, LaserScan, NavSatFix
from std_msgs.msg import Float32, Int32, String


@dataclass(frozen=True)
class Monitor:
    name: str
    topic: str
    msg_type: object
    stale_after: float
    service: str | None
    recover: bool = True
    required: bool = True
    stopped_only: bool = False


GNSS_ENABLED = os.environ.get("ATLAS_GNSS_ENABLED", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
ULTRASONIC_ENABLED = os.environ.get(
    "ATLAS_ULTRASONIC_ENABLED", "1"
).strip().lower() not in ("0", "false", "no", "off")

MONITORS = tuple(item for item in (
    Monitor("lidar", "/scan", LaserScan, 5.0, "atlas-lidar.service"),
    Monitor("camera", "/camera/image_raw/compressed", CompressedImage, 8.0,
            "atlas-camera.service"),
    # The Mega is the single owner for several shared-bus sensors. Restarting
    # its CH340 serial service can hardware-reset only the Mega while its I2C
    # peripherals remain powered, turning one stale topic into a complete bus
    # outage. The Mega firmware performs bounded bus recovery internally;
    # systemd still restarts the bridge if the process genuinely crashes.
    Monitor("imu", "/imu/data", Imu, 5.0,
            "atlas-mega-sensor-hub.service", recover=False),
    Monitor("radar", "/radar/targets", String, 8.0, "rover-radar.service"),
    Monitor("ultrasonic", "/ultrasonic/status", String, 8.0,
            "atlas-mega-sensor-hub.service", recover=False),
    Monitor("thermal", "/thermal/amg8833/status", String, 10.0,
            "atlas-mega-sensor-hub.service", recover=False),
    # The ambient sensor is currently being replaced. Diagnose bad/stale data,
    # but do not create restart loops while the BME680 is electrically absent.
    Monitor("ambient", "/environment/outside_status", String, 10.0,
            "atlas-mega-sensor-hub.service", recover=False),
    # cellular_telemetry is the single GPS owner. A missing fix is diagnostic;
    # starting the legacy atlas-gnss unit would create a duplicate publisher.
    Monitor("gps", "/gps/fix", NavSatFix, 12.0, None, recover=False),
    Monitor("bms", "/bms/status", String, 15.0, "rover-daly-bms.service"),
    # Never restart the network path from which a remote operator may be
    # connected. Report it and let the operator approve network recovery.
    Monitor("cellular", "/cellular/registration", String, 20.0,
            "rover-cellular.service", recover=False, required=False),
    # Fused odometry may recover automatically only while the rover is
    # stationary. The user-managed EKF has no motor authority.
    Monitor("odometry", "/odom", Odometry, 5.0,
            "atlas-ekf.service", recover=True, stopped_only=True),
    # Raw wheel odometry belongs to the motor-base process. Restarting that
    # process is deliberately diagnosis-only because it owns locomotion I/O.
    Monitor("wheel_odometry", "/yahboom/odom", Odometry, 5.0,
            "rover-base-telemetry.service", recover=False),
    Monitor("encoder_fl", "/yahboom/encoder/m1", Int32, 6.0,
            "rover-base-telemetry.service", recover=False),
    Monitor("map", "/map", OccupancyGrid, 20.0,
            "atlas-slam-fast.service", recover=False, required=False),
) if (GNSS_ENABLED or item.name != "gps")
   and (ULTRASONIC_ENABLED or item.name != "ultrasonic"))

BAD_WORDS = (
    "offline", "error", "failed", "fault", "disconnected", "not found",
    "remote i/o", "no device", "unavailable",
)
STARTUP_GRACE = 30.0
COOLDOWN = 60.0
ATTEMPT_WINDOW = 600.0
MAX_ATTEMPTS = 3
RECOVERY_CONFIRM_TIMEOUT = 25.0


class AtlasRecovery(Node):
    def __init__(self):
        super().__init__("atlas_sensor_recovery")
        now = time.monotonic()
        self.started = now
        self.last_seen = {item.name: now for item in MONITORS}
        self.last_value = {item.name: "waiting" for item in MONITORS}
        self.attempts = {item.name: [] for item in MONITORS}
        self.last_notice = {item.name: 0.0 for item in MONITORS}
        self.recovering = set()
        self.lock = threading.Lock()
        self.service_cache = {}
        self.motion_last_seen = now
        self.motion_active = False
        self.status_pub = self.create_publisher(
            String, "/atlas/recovery_status", 10
        )
        self.state_pub = self.create_publisher(
            String, "/atlas/recovery_state", 10
        )
        for item in MONITORS:
            self.create_subscription(
                item.msg_type,
                item.topic,
                lambda msg, name=item.name: self.on_message(name, msg),
                10,
            )
        self.create_subscription(Twist, "/cmd_vel", self.on_velocity, 10)
        self.create_timer(2.0, self.check)
        self.create_timer(5.0, self.publish_state)
        suffix = (
            "; ultrasonic intentionally disabled; LiDAR primary"
            if not ULTRASONIC_ENABLED else ""
        )
        self.publish_status("READY: full bounded fault recovery armed" + suffix)

    def publish_status(self, text):
        self.status_pub.publish(String(data=text))
        self.get_logger().info(text)

    def on_velocity(self, msg):
        self.motion_last_seen = time.monotonic()
        self.motion_active = (
            abs(msg.linear.x) > 0.01
            or abs(msg.linear.y) > 0.01
            or abs(msg.angular.z) > 0.01
        )

    def on_message(self, name, msg):
        now = time.monotonic()
        self.last_seen[name] = now
        if isinstance(msg, String):
            value = msg.data.strip()[:240]
        elif isinstance(msg, NavSatFix):
            value = f"status={msg.status.status} lat={msg.latitude:.6f} lon={msg.longitude:.6f}"
        else:
            value = "data received"
        self.last_value[name] = value
        # Sustained healthy data clears the old retry budget.
        if self.attempts[name] and now - self.attempts[name][-1] > ATTEMPT_WINDOW:
            self.attempts[name] = []

    def service_active(self, service):
        if not service:
            return True
        now = time.monotonic()
        cached = self.service_cache.get(service)
        if cached and now - cached[0] < 4.0:
            return cached[1]
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", service],
            timeout=5,
            check=False,
        )
        active = result.returncode == 0
        self.service_cache[service] = (now, active)
        return active

    def bad_status(self, name):
        value = self.last_value[name].lower()
        return any(word in value for word in BAD_WORDS)

    def schedule_recovery(self, item, reason):
        now = time.monotonic()
        if item.stopped_only and self.motion_active:
            if now - self.last_notice[item.name] >= COOLDOWN:
                self.last_notice[item.name] = now
                self.publish_status(
                    f"STOP REQUIRED: {item.name} {reason}; automatic restart "
                    "is inhibited while motion is active"
                )
            return
        with self.lock:
            recent = [stamp for stamp in self.attempts[item.name]
                      if now - stamp < ATTEMPT_WINDOW]
            self.attempts[item.name] = recent
            if item.name in self.recovering:
                return
            if recent and now - recent[-1] < COOLDOWN:
                return
            if len(recent) >= MAX_ATTEMPTS:
                if now - self.last_notice[item.name] >= COOLDOWN:
                    self.last_notice[item.name] = now
                    self.publish_status(
                        f"HARDWARE ATTENTION: {item.name} still faulty after "
                        f"{MAX_ATTEMPTS} bounded recoveries; check power, cable, and device"
                    )
                return
            self.attempts[item.name].append(now)
            self.recovering.add(item.name)
        thread = threading.Thread(
            target=self.recover, args=(item, reason), daemon=True
        )
        thread.start()

    def recover(self, item, reason):
        try:
            # Most peripheral recovery is allowed while stationary or moving
            # because the command watchdog remains authoritative. Components
            # marked stopped_only are gated before this worker is scheduled.
            attempt = len(self.attempts[item.name])
            self.publish_status(
                f"RECOVERING: {item.name} ({reason}); restarting "
                f"{item.service}, attempt {attempt}/{MAX_ATTEMPTS}"
            )
            subprocess.run(
                ["systemctl", "--user", "restart", item.service],
                timeout=15,
                check=True,
            )
            self.service_cache.pop(item.service, None)
            deadline = time.monotonic() + RECOVERY_CONFIRM_TIMEOUT
            baseline = time.monotonic()
            while time.monotonic() < deadline:
                if self.last_seen[item.name] >= baseline and not self.bad_status(item.name):
                    self.publish_status(f"RECOVERED: {item.name} data is healthy")
                    return
                time.sleep(1.0)
            self.publish_status(
                f"RECOVERY INCOMPLETE: {item.name}; hardware inspection may be required"
            )
        except Exception as exc:
            self.publish_status(
                f"RECOVERY FAILED: {item.name}; {type(exc).__name__}: {exc}"
            )
        finally:
            with self.lock:
                self.recovering.discard(item.name)

    def classify(self, item, now):
        age = now - self.last_seen[item.name]
        if self.bad_status(item.name):
            return "FAULT", age, self.last_value[item.name]
        if age > item.stale_after:
            return "STALE", age, f"no data for {age:.1f}s"
        if item.name == "gps" and self.last_value[item.name].startswith("status=-1"):
            return "NO_FIX", age, "receiver online; waiting for satellite fix"
        if item.service and not self.service_active(item.service):
            return "SERVICE_DOWN", age, f"{item.service} inactive"
        return "HEALTHY", age, self.last_value[item.name]

    def check(self):
        now = time.monotonic()
        if now - self.started < STARTUP_GRACE:
            return
        for item in MONITORS:
            state, age, detail = self.classify(item, now)
            if state == "HEALTHY":
                continue
            reason = f"{state.lower()}: {detail}"
            if item.recover and item.service:
                self.schedule_recovery(item, reason)
            elif item.required:
                if now - self.last_notice[item.name] >= COOLDOWN:
                    self.last_notice[item.name] = now
                    self.publish_status(
                        f"DIAGNOSIS ONLY: {item.name} {reason}; operator inspection required"
                    )

    def publish_state(self):
        now = time.monotonic()
        systems = {}
        for item in MONITORS:
            state, age, detail = self.classify(item, now)
            systems[item.name] = {
                "state": state,
                "age_s": round(age, 1),
                "detail": detail,
                "auto_recovery": bool(item.recover),
                "attempts": len([
                    stamp for stamp in self.attempts[item.name]
                    if now - stamp < ATTEMPT_WINDOW
                ]),
            }
        overall = "HEALTHY"
        required_states = [
            systems[item.name]["state"] for item in MONITORS if item.required
        ]
        if any(state == "FAULT" for state in required_states):
            overall = "FAULT"
        elif any(state in ("STALE", "SERVICE_DOWN", "NO_FIX") for state in required_states):
            overall = "DEGRADED"
        payload = {
            "overall": overall,
            "motion_active": self.motion_active,
            "recovering": sorted(self.recovering),
            "systems": systems,
        }
        self.state_pub.publish(
            String(data=json.dumps(payload, separators=(",", ":")))
        )


def main():
    rclpy.init()
    node = AtlasRecovery()
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
