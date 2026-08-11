#!/usr/bin/env python3
"""Non-blocking Foxglove mission bindings for Project ATLAS."""

from concurrent.futures import ThreadPoolExecutor
import json
import math
import subprocess
import time
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

import rclpy
from action_msgs.srv import CancelGoal
from geometry_msgs.msg import PoseStamped, Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Empty, Int32, String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


class AtlasMissionControl(Node):
    """Expose topic and service controls without blocking the ROS executor."""

    MAPPING_BACKGROUND_UNITS = (
        "atlas-camera-tracker.service",
        "atlas-follow-person.service",
        "atlas-foxglove.service",
        "atlas-voice-companion.service",
    )

    def __init__(self):
        super().__init__("atlas_mission_control")
        self.declare_parameter(
            "map_prefix", "/home/jetson/project_atlas/maps/atlas_latest"
        )
        self.declare_parameter("explore_unit", "atlas-explore.service")
        self.declare_parameter("home_verify_delay", 2.0)
        self.declare_parameter("home_verify_tolerance", 0.15)
        self.declare_parameter("home_max_retries", 1)
        self.home_file = Path.home() / ".config/project_atlas/home_pose.json"
        self.localization_seed_file = (
            Path.home() / ".config/project_atlas/localization_seed_pose.json"
        )
        self.places_file = Path.home() / ".config/project_atlas/named_places.json"
        self.map_prefix = Path(str(self.get_parameter("map_prefix").value))
        self.map_prefix.parent.mkdir(parents=True, exist_ok=True)
        self.explore_unit = str(self.get_parameter("explore_unit").value)
        self.home_verify_delay = float(
            self.get_parameter("home_verify_delay").value
        )
        self.home_verify_tolerance = float(
            self.get_parameter("home_verify_tolerance").value
        )
        self.home_max_retries = int(
            self.get_parameter("home_max_retries").value
        )
        self.paused_services_file = (
            Path.home() / ".config/project_atlas/mapping_paused_services.json"
        )

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.nav = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        self.cancel_nav = self.create_client(
            CancelGoal, "/navigate_to_pose/_action/cancel_goal"
        )
        self.zero_pub = self.create_publisher(Twist, "/cmd_vel_nav", 10)
        self.camera_pan_pub = self.create_publisher(
            Int32, "/camera/bottom_servo_cmd_us", 10
        )
        self.camera_tilt_pub = self.create_publisher(
            Int32, "/camera/second_servo_cmd_us", 10
        )
        self.status_pub = self.create_publisher(
            String, "/atlas/mission_status", 10
        )
        self.current_status = "STARTING"
        self.safety_status = "UNKNOWN"
        self.tracker_paused_for_goal = False
        self.create_timer(1.0, self.publish_current_status)
        self.safety_subscription = self.create_subscription(
            String, "/atlas/safety_status", self.update_safety_status, 10
        )

        self.worker = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="atlas-mission"
        )
        self.operation_lock = Lock()

        bindings = {
            "/atlas/start_exploration": self.request_start_exploration,
            "/atlas/stop_exploration": self.request_stop_exploration,
            "/atlas/set_home": self.request_set_home,
            "/atlas/return_home": self.request_return_home,
            "/atlas/cancel_navigation": self.request_cancel_navigation,
        }
        # Keep explicit references for the lifetime of the node. Without this,
        # Python may garbage-collect a subscription after long runtimes and a
        # Foxglove/dashboard button can appear to publish while no callback is
        # invoked.
        self.command_subscriptions = [
            self.create_subscription(Empty, topic, callback, 10)
            for topic, callback in bindings.items()
        ]
        self.command_subscriptions.extend(
            [
                self.create_subscription(String, "/atlas/save_named_place", self.request_save_named_place, 10),
                self.create_subscription(String, "/atlas/navigate_named_place", self.request_navigate_named_place, 10),
            ]
        )

        self.create_service(
            Trigger, "/atlas/start_exploration",
            lambda req, res: self.service_submit(
                res, self.start_exploration, "exploration start queued"
            )
        )
        self.create_service(
            Trigger, "/atlas/stop_exploration",
            lambda req, res: self.service_submit(
                res, self.stop_exploration, "exploration stop/map save queued"
            )
        )
        self.create_service(
            Trigger, "/atlas/set_home",
            lambda req, res: self.service_submit(
                res, self.set_home, "home save queued"
            )
        )
        self.create_service(
            Trigger, "/atlas/return_home",
            lambda req, res: self.service_submit(
                res, self.return_home, "return-home queued"
            )
        )
        self.create_service(
            Trigger, "/atlas/cancel_navigation",
            lambda req, res: self.service_submit(
                res, self.cancel_navigation, "navigation cancel queued"
            )
        )
        self.status("READY")
        self.get_logger().info(
            "Foxglove topic bindings ready: start, stop, set-home, return-home, cancel"
        )

    def status(self, text: str) -> None:
        self.current_status = text
        self.status_pub.publish(String(data=text))
        self.get_logger().info(text)

    def publish_current_status(self) -> None:
        self.status_pub.publish(String(data=self.current_status))

    def update_safety_status(self, msg: String) -> None:
        self.safety_status = msg.data.strip()

    def safety_blocks_autonomy(self) -> bool:
        value = self.safety_status.upper()
        return any(
            marker in value
            for marker in ("BLOCKED", "EMERGENCY", "E-STOP", "ESTOP")
        )

    def error(self, operation: str, exc: Exception) -> None:
        message = f"ERROR {operation}: {exc}"
        self.current_status = message
        self.status_pub.publish(String(data=message))
        self.get_logger().error(message)

    def submit(self, name: str, operation: Callable[[], None]) -> None:
        if not self.operation_lock.acquire(blocking=False):
            self.status(f"BUSY: ignored {name}")
            return

        def run():
            try:
                operation()
            except Exception as exc:
                self.error(name, exc)
            finally:
                self.operation_lock.release()

        self.status(f"QUEUED {name}")
        self.worker.submit(run)

    def service_submit(self, response, operation, message):
        self.submit(message, operation)
        response.success = True
        response.message = message
        return response

    def request_start_exploration(self, _msg: Empty) -> None:
        self.submit("start exploration", self.start_exploration)

    def request_stop_exploration(self, _msg: Empty) -> None:
        self.submit("stop exploration", self.stop_exploration)

    def request_set_home(self, _msg: Empty) -> None:
        self.submit("set home", self.set_home)

    def request_return_home(self, _msg: Empty) -> None:
        self.submit("return home", self.return_home)

    def request_cancel_navigation(self, _msg: Empty) -> None:
        self.submit("cancel navigation", self.cancel_navigation)

    @staticmethod
    def clean_place_name(value: str) -> str:
        name = " ".join((value or "").strip().lower().split())
        if not name or len(name) > 48 or not all(c.isalnum() or c in " _-" for c in name):
            raise ValueError("place name is missing or invalid")
        return name

    def request_save_named_place(self, msg: String) -> None:
        try:
            name = self.clean_place_name(msg.data)
            self.submit(f"save named place {name}", lambda: self.save_named_place(name))
        except Exception as exc:
            self.error("save named place", exc)

    def request_navigate_named_place(self, msg: String) -> None:
        try:
            name = self.clean_place_name(msg.data)
            self.submit(f"navigate named place {name}", lambda: self.navigate_named_place(name))
        except Exception as exc:
            self.error("navigate named place", exc)

    def current_pose(self):
        failures = []
        for frame_id in ("map", "odom"):
            try:
                transform = self.tf_buffer.lookup_transform(
                    frame_id, "base_link", rclpy.time.Time(),
                    timeout=rclpy.duration.Duration(seconds=1.0)
                )
                return {
                    "frame_id": frame_id,
                    "x": transform.transform.translation.x,
                    "y": transform.transform.translation.y,
                    "z": transform.transform.translation.z,
                    "qx": transform.transform.rotation.x,
                    "qy": transform.transform.rotation.y,
                    "qz": transform.transform.rotation.z,
                    "qw": transform.transform.rotation.w,
                }
            except Exception as exc:
                failures.append(f"{frame_id}: {exc}")
        raise RuntimeError("no map/odom pose available; " + " | ".join(failures))

    def set_home(self) -> None:
        pose = self.stable_current_pose()
        self.home_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.home_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(pose, indent=2), encoding="utf-8")
        temporary.replace(self.home_file)
        self.status(
            f"HOME SAVED frame={pose['frame_id']} "
            f"x={pose['x']:.2f} y={pose['y']:.2f}"
        )

    def stable_current_pose(
        self, samples: int = 5, interval: float = 0.4,
        tolerance: float = 0.05,
    ) -> dict:
        """Return a settled pose and refuse to save while SLAM is shifting."""
        poses = []
        for index in range(samples):
            poses.append(self.current_pose())
            if index + 1 < samples:
                time.sleep(interval)
        frames = {pose["frame_id"] for pose in poses}
        if len(frames) != 1:
            raise RuntimeError("pose frame changed while saving home")
        anchor = poses[-1]
        spread = max(
            math.hypot(
                float(pose["x"]) - float(anchor["x"]),
                float(pose["y"]) - float(anchor["y"]),
            )
            for pose in poses
        )
        if spread > tolerance:
            raise RuntimeError(
                f"SLAM pose is not settled (shift={spread:.2f}m); "
                "keep ATLAS stopped and try SET HOME again"
            )
        return anchor

    def save_localization_seed(self) -> dict:
        """Persist the final pose that belongs to the map being saved."""
        pose = self.stable_current_pose()
        if pose.get("frame_id") != "map":
            raise RuntimeError("localization seed requires a live map-frame pose")
        self.localization_seed_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.localization_seed_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(pose, indent=2), encoding="utf-8")
        temporary.replace(self.localization_seed_file)
        self.get_logger().info(
            "LOCALIZATION SEED SAVED "
            f"x={pose['x']:.2f} y={pose['y']:.2f}"
        )
        return pose

    def start_exploration(self) -> None:
        # Saved-map localization is the safe boot default.  Switch to the
        # mapping stack before recording home so the pose belongs to the new
        # live SLAM frame rather than the previously loaded map frame.
        self.ensure_mapping_stack()
        # Start always records the present SLAM pose as mission home.
        self.set_home()
        self.pause_mapping_background()
        try:
            self.center_camera_for_navigation()
            result = subprocess.run(
                ["systemctl", "--user", "start", self.explore_unit],
                check=False, timeout=8, capture_output=True, text=True
            )
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "systemctl start failed")
        except Exception:
            self.restore_mapping_background()
            raise
        self.status("EXPLORATION ACTIVE")

    def center_camera_for_navigation(self) -> None:
        """Put the pan/tilt camera in its calibrated forward navigation pose."""
        for _ in range(3):
            self.camera_pan_pub.publish(Int32(data=1300))
            self.camera_tilt_pub.publish(Int32(data=2100))
            time.sleep(0.15)
        self.get_logger().info(
            "Camera centered for LiDAR-confirmed semantic navigation"
        )

    def ensure_mapping_stack(self) -> None:
        """Enter mapping mode without allowing explore_lite to move early."""
        stop = subprocess.run(
            ["systemctl", "--user", "stop", "atlas-localization.service"],
            check=False, timeout=35, capture_output=True, text=True,
        )
        if stop.returncode:
            raise RuntimeError(
                stop.stderr.strip() or "could not stop saved-map localization"
            )
        start = subprocess.run(
            [
                "systemctl", "--user", "start",
                "atlas-slam-fast.service", "atlas-nav2.service",
            ],
            check=False, timeout=35, capture_output=True, text=True,
        )
        if start.returncode:
            raise RuntimeError(
                start.stderr.strip() or "could not start mapping stack"
            )
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            ready = all(
                subprocess.run(
                    ["systemctl", "--user", "is-active", "--quiet", unit],
                    check=False, timeout=4,
                ).returncode == 0
                for unit in ("atlas-slam-fast.service", "atlas-nav2.service")
            )
            if ready and self.nav.wait_for_server(timeout_sec=1.0):
                return
            time.sleep(1.0)
        raise RuntimeError("mapping stack did not become ready within 30 seconds")

    def pause_mapping_background(self) -> None:
        """Free CPU for SLAM/Nav2 while preserving the live raw camera."""
        active = []
        for unit in self.MAPPING_BACKGROUND_UNITS:
            check = subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", unit],
                check=False, timeout=3,
            )
            if check.returncode == 0:
                active.append(unit)
        if active:
            result = subprocess.run(
                ["systemctl", "--user", "stop", *active],
                check=False, timeout=15, capture_output=True, text=True,
            )
            if result.returncode:
                raise RuntimeError(
                    result.stderr.strip() or "could not pause mapping background"
                )
        self.paused_services_file.parent.mkdir(parents=True, exist_ok=True)
        self.paused_services_file.write_text(
            json.dumps(active, indent=2), encoding="utf-8"
        )
        self.get_logger().info(
            "Mapping CPU profile active; paused: " +
            (", ".join(active) or "none")
        )

    def load_named_places(self) -> dict:
        try:
            data = json.loads(self.places_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_named_place(self, name: str) -> None:
        pose = self.current_pose()
        if pose.get("frame_id") != "map":
            raise RuntimeError(
                "named places require a live map pose; start mapping or localization first"
            )
        places = self.load_named_places()
        places[name] = pose
        self.places_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.places_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(places, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.places_file)
        self.status(f"PLACE SAVED name={name} frame={pose['frame_id']} x={pose['x']:.2f} y={pose['y']:.2f}")

    def navigate_named_place(self, name: str) -> None:
        places = self.load_named_places()
        if name not in places:
            known = ", ".join(sorted(places)) or "none"
            raise RuntimeError(f"unknown named place {name!r}; known places: {known}")
        pose = places[name]
        if pose.get("frame_id") != "map":
            raise RuntimeError(f"named place {name!r} is not stored in the map frame")
        self.dispatch_pose_goal(pose, name)

    def dispatch_pose_goal(self, pose: dict, label: str) -> None:
        # Nav2 semantic fusion assumes the optical axis stays aligned with the
        # calibrated forward camera/LiDAR geometry. Person-follow mode may
        # move the camera, so pause tracking only for the duration of a goal.
        self.tracker_paused_for_goal = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "atlas-camera-tracker.service"],
            check=False, timeout=3,
        ).returncode == 0
        if self.tracker_paused_for_goal:
            subprocess.run(
                ["systemctl", "--user", "stop", "atlas-camera-tracker.service"],
                check=False, timeout=10, capture_output=True, text=True,
            )
        self.center_camera_for_navigation()
        if not self.nav.wait_for_server(timeout_sec=10.0):
            self.restore_goal_tracker()
            raise RuntimeError("Nav2 NavigateToPose action is unavailable")
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = pose.get("frame_id", "map")
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(pose["x"])
        goal.pose.pose.position.y = float(pose["y"])
        goal.pose.pose.position.z = float(pose.get("z", 0.0))
        goal.pose.pose.orientation.x = float(pose["qx"])
        goal.pose.pose.orientation.y = float(pose["qy"])
        goal.pose.pose.orientation.z = float(pose["qz"])
        goal.pose.pose.orientation.w = float(pose["qw"])
        future = self.nav.send_goal_async(goal)
        future.add_done_callback(lambda done: self.named_goal_response(done, label))
        self.status(f"NAMED GOAL DISPATCHED name={label}")

    def named_goal_response(self, future, label: str) -> None:
        try:
            handle = future.result()
            if not handle.accepted:
                self.status(f"NAMED GOAL REJECTED name={label}")
                return
            self.status(f"NAMED GOAL ACCEPTED name={label}")
            result = handle.get_result_async()
            result.add_done_callback(lambda done: self.named_goal_finished(done, label))
        except Exception as exc:
            self.restore_goal_tracker()
            self.error(f"named goal {label}", exc)

    def named_goal_finished(self, future, label: str) -> None:
        try:
            self.status(f"NAMED GOAL FINISHED name={label} status={future.result().status}")
        finally:
            self.restore_goal_tracker()

    def restore_goal_tracker(self) -> None:
        if self.tracker_paused_for_goal:
            subprocess.run(
                ["systemctl", "--user", "reset-failed", "atlas-camera-tracker.service"],
                check=False, timeout=5, capture_output=True, text=True,
            )
            subprocess.run(
                ["systemctl", "--user", "start", "atlas-camera-tracker.service"],
                check=False, timeout=10, capture_output=True, text=True,
            )
        self.tracker_paused_for_goal = False

    def restore_mapping_background(self) -> None:
        """Restore only services that were active before mapping began."""
        if not self.paused_services_file.exists():
            return
        try:
            units = json.loads(
                self.paused_services_file.read_text(encoding="utf-8")
            )
            if units:
                result = subprocess.run(
                    ["systemctl", "--user", "start", *units],
                    check=False, timeout=20, capture_output=True, text=True,
                )
                if result.returncode:
                    raise RuntimeError(
                        result.stderr.strip() or "could not restore mapping background"
                    )
            self.paused_services_file.unlink(missing_ok=True)
            self.get_logger().info("Normal CPU profile restored")
        except Exception as exc:
            self.get_logger().error(f"Background restore failed: {exc}")

    def cancel_all_nav_goals(self) -> bool:
        if not self.cancel_nav.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn("Nav2 cancel service unavailable")
            return False
        request = CancelGoal.Request()
        request.goal_info.goal_id.uuid = [0] * 16
        request.goal_info.stamp.sec = 0
        request.goal_info.stamp.nanosec = 0
        future = self.cancel_nav.call_async(request)
        deadline = time.monotonic() + 3.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done():
            self.get_logger().error("Timed out waiting for Nav2 goal cancellation")
            return False
        response = future.result()
        if response is None:
            self.get_logger().error("Nav2 goal cancellation returned no response")
            return False
        self.get_logger().info(
            f"Nav2 cancel acknowledged; goals_canceling={len(response.goals_canceling)}"
        )
        return True

    def stop_exploration(self) -> None:
        try:
            self.zero_pub.publish(Twist())
            map_yaml = self.map_prefix.with_suffix(".yaml")
            map_image = self.map_prefix.with_suffix(".pgm")
            previous_yaml_mtime = map_yaml.stat().st_mtime if map_yaml.exists() else 0.0
            previous_image_mtime = map_image.stat().st_mtime if map_image.exists() else 0.0
            result = subprocess.run(
                ["systemctl", "--user", "stop", self.explore_unit],
                check=False, timeout=40, capture_output=True, text=True
            )
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "systemctl stop failed")
            if not self.cancel_all_nav_goals():
                raise RuntimeError("exploration stopped but Nav2 goal cancellation was not acknowledged")
            self.zero_pub.publish(Twist())
            # Capture the settled endpoint while this exact SLAM map is still
            # active.  The next localization boot must never reuse a seed
            # from an older map/session.
            self.save_localization_seed()

            # ExecStopPost normally saves the map. Avoid racing it with a
            # second map_saver; only run it when no fresh YAML appeared.
            saved_by_unit = (
                map_yaml.exists()
                and map_image.exists()
                and map_yaml.stat().st_mtime > previous_yaml_mtime
                and map_image.stat().st_mtime > previous_image_mtime
            )
            if not saved_by_unit:
                save = subprocess.run(
                    [
                        "ros2", "run", "nav2_map_server", "map_saver_cli",
                        "-f", str(self.map_prefix),
                        "--ros-args", "-p", "save_map_timeout:=18.0",
                    ],
                    check=False, timeout=30, capture_output=True, text=True
                )
                self.zero_pub.publish(Twist())
                if save.returncode:
                    raise RuntimeError(save.stderr.strip() or "map save failed")
            if not map_yaml.exists() or not map_image.exists():
                raise RuntimeError("map saver returned success but YAML/PGM output is incomplete")
            self.status(f"EXPLORATION STOPPED; MAP SAVED {self.map_prefix}.yaml")
        finally:
            self.restore_mapping_background()

    def cancel_navigation(self) -> None:
        """Cancel active Nav2 goals without changing mapping or saving a map."""
        self.zero_pub.publish(Twist())
        if not self.cancel_all_nav_goals():
            raise RuntimeError("Nav2 goal cancellation was not acknowledged")
        self.zero_pub.publish(Twist())
        self.status("NAVIGATION CANCELED; ROVER STOPPED")

    def return_home(self) -> None:
        if not self.home_file.exists():
            raise RuntimeError("home pose has not been saved")
        if self.safety_blocks_autonomy():
            raise RuntimeError(
                f"safety blocks return-home: {self.safety_status}"
            )
        if not self.nav.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("Nav2 NavigateToPose action is unavailable")
        pose = json.loads(self.home_file.read_text(encoding="utf-8"))
        self.dispatch_home_goal(pose, attempt=0)

    def dispatch_home_goal(self, pose, attempt: int) -> None:
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = pose.get("frame_id", "map")
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(pose["x"])
        goal.pose.pose.position.y = float(pose["y"])
        goal.pose.pose.position.z = float(pose.get("z", 0.0))
        goal.pose.pose.orientation.x = float(pose["qx"])
        goal.pose.pose.orientation.y = float(pose["qy"])
        goal.pose.pose.orientation.z = float(pose["qz"])
        goal.pose.pose.orientation.w = float(pose["qw"])
        future = self.nav.send_goal_async(goal)
        future.add_done_callback(
            lambda done: self.home_goal_response(done, pose, attempt)
        )
        self.status(f"RETURN HOME GOAL DISPATCHED attempt={attempt + 1}")

    def home_goal_response(self, future, pose, attempt: int) -> None:
        try:
            handle = future.result()
            if not handle.accepted:
                self.status("RETURN HOME REJECTED")
                return
            self.status("RETURN HOME ACCEPTED")
            result = handle.get_result_async()
            result.add_done_callback(
                lambda done: self.home_goal_result(done, pose, attempt)
            )
        except Exception as exc:
            self.error("return-home action", exc)

    def home_goal_result(self, future, pose, attempt: int) -> None:
        try:
            status = future.result().status
            self.status(f"RETURN HOME FINISHED status={status}")
            if status == 4:
                self.worker.submit(
                    self.verify_home_after_settle, pose, attempt
                )
        except Exception as exc:
            self.error("return-home result", exc)

    def verify_home_after_settle(self, home, attempt: int) -> None:
        """Reject transient SLAM success and retry once after pose settles."""
        time.sleep(max(0.0, self.home_verify_delay))
        current = self.current_pose()
        if current["frame_id"] != home.get("frame_id", "map"):
            raise RuntimeError(
                "cannot verify home across different pose frames: "
                f"{current['frame_id']} != {home.get('frame_id', 'map')}"
            )
        error = math.hypot(
            float(current["x"]) - float(home["x"]),
            float(current["y"]) - float(home["y"]),
        )
        if error <= self.home_verify_tolerance:
            self.status(f"RETURN HOME VERIFIED error={error:.2f}m")
            return
        if self.safety_blocks_autonomy():
            self.zero_pub.publish(Twist())
            self.status(
                f"RETURN HOME RETRY BLOCKED error={error:.2f}m; "
                f"{self.safety_status}"
            )
            return
        if attempt >= self.home_max_retries:
            self.status(f"RETURN HOME INACCURATE error={error:.2f}m; STOPPED")
            self.zero_pub.publish(Twist())
            return
        self.status(
            f"RETURN HOME RETRY error={error:.2f}m attempt={attempt + 2}"
        )
        self.dispatch_home_goal(home, attempt + 1)

    def destroy_node(self):
        if rclpy.ok():
            self.zero_pub.publish(Twist())
        self.worker.shutdown(wait=False, cancel_futures=True)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = AtlasMissionControl()
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
