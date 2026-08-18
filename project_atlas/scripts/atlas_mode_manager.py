#!/usr/bin/env python3
"""Deterministic mutually-exclusive operating modes for Project ATLAS.

This node never starts exploration or sends a navigation goal. It only
transitions the supporting SLAM/localization/Nav2 services while publishing
zero Nav2 velocity before and after every transition.
"""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
from threading import Lock

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


class AtlasModeManager(Node):
    MODES = {"IDLE", "MAPPING", "LOCALIZATION", "FAILED"}

    def __init__(self):
        super().__init__("atlas_mode_manager")
        self.declare_parameter(
            "map_file", "/home/jetson/project_atlas/maps/atlas_latest.yaml"
        )
        self.state_file = Path.home() / ".config/project_atlas/operating_mode.json"
        self.seed_pose_file = (
            Path.home() / ".config/project_atlas/localization_seed_pose.json"
        )
        self.map_file = Path(str(self.get_parameter("map_file").value))
        self.lock = Lock()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="atlas-mode")
        self.mode_pub = self.create_publisher(String, "/atlas/mode", 10)
        self.detail_pub = self.create_publisher(String, "/atlas/mode/detail", 10)
        self.zero_pub = self.create_publisher(Twist, "/cmd_vel_nav", 10)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.mode = self.detect_mode()
        self.detail = "Observed existing service state; no transition performed"
        self.create_service(Trigger, "/atlas/mode/idle", self.request_idle)
        self.create_service(Trigger, "/atlas/mode/mapping", self.request_mapping)
        self.create_service(
            Trigger, "/atlas/mode/localization", self.request_localization
        )
        self.create_service(Trigger, "/atlas/mode/status", self.request_status)
        self.create_timer(1.0, self.publish)
        self.create_timer(2.0, self.reconcile_observed_mode)
        self.record()
        self.get_logger().info(f"Mode manager ready in observed mode {self.mode}")

    @staticmethod
    def unit_active(unit):
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", unit],
            check=False,
            timeout=4,
        )
        return result.returncode == 0

    def detect_mode(self):
        if self.unit_active("atlas-localization.service"):
            return "LOCALIZATION"
        if self.unit_active("atlas-slam-fast.service") and self.unit_active(
            "atlas-nav2.service"
        ):
            return "MAPPING"
        return "IDLE"

    def publish(self):
        self.mode_pub.publish(String(data=self.mode))
        self.detail_pub.publish(String(data=self.detail))

    def reconcile_observed_mode(self):
        """Correct boot-time service races without disturbing transitions."""
        if self.lock.locked() or self.mode == "FAILED":
            return
        observed = self.detect_mode()
        if observed == self.mode:
            return
        self.mode = observed
        self.detail = f"Reconciled live service state after startup: {observed}"
        self.record()
        self.get_logger().info(f"Observed operating mode reconciled to {observed}")

    def record(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"mode": self.mode, "detail": self.detail}, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_file)

    def set_state(self, mode, detail):
        if mode not in self.MODES:
            raise ValueError(f"unsupported mode: {mode}")
        self.mode = mode
        self.detail = detail
        self.record()
        self.publish()
        self.get_logger().info(f"{mode}: {detail}")

    def systemctl(self, action, *units, timeout=35):
        result = subprocess.run(
            ["systemctl", "--user", action, *units],
            check=False,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                result.stderr.strip() or result.stdout.strip() or
                f"systemctl {action} failed for {', '.join(units)}"
            )

    def zero(self):
        try:
            if rclpy.ok():
                self.zero_pub.publish(Twist())
        except Exception as exc:
            self.get_logger().debug(f"zero publish skipped during shutdown: {exc}")

    def save_localization_seed(self):
        # A map->base_link transform from an incomplete mapping/Nav2 stack may
        # merely be its temporary (0, 0) origin. Only trust a live transform
        # when ATLAS is already in the verified saved-map localization mode.
        trust_live_pose = (
            (
                self.mode == "LOCALIZATION"
                and self.unit_active("atlas-localization.service")
            )
            or (
                self.mode == "MAPPING"
                and self.unit_active("atlas-slam-fast.service")
                and self.unit_active("atlas-nav2.service")
            )
        )
        try:
            if not trust_live_pose:
                raise RuntimeError("live pose is not from localization mode")
            transform = self.tf_buffer.lookup_transform(
                "map", "base_link", Time(), timeout=Duration(seconds=2.0)
            )
            pose = {
                "frame_id": "map",
                "x": transform.transform.translation.x,
                "y": transform.transform.translation.y,
                "z": transform.transform.translation.z,
                "qx": transform.transform.rotation.x,
                "qy": transform.transform.rotation.y,
                "qz": transform.transform.rotation.z,
                "qw": transform.transform.rotation.w,
            }
        except Exception:
            fallback_files = (
                self.seed_pose_file,
                Path.home() / ".config/project_atlas/home_pose.json",
            )
            fallback = next((path for path in fallback_files if path.exists()), None)
            if fallback is None:
                raise RuntimeError("no live map pose or saved localization seed")
            pose = json.loads(fallback.read_text(encoding="utf-8"))
            if pose.get("frame_id") != "map":
                raise RuntimeError("saved localization seed is not in map frame")
        self.seed_pose_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.seed_pose_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(pose, indent=2), encoding="utf-8")
        temporary.replace(self.seed_pose_file)
        return pose

    def transition(self, target):
        if not self.lock.acquire(blocking=False):
            self.set_state(self.mode, f"BUSY: ignored transition to {target}")
            return
        try:
            self.zero()
            if target == "IDLE":
                self.systemctl(
                    "stop",
                    "atlas-explore.service",
                    "atlas-localization.service",
                    "atlas-nav2.service",
                    "atlas-slam-fast.service",
                )
                self.set_state("IDLE", "Autonomy support stacks stopped safely")
            elif target == "MAPPING":
                self.systemctl(
                    "stop", "atlas-explore.service", "atlas-localization.service"
                )
                self.systemctl(
                    "start", "atlas-slam-fast.service", "atlas-nav2.service"
                )
                if not (
                    self.unit_active("atlas-slam-fast.service")
                    and self.unit_active("atlas-nav2.service")
                ):
                    raise RuntimeError("mapping stack did not become active")
                self.set_state(
                    "MAPPING", "SLAM and Nav2 ready; exploration remains stopped"
                )
            elif target == "LOCALIZATION":
                if not self.map_file.exists():
                    raise RuntimeError(f"saved map is missing: {self.map_file}")
                seed = self.save_localization_seed()
                self.systemctl(
                    "stop",
                    "atlas-explore.service",
                    "atlas-nav2.service",
                    "atlas-slam-fast.service",
                )
                self.systemctl("start", "atlas-localization.service")
                if not self.unit_active("atlas-localization.service"):
                    raise RuntimeError("localization stack did not become active")
                result = subprocess.run(
                    [
                        "/usr/bin/python3",
                        "/home/jetson/project_atlas/scripts/seed_atlas_localization.py",
                    ],
                    check=False, timeout=30, capture_output=True, text=True,
                )
                if result.returncode:
                    raise RuntimeError(
                        result.stderr.strip() or result.stdout.strip() or
                        "AMCL localization seed failed"
                    )
                self.set_state(
                    "LOCALIZATION",
                    "Saved map, AMCL and Nav2 active; seeded at "
                    f"x={seed['x']:.2f} y={seed['y']:.2f}",
                )
            else:
                raise ValueError(f"unsupported transition target: {target}")
        except Exception as exc:
            self.zero()
            self.set_state("FAILED", f"Transition to {target} failed: {exc}")
        finally:
            self.zero()
            self.lock.release()

    def submit(self, target):
        self.worker.submit(self.transition, target)

    def response(self, response, target):
        self.submit(target)
        response.success = True
        response.message = f"transition to {target} queued"
        return response

    def request_idle(self, _request, response):
        return self.response(response, "IDLE")

    def request_mapping(self, _request, response):
        return self.response(response, "MAPPING")

    def request_localization(self, _request, response):
        return self.response(response, "LOCALIZATION")

    def request_status(self, _request, response):
        observed = self.detect_mode()
        response.success = self.mode != "FAILED"
        response.message = f"reported={self.mode} observed={observed}: {self.detail}"
        return response

    def destroy_node(self):
        self.zero()
        self.worker.shutdown(wait=False, cancel_futures=True)
        return super().destroy_node()


def main():
    rclpy.init()
    node = AtlasModeManager()
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
