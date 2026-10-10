#!/usr/bin/env python3
"""Non-blocking Foxglove mission bindings for Project ATLAS."""

from concurrent.futures import ThreadPoolExecutor
from collections import deque
import json
import math
import os
import subprocess
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

import rclpy
from action_msgs.msg import GoalStatus
from action_msgs.srv import CancelGoal
from geometry_msgs.msg import (
    PolygonStamped,
    PoseStamped,
    PoseWithCovarianceStamped,
    Twist,
)
from nav_msgs.msg import OccupancyGrid, Odometry
from nav2_msgs.action import (
    ComputePathToPose,
    NavigateThroughPoses,
    NavigateToPose,
)
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Empty, Int32, String
from std_srvs.srv import Empty as EmptyService, Trigger
from tf2_ros import Buffer, TransformListener
from tf2_msgs.msg import TFMessage

from atlas_map_acceptance_core import (
    COMMISSIONED_SLAM_TF_FUTURE_OFFSET_S,
    EVIDENCE_SCHEMA_VERSION,
    MapAcceptancePolicy,
    TransformJumpTracker,
    closure_evidence,
    evaluate_acceptance_evidence,
    exact_candidate_connectivity,
    map_pair_id,
    polygon_dimensions,
    prepare_map_bound_metadata_values,
    transactionally_promote_map_pair,
)
from atlas_map_footprint_sanitizer import sanitize_saved_map
from atlas_amcl_update_gate import AmclUpdateGate
from atlas_amcl_processing_health import ProcessingHealth
from atlas_scan_fit_core import (
    OccupiedIndex,
    ScanFitPolicy,
    evaluate as evaluate_scan_fit,
    load_occupied_index,
    unused_beam_points,
)


class AtlasMissionControl(Node):
    """Expose topic and service controls without blocking the ROS executor."""

    MAPPING_BACKGROUND_UNITS = (
        "atlas-camera-tracker.service",
        "atlas-follow-person.service",
        "atlas-foxglove.service",
        "atlas-voice-companion.service",
    )
    CAMERA_PAN_MIN_US = 700
    CAMERA_PAN_MAX_US = 2300
    CAMERA_PAN_HOME_US = 1628
    CAMERA_TILT_MIN_US = 500
    CAMERA_TILT_MAX_US = 2500
    CAMERA_TILT_HOME_US = 1442
    CAMERA_STEP_US = 160
    CAMERA_HOME_FILE = (
        Path.home()
        / ".config/systemd/user/atlas-uno-r4-sensor-hub.service.d/camera-home.conf"
    )

    def __init__(self):
        super().__init__("atlas_mission_control")
        self.camera_pan_home_us, self.camera_tilt_home_us = self.load_camera_home()
        self.declare_parameter(
            "map_prefix", "/home/jetson/project_atlas/maps/atlas_latest"
        )
        self.declare_parameter("explore_unit", "atlas-explore.service")
        self.declare_parameter("home_verify_delay", 2.0)
        self.declare_parameter("amcl_guarded_refresh_enabled", False)
        self.declare_parameter("amcl_motion_gated_updates", False)
        self.amcl_motion_gated_updates = bool(
            self.get_parameter("amcl_motion_gated_updates").value)
        self.amcl_guarded_refresh_enabled = bool(
            self.get_parameter("amcl_guarded_refresh_enabled").value)
        self.amcl_processing = ProcessingHealth()
        self.guarded_refresh_key = None
        self.create_subscription(String, "/atlas_amcl/processing", self.on_amcl_processing, 1)
        self.create_subscription(Empty, "/atlas/localization_refresh_request",
                                 self.on_guarded_localization_refresh, 1)
        self.declare_parameter("home_verify_tolerance", 0.15)
        self.declare_parameter("home_max_retries", 1)
        self.declare_parameter("home_already_reached_distance_m", 0.05)
        self.declare_parameter("home_already_reached_yaw_deg", 10.0)
        self.declare_parameter("localization_max_xy_std_m", 0.60)
        self.declare_parameter("localization_max_yaw_std_deg", 25.0)
        self.declare_parameter("localization_stability_window_s", 8.0)
        self.declare_parameter("localization_max_stationary_shift_m", 0.10)
        self.declare_parameter("localization_max_stationary_yaw_deg", 5.0)
        self.declare_parameter("map_acceptance_max_tf_jump_m", 0.15)
        self.declare_parameter("map_acceptance_max_tf_yaw_deg", 5.0)
        self.declare_parameter("map_acceptance_max_closure_m", 0.15)
        self.declare_parameter("map_acceptance_max_closure_yaw_deg", 10.0)
        self.declare_parameter(
            "map_acceptance_slam_tf_future_offset_s",
            COMMISSIONED_SLAM_TF_FUTURE_OFFSET_S,
        )
        self.declare_parameter("map_acceptance_start_place", "dhruv room")
        self.declare_parameter("map_acceptance_goal_place", "hall")
        self.home_file = Path.home() / ".config/project_atlas/home_pose.json"
        self.localization_seed_file = (
            Path.home() / ".config/project_atlas/localization_seed_pose.json"
        )
        self.places_file = Path.home() / ".config/project_atlas/named_places.json"
        self.taught_routes_dir = Path("/home/jetson/project_atlas/config/routes")
        self.map_prefix = Path(str(self.get_parameter("map_prefix").value))
        # Mission-start LiDAR/map agreement (2026-10-10). Only ever refuses.
        self.declare_parameter("scan_fit_gate_enabled", True)
        self.declare_parameter("scan_fit_min_fraction", 0.85)
        self.scan_fit_gate_enabled = bool(
            self.get_parameter("scan_fit_gate_enabled").value)
        self.scan_fit_policy = ScanFitPolicy(
            min_fit_fraction=float(self.get_parameter("scan_fit_min_fraction").value))
        self.latest_scan = None
        self.latest_scan_received_at = None
        self.scan_fit_map_key = None
        self.scan_fit_index = None
        self.create_subscription(
            LaserScan, "/scan", self.update_latest_scan, qos_profile_sensor_data)
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
        self.home_already_reached_distance_m = float(
            self.get_parameter("home_already_reached_distance_m").value
        )
        self.home_already_reached_yaw_deg = float(
            self.get_parameter("home_already_reached_yaw_deg").value
        )
        self.localization_max_xy_std_m = float(
            self.get_parameter("localization_max_xy_std_m").value
        )
        self.localization_max_yaw_std_deg = float(
            self.get_parameter("localization_max_yaw_std_deg").value
        )
        self.localization_stability_window_s = float(
            self.get_parameter("localization_stability_window_s").value
        )
        self.localization_max_stationary_shift_m = float(
            self.get_parameter("localization_max_stationary_shift_m").value
        )
        self.localization_max_stationary_yaw_deg = float(
            self.get_parameter("localization_max_stationary_yaw_deg").value
        )
        self.map_acceptance_policy = MapAcceptancePolicy(
            max_tf_translation_jump_m=min(
                0.15,
                float(self.get_parameter("map_acceptance_max_tf_jump_m").value),
            ),
            max_tf_yaw_jump_deg=min(
                5.0,
                float(self.get_parameter("map_acceptance_max_tf_yaw_deg").value),
            ),
            max_closure_translation_m=min(
                0.15,
                float(self.get_parameter("map_acceptance_max_closure_m").value),
            ),
            max_closure_yaw_deg=min(
                10.0,
                float(
                    self.get_parameter("map_acceptance_max_closure_yaw_deg").value
                ),
            ),
        )
        self.map_acceptance_slam_tf_future_offset_s = float(
            self.get_parameter(
                "map_acceptance_slam_tf_future_offset_s"
            ).value
        )
        if (
            not math.isfinite(self.map_acceptance_slam_tf_future_offset_s)
            or self.map_acceptance_slam_tf_future_offset_s < 0.0
            or self.map_acceptance_slam_tf_future_offset_s
            > self.map_acceptance_policy.max_tf_source_future_offset_s
        ):
            raise ValueError(
                "map_acceptance_slam_tf_future_offset_s must be finite and "
                "within the commissioned 0.0-"
                f"{self.map_acceptance_policy.max_tf_source_future_offset_s:.1f}s bound"
            )
        self.map_acceptance_start_place = self.clean_place_name(
            str(self.get_parameter("map_acceptance_start_place").value)
        )
        self.map_acceptance_goal_place = self.clean_place_name(
            str(self.get_parameter("map_acceptance_goal_place").value)
        )
        if self.map_acceptance_start_place == self.map_acceptance_goal_place:
            raise ValueError("map-acceptance endpoints must be different places")
        self.paused_services_file = (
            Path.home() / ".config/project_atlas/mapping_paused_services.json"
        )
        self.mapping_session_file = (
            Path.home() / ".config/project_atlas/mapping_session.json"
        )
        self.mapping_recorder_process = None
        self.mapping_recorder_script = Path(__file__).with_name(
            "record_atlas_demonstration.sh"
        )

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.nav = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        self.path_planner = ActionClient(
            self, ComputePathToPose, "/compute_path_to_pose"
        )
        self.nav_through = ActionClient(
            self, NavigateThroughPoses, "/navigate_through_poses"
        )
        self.cancel_nav = self.create_client(
            CancelGoal, "/navigate_to_pose/_action/cancel_goal"
        )
        self.cancel_nav_through = self.create_client(
            CancelGoal, "/navigate_through_poses/_action/cancel_goal"
        )
        self.zero_pub = self.create_publisher(Twist, "/cmd_vel_nav", 10)
        self.camera_pan_pub = self.create_publisher(
            Int32, "/camera/bottom_servo_cmd_us", 10
        )
        self.camera_tilt_pub = self.create_publisher(
            Int32, "/camera/second_servo_cmd_us", 10
        )
        self.camera_pan_us = self.camera_pan_home_us
        self.camera_tilt_us = self.camera_tilt_home_us
        self.create_subscription(
            Int32, "/camera/bottom_servo_us", self.update_camera_pan, 10
        )
        self.create_subscription(
            Int32, "/camera/second_servo_us", self.update_camera_tilt, 10
        )
        self.status_pub = self.create_publisher(
            String, "/atlas/mission_status", 10
        )
        self.current_status = "STARTING"
        self.safety_status = "UNKNOWN"
        self.localization_quality = None
        self.localization_samples = deque(maxlen=30)
        self.tracker_paused_for_goal = False
        self.map_acceptance_lock = Lock()
        self.map_tf_tracker = TransformJumpTracker(
            source_future_offset_s=(
                self.map_acceptance_slam_tf_future_offset_s
            ),
            max_source_future_skew_s=(
                self.map_acceptance_policy.max_tf_source_future_skew_s
            ),
        )
        self.global_footprint_observation = None
        self.create_timer(1.0, self.publish_current_status)
        self.safety_subscription = self.create_subscription(
            String, "/atlas/safety_status", self.update_safety_status, 10
        )
        self.localization_subscription = self.create_subscription(
            PoseWithCovarianceStamped,
            "/amcl_pose",
            self.update_localization_quality,
            10,
        )
        self.mapping_map_received_at = 0.0
        self.mapping_map_subscription = self.create_subscription(
            OccupancyGrid, "/map_raw", self.update_mapping_map, 1
        )
        self.mapping_tf_subscription = self.create_subscription(
            TFMessage, "/tf", self.update_mapping_tf, 100
        )
        self.global_footprint_subscription = self.create_subscription(
            PolygonStamped,
            "/global_costmap/published_footprint",
            self.update_global_footprint,
            10,
        )
        self.nomotion_client = self.create_client(
            EmptyService, "/request_nomotion_update"
        )
        self.amcl_update_gate = AmclUpdateGate()
        self.localization_update_future = None
        self.localization_odom = None
        self.create_subscription(Odometry, "/odom", self.update_localization_odom, 10)
        # Never manufacture a heartbeat by repeatedly assimilating stationary
        # evidence. The explicit pre-motion refresh and mux timeout remain.
        self.create_timer(1.0, self.request_periodic_localization_update)

        self.worker = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="atlas-mission"
        )
        self.operation_lock = Lock()

        bindings = {
            "/atlas/start_exploration": self.request_start_exploration,
            "/atlas/start_manual_mapping": self.request_start_manual_mapping,
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
                self.create_subscription(Empty, "/atlas/camera/pan_left", self.camera_pan_left, 10),
                self.create_subscription(Empty, "/atlas/camera/pan_right", self.camera_pan_right, 10),
                self.create_subscription(Empty, "/atlas/camera/tilt_up", self.camera_tilt_up, 10),
                self.create_subscription(Empty, "/atlas/camera/tilt_down", self.camera_tilt_down, 10),
                self.create_subscription(Empty, "/atlas/camera/home", self.camera_home, 10),
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
            "Foxglove topic bindings ready: missions, rear clearance, camera pan/tilt"
        )
        self.create_service(
            Trigger, "/atlas/start_manual_mapping",
            lambda req, res: self.service_submit(
                res, self.start_manual_mapping, "manual mapping start queued"
            )
        )

    def update_camera_pan(self, msg: Int32) -> None:
        self.camera_pan_us = max(
            self.CAMERA_PAN_MIN_US, min(self.CAMERA_PAN_MAX_US, int(msg.data))
        )

    def update_camera_tilt(self, msg: Int32) -> None:
        self.camera_tilt_us = max(
            self.CAMERA_TILT_MIN_US, min(self.CAMERA_TILT_MAX_US, int(msg.data))
        )

    def camera_pan_left(self, _msg: Empty) -> None:
        self.camera_pan_us = max(
            self.CAMERA_PAN_MIN_US, self.camera_pan_us - self.CAMERA_STEP_US
        )
        self.camera_pan_pub.publish(Int32(data=self.camera_pan_us))

    def camera_pan_right(self, _msg: Empty) -> None:
        self.camera_pan_us = min(
            self.CAMERA_PAN_MAX_US, self.camera_pan_us + self.CAMERA_STEP_US
        )
        self.camera_pan_pub.publish(Int32(data=self.camera_pan_us))

    def camera_tilt_up(self, _msg: Empty) -> None:
        self.camera_tilt_us = min(
            self.CAMERA_TILT_MAX_US, self.camera_tilt_us + self.CAMERA_STEP_US
        )
        self.camera_tilt_pub.publish(Int32(data=self.camera_tilt_us))

    def camera_tilt_down(self, _msg: Empty) -> None:
        self.camera_tilt_us = max(
            self.CAMERA_TILT_MIN_US, self.camera_tilt_us - self.CAMERA_STEP_US
        )
        self.camera_tilt_pub.publish(Int32(data=self.camera_tilt_us))

    def load_camera_home(self) -> tuple[int, int]:
        """Load the dashboard-commissioned forward pose from the shared file."""
        pan = self.CAMERA_PAN_HOME_US
        tilt = self.CAMERA_TILT_HOME_US
        try:
            for raw_line in self.CAMERA_HOME_FILE.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                pan_prefix = "Environment=ATLAS_CAMERA_PAN_HOME_US="
                tilt_prefix = "Environment=ATLAS_CAMERA_TILT_HOME_US="
                if line.startswith(pan_prefix):
                    pan = int(line[len(pan_prefix):])
                elif line.startswith(tilt_prefix):
                    tilt = int(line[len(tilt_prefix):])
        except (OSError, ValueError):
            self.get_logger().warning(
                "Saved camera home unavailable; using commissioned defaults"
            )
        return (
            max(self.CAMERA_PAN_MIN_US, min(self.CAMERA_PAN_MAX_US, pan)),
            max(self.CAMERA_TILT_MIN_US, min(self.CAMERA_TILT_MAX_US, tilt)),
        )

    def camera_home(self, _msg: Empty) -> None:
        self.camera_pan_home_us, self.camera_tilt_home_us = self.load_camera_home()
        self.camera_pan_us = self.camera_pan_home_us
        self.camera_tilt_us = self.camera_tilt_home_us
        self.camera_pan_pub.publish(Int32(data=self.camera_pan_us))
        self.camera_tilt_pub.publish(Int32(data=self.camera_tilt_us))

    def status(self, text: str) -> None:
        self.current_status = text
        self.status_pub.publish(String(data=text))
        self.get_logger().info(text)

    def publish_current_status(self) -> None:
        self.status_pub.publish(String(data=self.current_status))

    def update_safety_status(self, msg: String) -> None:
        self.safety_status = msg.data.strip()

    def update_mapping_map(self, _msg: OccupancyGrid) -> None:
        """Record receipt of a map produced by the running SLAM node."""
        self.mapping_map_received_at = time.monotonic()

    def begin_map_acceptance_observation(self, session: dict) -> None:
        """Start session-scoped TF evidence only after the session is durable."""
        with self.map_acceptance_lock:
            self.map_tf_tracker.begin(
                session["id"], session["started_unix"], time.time()
            )

    def start_mapping_recording(self, session_id: str) -> None:
        """Record the complete mapping run, including the SLAM startup boundary."""
        if self.mapping_recorder_process is not None:
            return
        if not self.mapping_recorder_script.exists():
            raise RuntimeError("mapping recorder script is missing")
        label = f"manual_mapping_{session_id[:12]}"
        self.mapping_recorder_process = subprocess.Popen(
            ["bash", str(self.mapping_recorder_script), label],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def stop_mapping_recording(self) -> None:
        process = self.mapping_recorder_process
        self.mapping_recorder_process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def update_mapping_tf(self, msg: TFMessage) -> None:
        """Track every publication-order map->odom correction during mapping."""
        now = time.time()
        with self.map_acceptance_lock:
            for transform in msg.transforms:
                parent = transform.header.frame_id.strip("/")
                child = transform.child_frame_id.strip("/")
                if parent != "map" or child != "odom":
                    continue
                rotation = transform.transform.rotation
                yaw = math.atan2(
                    2.0 * (
                        rotation.w * rotation.z + rotation.x * rotation.y
                    ),
                    1.0 - 2.0 * (
                        rotation.y * rotation.y + rotation.z * rotation.z
                    ),
                )
                translation = transform.transform.translation
                source_unix = (
                    float(transform.header.stamp.sec)
                    + float(transform.header.stamp.nanosec) * 1e-9
                )
                self.map_tf_tracker.observe(
                    translation.x, translation.y, yaw, now, source_unix
                )

    def update_global_footprint(self, msg: PolygonStamped) -> None:
        """Keep a fresh, rotation-independent global-costmap footprint proof."""
        points = [(float(point.x), float(point.y)) for point in msg.polygon.points]
        try:
            observation = polygon_dimensions(points)
        except ValueError:
            return
        observation.update(
            {
                "frame_id": msg.header.frame_id,
                "observed_unix": time.time(),
                "source": "/global_costmap/published_footprint",
            }
        )
        with self.map_acceptance_lock:
            self.global_footprint_observation = observation

    def update_localization_quality(self, msg: PoseWithCovarianceStamped) -> None:
        covariance = msg.pose.covariance
        xy_variance = max(0.0, covariance[0]) + max(0.0, covariance[7])
        yaw_variance = max(0.0, covariance[35])
        self.localization_quality = (
            math.sqrt(xy_variance),
            math.degrees(math.sqrt(yaw_variance)),
        )
        pose = msg.pose.pose
        self.localization_samples.append(
            (
                time.monotonic(),
                float(pose.position.x),
                float(pose.position.y),
                2.0 * math.atan2(
                    float(pose.orientation.z), float(pose.orientation.w)
                ),
            )
        )

    def update_localization_odom(self, msg: Odometry) -> None:
        self.localization_odom = msg

    def on_amcl_processing(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
        except (TypeError, ValueError):
            data = None
        self.amcl_processing.ingest(data, self.get_clock().now().nanoseconds/1e9,
                                    time.monotonic())

    def on_guarded_localization_refresh(self, _msg: Empty) -> None:
        if (not self.amcl_guarded_refresh_enabled
                or not self.nomotion_client.service_is_ready()
                or (self.localization_update_future is not None
                    and not self.localization_update_future.done())):
            return
        health = self.amcl_processing.snapshot(
            self.get_clock().now().nanoseconds/1e9, time.monotonic())
        if health['processing_state'] != 'PROCESSING':
            return
        key=(health['session'], health['pose_seq'])
        if key == self.guarded_refresh_key:
            return
        self.guarded_refresh_key=key
        self.localization_update_future=self.nomotion_client.call_async(EmptyService.Request())

    def request_periodic_localization_update(self) -> None:
        """Request at most one update for fresh, accumulated odometry progress.

        This does not certify localization or relax the motor mux's freshness
        gate. At very low speed that gate may stop motion; validation is needed
        before deploying this policy. AMCL's natural scan updates stay enabled.
        """
        if (not self.nomotion_client.service_is_ready()
                or (self.localization_update_future is not None
                    and not self.localization_update_future.done())):
            return
        if not self.amcl_motion_gated_updates:
            # Preserve deployed baseline unless the full experimental contract
            # is deliberately enabled. Still prevent overlapping requests.
            self.localization_update_future = self.nomotion_client.call_async(
                EmptyService.Request())
            return
        msg = self.localization_odom
        if msg is None or msg.header.frame_id.lstrip('/') != 'odom':
            return
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        norm = q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w
        if not math.isfinite(norm) or abs(norm - 1.0) > .01:
            return
        yaw = math.atan2(2*(q.w*q.z + q.x*q.y), 1-2*(q.y*q.y + q.z*q.z))
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        now = self.get_clock().now().nanoseconds * 1e-9
        if self.amcl_update_gate.allow(p.x, p.y, yaw, stamp, now):
            self.localization_update_future = self.nomotion_client.call_async(
                EmptyService.Request())

    def refresh_localization_before_motion(self, timeout_s: float = 5.0) -> None:
        """Force one fresh AMCL sample immediately before releasing motion.

        AMCL normally waits for a configured odometry change before
        publishing. The motor mux intentionally refuses autonomous motion when
        AMCL is older than 2.5 seconds, so a stationary rover can otherwise
        deadlock at mission start. A forced scan update breaks that deadlock
        without relaxing the watchdog.
        """
        # During an active SLAM mapping session, slam_toolbox owns map->odom and
        # AMCL is intentionally stopped. Requiring AMCL here deadlocks valid
        # return-home requests made before the new map is saved. Confirm that
        # the live SLAM transform is available, then let Nav2 use that pose.
        if self.active_mapping_session():
            slam_active = subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet",
                 "atlas-slam-fast.service"],
                check=False,
                timeout=4,
            ).returncode == 0
            if not slam_active:
                raise RuntimeError(
                    "active mapping session has no SLAM localization"
                )
            self.current_pose()
            return
        if not self.nomotion_client.wait_for_service(timeout_sec=1.0):
            raise RuntimeError("AMCL no-motion update service is unavailable")
        previous_stamp = (
            self.localization_samples[-1][0]
            if self.localization_samples else 0.0
        )
        future = self.nomotion_client.call_async(EmptyService.Request())
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if future.done() and future.exception() is not None:
                raise RuntimeError(
                    f"AMCL no-motion update failed: {future.exception()}"
                )
            if (
                self.localization_samples
                and self.localization_samples[-1][0] > previous_stamp
            ):
                self.require_confident_localization()
                return
            time.sleep(0.05)
        raise RuntimeError(
            "AMCL did not publish a fresh pose before motion; autonomy remains blocked"
        )

    @staticmethod
    def angle_delta(first: float, second: float) -> float:
        return math.atan2(math.sin(second - first), math.cos(second - first))

    def localization_stability(self) -> tuple:
        now = time.monotonic()
        window_start = now - self.localization_stability_window_s
        samples = [item for item in self.localization_samples if item[0] >= window_start]
        if len(samples) < 4:
            return None
        covered = samples[-1][0] - samples[0][0]
        if covered < self.localization_stability_window_s * 0.70:
            return None
        maximum_shift = max(
            math.hypot(a[1] - b[1], a[2] - b[2])
            for index, a in enumerate(samples)
            for b in samples[index + 1:]
        )
        reference_yaw = samples[0][3]
        relative_yaws = [self.angle_delta(reference_yaw, item[3]) for item in samples]
        maximum_yaw = math.degrees(max(relative_yaws) - min(relative_yaws))
        return maximum_shift, maximum_yaw

    def require_confident_localization(self) -> None:
        if self.localization_quality is None:
            raise RuntimeError(
                "localization confidence unavailable; set the current named "
                "place before autonomous navigation"
            )
        xy_std, yaw_std_deg = self.localization_quality
        if (
            xy_std > self.localization_max_xy_std_m
            or yaw_std_deg > self.localization_max_yaw_std_deg
        ):
            raise RuntimeError(
                "localization uncertain: "
                f"position_std={xy_std:.2f}m "
                f"heading_std={yaw_std_deg:.1f}deg; "
                "set the current named place before autonomous navigation"
            )
        stability = self.localization_stability()
        if stability is None:
            raise RuntimeError(
                "localization has not completed its stationary stability window; "
                "keep ATLAS stopped and retry shortly"
            )
        shift_m, yaw_deg = stability
        if (
            shift_m > self.localization_max_stationary_shift_m
            or yaw_deg > self.localization_max_stationary_yaw_deg
        ):
            raise RuntimeError(
                "localization still moving while ATLAS is stopped: "
                f"pose_shift={shift_m:.2f}m heading_shift={yaw_deg:.1f}deg; "
                "autonomous navigation remains blocked"
            )

    def safety_blocks_autonomy(self) -> bool:
        value = self.safety_status.upper()
        return any(
            marker in value
            for marker in (
                "BLOCKED",
                "FAULT",
                "STOP:",
                "EMERGENCY",
                "E-STOP",
                "ESTOP",
            )
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

    def request_start_manual_mapping(self, _msg: Empty) -> None:
        self.submit("start manual mapping", self.start_manual_mapping)

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

    @staticmethod
    def atomic_write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def map_files_id(yaml_path: Path, image_path: Path) -> Optional[str]:
        """Return the identity of an explicit YAML/image pair."""
        return map_pair_id(yaml_path, image_path)

    def current_map_id(self) -> Optional[str]:
        """Return an identity tied to the exact accepted YAML and image."""
        yaml_path = self.map_prefix.with_suffix(".yaml")
        if not yaml_path.exists():
            return None
        image_path = self.map_prefix.with_suffix(".pgm")
        try:
            for line in yaml_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("image:"):
                    image_name = line.split(":", 1)[1].strip().strip("'\"")
                    candidate = Path(image_name)
                    image_path = (
                        candidate
                        if candidate.is_absolute()
                        else yaml_path.parent / candidate
                    )
                    break
        except OSError:
            return None
        return self.map_files_id(yaml_path, image_path)

    def active_mapping_session(self) -> Optional[dict]:
        try:
            value = json.loads(self.mapping_session_file.read_text(encoding="utf-8"))
            return value if value.get("state") == "active" else None
        except (OSError, ValueError, AttributeError):
            return None

    def require_matching_map(self, pose: dict, label: str) -> None:
        stored_id = pose.get("map_id")
        current_id = self.current_map_id()
        if stored_id and current_id and stored_id != current_id:
            raise RuntimeError(
                f"{label} belongs to a different map; set it again on the current map"
            )

    def update_latest_scan(self, msg: LaserScan) -> None:
        self.latest_scan = msg
        self.latest_scan_received_at = time.monotonic()

    def scan_fit_map_index(self) -> OccupiedIndex:
        yaml_path = self.map_prefix.with_suffix(".yaml")
        image_path = self.map_prefix.with_suffix(".pgm")
        key = tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in (yaml_path, image_path))
        if key != self.scan_fit_map_key:
            self.scan_fit_index = load_occupied_index(yaml_path, image_path)
            self.scan_fit_map_key = key
        return self.scan_fit_index

    def require_scan_map_agreement(self) -> None:
        """Refuse saved-map goals when a fresh scan disagrees with the map.

        Covariance and stillness checks pass while AMCL sits confidently at a
        wrong pose, e.g. after ATLAS was moved by hand (2026-10-10 audits).
        This scores beams AMCL does not sample against the accepted map bytes.
        It never publishes, seeds or moves anything; it can only refuse.
        """
        if not self.scan_fit_gate_enabled or self.active_mapping_session():
            return
        current = self.current_pose()
        if current.get("frame_id") != "map":
            raise RuntimeError("scan check blocked: no map-frame pose")
        try:
            laser_tf = self.tf_buffer.lookup_transform(
                "base_link", "laser_frame", rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=1.0))
            index = self.scan_fit_map_index()
        except Exception as exc:
            raise RuntimeError(f"scan check blocked: {exc}") from exc
        scan = self.latest_scan
        age = (None if self.latest_scan_received_at is None
               else time.monotonic() - self.latest_scan_received_at)
        points = [] if scan is None else unused_beam_points(
            scan.angle_min, scan.angle_increment, scan.ranges,
            scan.range_min, scan.range_max, self.scan_fit_policy)
        q = laser_tf.transform.rotation
        laser = (laser_tf.transform.translation.x, laser_tf.transform.translation.y,
                 math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))
        pose = (float(current["x"]), float(current["y"]),
                math.atan2(2 * (current["qw"] * current["qz"] + current["qx"] * current["qy"]),
                           1 - 2 * (current["qy"] ** 2 + current["qz"] ** 2)))
        result = evaluate_scan_fit(points, pose, laser, index, age, self.scan_fit_policy)
        if not result.ok:
            raise RuntimeError("navigation blocked: " + result.reason)
        self.status(f"SCAN CHECK OK fit={result.fit_fraction:.0%} returns={result.endpoints}")

    def require_known_saved_map_start(self) -> None:
        """Do not dispatch a saved-map goal from unknown or occupied space.

        Active SLAM sessions use a changing map and are checked separately by
        Nav2. In localization mode, evaluate the exact accepted map bytes with
        the same conservative clearance used for map acceptance.
        """
        if self.active_mapping_session():
            return
        current = self.current_pose()
        if current.get("frame_id") != "map":
            raise RuntimeError("saved-map navigation has no map-frame start pose")
        try:
            exact_candidate_connectivity(
                self.map_prefix.with_suffix(".yaml"),
                self.map_prefix.with_suffix(".pgm"),
                current,
                current,
                inflation_radius_m=(
                    self.map_acceptance_policy.min_candidate_clearance_m
                ),
            )
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                "saved-map navigation blocked: current pose is not in known "
                f"clear space on the accepted map ({exc})"
            ) from exc

    def prepare_map_bound_metadata(
        self, new_map_id: str, old_map_id: Optional[str], session: dict
    ) -> dict:
        """Prepare, but do not write, the complete post-promotion metadata set.

        Current-session poses are bound to the validated candidate. Older
        unversioned named places are bound to the previous accepted map before
        replacement, preserving the legacy behavior while ensuring they fail
        closed against the new map. Returning serialized bytes lets map and
        metadata promotion share one rollback boundary.
        """

        home = json.loads(self.home_file.read_text(encoding="utf-8"))
        seed = json.loads(self.localization_seed_file.read_text(encoding="utf-8"))
        places = json.loads(self.places_file.read_text(encoding="utf-8"))
        prepared_home, prepared_seed, prepared_places = (
            prepare_map_bound_metadata_values(
                home=home,
                seed=seed,
                places=places,
                session_id=session["id"],
                new_map_id=new_map_id,
                old_map_id=old_map_id,
            )
        )
        return {
            self.home_file: json.dumps(prepared_home, indent=2).encode("utf-8"),
            self.localization_seed_file: json.dumps(
                prepared_seed, indent=2
            ).encode("utf-8"),
            self.places_file: json.dumps(prepared_places, indent=2).encode("utf-8"),
        }

    @staticmethod
    def wait_for_future(future, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        return future.done()

    @staticmethod
    def plan_pose(pose: dict, stamp) -> PoseStamped:
        message = PoseStamped()
        message.header.frame_id = "map"
        message.header.stamp = stamp
        message.pose.position.x = float(pose["x"])
        message.pose.position.y = float(pose["y"])
        message.pose.position.z = float(pose.get("z", 0.0))
        message.pose.orientation.x = float(pose["qx"])
        message.pose.orientation.y = float(pose["qy"])
        message.pose.orientation.z = float(pose["qz"])
        message.pose.orientation.w = float(pose["qw"])
        return message

    def plan_only_evidence(
        self, start_name: str, start_pose: dict, goal_name: str, goal_pose: dict
    ) -> dict:
        """Ask Nav2 for an explicit-start path without dispatching movement."""
        evidence = {
            "start": start_name,
            "goal": goal_name,
            "passed": False,
            "poses": 0,
        }
        try:
            if not self.path_planner.wait_for_server(timeout_sec=8.0):
                raise RuntimeError("Nav2 ComputePathToPose is unavailable")
            goal = ComputePathToPose.Goal()
            stamp = self.get_clock().now().to_msg()
            goal.start = self.plan_pose(start_pose, stamp)
            goal.goal = self.plan_pose(goal_pose, stamp)
            goal.use_start = True
            send_future = self.path_planner.send_goal_async(goal)
            if not self.wait_for_future(send_future, 10.0):
                raise RuntimeError("planner did not accept or reject within 10 seconds")
            handle = send_future.result()
            if handle is None or not handle.accepted:
                raise RuntimeError("planner rejected the plan-only request")
            result_future = handle.get_result_async()
            if not self.wait_for_future(result_future, 20.0):
                handle.cancel_goal_async()
                raise RuntimeError("planner did not finish within 20 seconds")
            wrapped = result_future.result()
            if wrapped is None:
                raise RuntimeError("planner returned no result")
            path = wrapped.result.path.poses
            length = sum(
                math.hypot(
                    second.pose.position.x - first.pose.position.x,
                    second.pose.position.y - first.pose.position.y,
                )
                for first, second in zip(path, path[1:])
            )
            evidence.update(
                {
                    "status": int(wrapped.status),
                    "poses": len(path),
                    "path_length_m": round(length, 6),
                    "passed": (
                        wrapped.status == GoalStatus.STATUS_SUCCEEDED
                        and len(path) >= self.map_acceptance_policy.min_path_poses
                    ),
                }
            )
            if not evidence["passed"]:
                evidence["error"] = "Nav2 returned no successful collision-free path"
        except Exception as exc:
            evidence["error"] = str(exc)
        return evidence

    def validate_candidate_map(
        self,
        candidate_prefix: Path,
        candidate_yaml: Path,
        candidate_image: Path,
        session: dict,
        seed: dict,
    ) -> str:
        """Collect and enforce every no-motion map-promotion safety gate."""
        candidate_map_id = self.map_files_id(candidate_yaml, candidate_image)
        if not candidate_map_id:
            raise RuntimeError(
                "candidate map identity could not be calculated; accepted map preserved"
            )

        closure = {"session_id": session["id"]}
        try:
            home = json.loads(self.home_file.read_text(encoding="utf-8"))
            if home.get("mapping_session_id") != session["id"]:
                raise RuntimeError("home pose belongs to a different mapping session")
            if seed.get("mapping_session_id") != session["id"]:
                raise RuntimeError("final seed belongs to a different mapping session")
            closure.update(closure_evidence(home, seed))
        except Exception as exc:
            closure["error"] = str(exc)

        plans = {
            "role": "supplemental_live_nav2_check",
            "forward": {"passed": False, "poses": 0},
            "reverse": {"passed": False, "poses": 0},
        }
        exact_connectivity = {
            "session_id": session["id"],
            "candidate_map_id": candidate_map_id,
            "connected": False,
            "unknown_is_blocked": True,
            "inflation_radius_m": self.map_acceptance_policy.min_candidate_clearance_m,
        }
        try:
            places = self.load_named_places()
            start_pose = places[self.map_acceptance_start_place]
            goal_pose = places[self.map_acceptance_goal_place]
            for name, pose in (
                (self.map_acceptance_start_place, start_pose),
                (self.map_acceptance_goal_place, goal_pose),
            ):
                if not isinstance(pose, dict) or pose.get("frame_id") != "map":
                    raise RuntimeError(f"named place {name!r} has no map-frame pose")
                if pose.get("mapping_session_id") != session["id"]:
                    raise RuntimeError(
                        f"named place {name!r} belongs to a different map session"
                    )
            exact_connectivity.update(
                exact_candidate_connectivity(
                    candidate_yaml,
                    candidate_image,
                    start_pose,
                    goal_pose,
                    inflation_radius_m=(
                        self.map_acceptance_policy.min_candidate_clearance_m
                    ),
                )
            )
            plans["forward"] = self.plan_only_evidence(
                self.map_acceptance_start_place,
                start_pose,
                self.map_acceptance_goal_place,
                goal_pose,
            )
            plans["reverse"] = self.plan_only_evidence(
                self.map_acceptance_goal_place,
                goal_pose,
                self.map_acceptance_start_place,
                start_pose,
            )
        except Exception as exc:
            exact_connectivity["error"] = str(exc)
            plans["forward"]["error"] = str(exc)
            plans["reverse"]["error"] = str(exc)

        evaluated_unix = time.time()
        with self.map_acceptance_lock:
            tf_evidence = self.map_tf_tracker.snapshot()
            footprint = (
                dict(self.global_footprint_observation)
                if self.global_footprint_observation is not None
                else {}
            )
        footprint["connected"] = bool(
            plans["forward"].get("passed") and plans["reverse"].get("passed")
        )
        footprint["validation"] = (
            "Nav2 ComputePathToPose with explicit endpoints and the live "
            "global costmap"
        )
        evidence = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "session_id": session["id"],
            "candidate_map_id": candidate_map_id,
            "evaluated_unix": evaluated_unix,
            "tf_jump": tf_evidence,
            "round_trip_closure": closure,
            "exact_candidate_connectivity": exact_connectivity,
            "full_footprint_connectivity": footprint,
            "bidirectional_plans": plans,
            "motion_dispatched": False,
        }
        failures = evaluate_acceptance_evidence(
            evidence,
            expected_session_id=session["id"],
            expected_candidate_map_id=candidate_map_id,
            session_started_unix=float(session["started_unix"]),
            evaluated_unix=evaluated_unix,
            policy=self.map_acceptance_policy,
        )
        evidence["decision"] = "rejected" if failures else "passed_pre_promotion"
        evidence["failures"] = failures
        report_path = candidate_prefix.with_suffix(".acceptance.json")
        self.atomic_write_json(report_path, evidence)
        if failures:
            raise RuntimeError(
                "candidate map rejected by pre-promotion safety gates: "
                + "; ".join(failures)
                + f"; accepted map preserved; report={report_path}"
            )
        return candidate_map_id

    def accept_saved_map(self, candidate_prefix: Path, session: dict) -> str:
        """Validate and atomically promote a candidate map; YAML is committed last."""
        candidate_yaml = candidate_prefix.with_suffix(".yaml")
        candidate_image = candidate_prefix.with_suffix(".pgm")
        if (
            not candidate_yaml.exists() or candidate_yaml.stat().st_size < 40
            or not candidate_image.exists() or candidate_image.stat().st_size < 100
        ):
            raise RuntimeError("candidate map is missing or too small; accepted map preserved")

        yaml_text = candidate_yaml.read_text(encoding="utf-8")
        lines = yaml_text.splitlines()
        image_line = next((line for line in lines if line.strip().startswith("image:")), None)
        if image_line is None:
            raise RuntimeError("candidate map YAML has no image; accepted map preserved")
        lines[lines.index(image_line)] = f"image: {self.map_prefix.name}.pgm"
        candidate_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")

        seed = json.loads(self.localization_seed_file.read_text(encoding="utf-8"))
        if seed.get("mapping_session_id") != session["id"]:
            raise RuntimeError(
                "localization seed does not belong to the candidate map session"
            )
        cleared = sanitize_saved_map(candidate_yaml, candidate_image, seed)
        self.get_logger().info(
            f"Saved-map footprint sanitation cleared {cleared} self-imprint cells"
        )

        # This is deliberately the last step before any accepted-map or
        # accepted-location write. A rejection leaves the rollback pair and
        # all map-bound coordinates untouched.
        candidate_map_id = self.validate_candidate_map(
            candidate_prefix,
            candidate_yaml,
            candidate_image,
            session,
            seed,
        )

        accepted_yaml = self.map_prefix.with_suffix(".yaml")
        accepted_image = self.map_prefix.with_suffix(".pgm")
        old_id = self.current_map_id()
        metadata_updates = self.prepare_map_bound_metadata(
            candidate_map_id, old_id, session
        )
        backup_dir = self.map_prefix.parent / "accepted_backups"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        map_id = transactionally_promote_map_pair(
            candidate_yaml=candidate_yaml,
            candidate_image=candidate_image,
            accepted_yaml=accepted_yaml,
            accepted_image=accepted_image,
            backup_dir=backup_dir,
            expected_map_id=candidate_map_id,
            backup_tag=f"{stamp}-{session['id'][:8]}",
            metadata_updates=metadata_updates,
        )
        return map_id

    def set_home(self) -> None:
        session = self.active_mapping_session()
        mapping_stack_active = all(
            subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", unit],
                check=False, timeout=4,
            ).returncode == 0
            for unit in ("atlas-slam-fast.service", "atlas-nav2.service")
        )
        if mapping_stack_active and not session:
            raise RuntimeError(
                "refusing to save a temporary SLAM pose without a versioned "
                "mapping session; use /atlas/start_manual_mapping first"
            )
        if not session and not mapping_stack_active:
            self.require_confident_localization()
        pose = self.stable_current_pose()
        if session:
            pose["mapping_session_id"] = session["id"]
        else:
            pose["map_id"] = self.current_map_id()
        self.atomic_write_json(self.home_file, pose)
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
        session = self.active_mapping_session()
        if session:
            pose["mapping_session_id"] = session["id"]
        self.atomic_write_json(self.localization_seed_file, pose)
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
        session = {
            "id": uuid.uuid4().hex,
            "state": "active",
            "started_unix": time.time(),
        }
        self.atomic_write_json(self.mapping_session_file, session)
        self.begin_map_acceptance_observation(session)
        # Start always records the present SLAM pose as mission home.
        try:
            self.set_home()
            self.pause_mapping_background()
            self.center_camera_for_navigation()
            result = subprocess.run(
                ["systemctl", "--user", "start", self.explore_unit],
                check=False, timeout=8, capture_output=True, text=True
            )
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "systemctl start failed")
            if subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", self.explore_unit],
                check=False, timeout=4,
            ).returncode != 0:
                raise RuntimeError("explore_lite exited instead of becoming active")
        except Exception:
            self.mapping_session_file.unlink(missing_ok=True)
            self.restore_mapping_background()
            raise
        self.status(f"EXPLORATION ACTIVE session={session['id'][:8]}")

    def start_manual_mapping(self) -> None:
        """Start a versioned SLAM session without autonomous wheel motion.

        This is the teaching mode used while Dhruv drives with the physical
        remote.  It deliberately leaves explore_lite stopped, but creates the
        same map-session identity used by the atomic map acceptance path.
        """
        session = {
            "id": uuid.uuid4().hex,
            "state": "starting",
            "mode": "manual_teaching",
            "started_unix": time.time(),
            "drive_ready": False,
        }
        self.atomic_write_json(self.mapping_session_file, session)
        self.start_mapping_recording(session["id"])
        self.status(
            f"MANUAL MAPPING PREPARING session={session['id'][:8]}; "
            "KEEP ATLAS STOPPED until MANUAL MAPPING ACTIVE"
        )
        try:
            self.ensure_mapping_stack()
            # Do not let a saved-map localization transform or the stack-change
            # discontinuity enter this session's quality evidence.  The
            # observation window starts only after fresh SLAM and Nav2 have
            # passed ensure_mapping_stack().
            session.update(
                {
                    "state": "active",
                    "drive_ready": True,
                    "ready_unix": time.time(),
                }
            )
            self.atomic_write_json(self.mapping_session_file, session)
            self.begin_map_acceptance_observation(session)
            self.set_home()
        except Exception:
            self.stop_mapping_recording()
            self.mapping_session_file.unlink(missing_ok=True)
            raise
        self.status(
            f"MANUAL MAPPING ACTIVE session={session['id'][:8]}; "
            "exploration stopped, operator has drive authority"
        )

    def center_camera_for_navigation(self) -> None:
        """Put the pan/tilt camera in its calibrated forward navigation pose."""
        self.camera_pan_home_us, self.camera_tilt_home_us = self.load_camera_home()
        for _ in range(3):
            self.camera_pan_pub.publish(Int32(data=self.camera_pan_home_us))
            self.camera_tilt_pub.publish(Int32(data=self.camera_tilt_home_us))
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
        # A stopped localization stack can leave a recent map->odom transform
        # in this node's TF buffer. Require a map received after this new SLAM
        # start request so that stale transform cannot become the session home.
        mapping_started_at = time.monotonic()
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
        # Smac Hybrid's first heuristic-table build can take 40-60 seconds on
        # the Orin while SLAM and costmaps start.  The previous 30-second
        # deadline falsely declared failure just before Nav2 became active.
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            ready = all(
                subprocess.run(
                    ["systemctl", "--user", "is-active", "--quiet", unit],
                    check=False, timeout=4,
                ).returncode == 0
                for unit in ("atlas-slam-fast.service", "atlas-nav2.service")
            )
            fresh_slam_map = self.mapping_map_received_at >= mapping_started_at
            if (
                ready
                and fresh_slam_map
                and self.nav.wait_for_server(timeout_sec=1.0)
            ):
                return
            time.sleep(1.0)
        raise RuntimeError("mapping stack did not become ready within 90 seconds")

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
        session = self.active_mapping_session()
        if session:
            # The live SLAM frame belongs to the candidate map, not the
            # previously accepted map. Defer binding until that candidate is
            # validated and atomically promoted by accept_saved_map().
            pose["mapping_session_id"] = session["id"]
        else:
            pose["map_id"] = self.current_map_id()
        places = self.load_named_places()
        places[name] = pose
        self.places_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.places_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(places, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.places_file)
        self.status(f"PLACE SAVED name={name} frame={pose['frame_id']} x={pose['x']:.2f} y={pose['y']:.2f}")

    def navigate_named_place(self, name: str) -> None:
        if self.safety_blocks_autonomy():
            raise RuntimeError(
                f"safety blocks named-place navigation: {self.safety_status}"
            )
        self.require_confident_localization()
        places = self.load_named_places()
        if name not in places:
            known = ", ".join(sorted(places)) or "none"
            raise RuntimeError(f"unknown named place {name!r}; known places: {known}")
        pose = places[name]
        if pose.get("frame_id") != "map":
            raise RuntimeError(f"named place {name!r} is not stored in the map frame")
        self.require_matching_map(pose, f"named place {name!r}")
        if self.dispatch_taught_route(name):
            return
        self.dispatch_pose_goal(pose, name)

    @staticmethod
    def yaw_quaternion(yaw: float) -> tuple:
        return (0.0, 0.0, math.sin(yaw * 0.5), math.cos(yaw * 0.5))

    def dispatch_taught_route(self, destination: str) -> bool:
        """Follow the commissioned room corridor instead of turning late.

        The route contains map poses learned from Dhruv's successful manual
        drive. Nav2 still plans and collision-checks each segment; no recorded
        motor command is replayed. If ATLAS is too far from the taught corridor
        we deliberately fall back to ordinary global planning.
        """
        normalized = destination.strip().lower()
        if normalized not in {"hall", "dhruv room"}:
            return False
        route_file = self.taught_routes_dir / "dhruv_room_to_hall.json"
        try:
            payload = json.loads(route_file.read_text(encoding="utf-8"))
            points = payload["points"]
        except (OSError, ValueError, KeyError, TypeError):
            return False
        route_map_id = payload.get("map_id")
        current_map_id = self.current_map_id()
        if not route_map_id or not current_map_id or route_map_id != current_map_id:
            self.get_logger().warn(
                "Taught route ignored: route map identity is missing or does not "
                "match the accepted occupancy map"
            )
            return False
        if normalized == "dhruv room":
            points = list(reversed(points))
        current = self.current_pose()
        nearest_index, nearest_point = min(
            enumerate(points),
            key=lambda pair: math.hypot(
                float(pair[1]["x"]) - float(current["x"]),
                float(pair[1]["y"]) - float(current["y"]),
            ),
        )
        nearest_distance = math.hypot(
            float(nearest_point["x"]) - float(current["x"]),
            float(nearest_point["y"]) - float(current["y"]),
        )
        if nearest_distance > 0.65:
            self.get_logger().warn(
                f"Taught route ignored: rover is {nearest_distance:.2f} m "
                "from the commissioned corridor"
            )
            return False
        remaining = points[nearest_index:]
        selected = []
        for point in remaining:
            if not selected:
                selected.append(point)
                continue
            distance = math.hypot(
                float(point["x"]) - float(selected[-1]["x"]),
                float(point["y"]) - float(selected[-1]["y"]),
            )
            yaw_change = abs(math.atan2(
                math.sin(float(point["yaw"]) - float(selected[-1]["yaw"])),
                math.cos(float(point["yaw"]) - float(selected[-1]["yaw"])),
            ))
            if distance >= 0.22 or yaw_change >= math.radians(10.0):
                selected.append(point)
        if remaining and selected[-1] is not remaining[-1]:
            selected.append(remaining[-1])
        # The closest recorded point is a corridor anchor, not a useful goal.
        if len(selected) > 1:
            selected = selected[1:]
        if not selected:
            return False
        self.dispatch_route_goal(selected, normalized, nearest_distance)
        return True

    def dispatch_route_goal(
        self, points: list, label: str, corridor_distance: float
    ) -> None:
        self.refresh_localization_before_motion()
        self.require_known_saved_map_start()
        self.require_scan_map_agreement()
        self.center_camera_for_navigation()
        if not self.nav_through.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("Nav2 NavigateThroughPoses action is unavailable")
        goal = NavigateThroughPoses.Goal()
        now = self.get_clock().now().to_msg()
        for point in points:
            pose = PoseStamped()
            pose.header.frame_id = "map"
            pose.header.stamp = now
            pose.pose.position.x = float(point["x"])
            pose.pose.position.y = float(point["y"])
            qx, qy, qz, qw = self.yaw_quaternion(float(point["yaw"]))
            pose.pose.orientation.x = qx
            pose.pose.orientation.y = qy
            pose.pose.orientation.z = qz
            pose.pose.orientation.w = qw
            goal.poses.append(pose)
        future = self.nav_through.send_goal_async(goal)
        future.add_done_callback(
            lambda done: self.named_goal_response(done, f"{label} taught-route")
        )
        self.status(
            f"TAUGHT ROUTE DISPATCHED name={label} waypoints={len(points)} "
            f"corridor_error={corridor_distance:.2f}m"
        )

    def dispatch_pose_goal(self, pose: dict, label: str) -> None:
        self.refresh_localization_before_motion()
        self.require_known_saved_map_start()
        self.require_scan_map_agreement()
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
        clients = [self.cancel_nav, self.cancel_nav_through]
        ready = [client for client in clients if client.wait_for_service(timeout_sec=1.0)]
        if not ready:
            self.get_logger().warn("Nav2 cancel services unavailable")
            return False
        request = CancelGoal.Request()
        request.goal_info.goal_id.uuid = [0] * 16
        request.goal_info.stamp.sec = 0
        request.goal_info.stamp.nanosec = 0
        futures = [client.call_async(request) for client in ready]
        deadline = time.monotonic() + 3.0
        while any(not future.done() for future in futures) and time.monotonic() < deadline:
            time.sleep(0.05)
        if any(not future.done() for future in futures):
            self.get_logger().error("Timed out waiting for Nav2 goal cancellation")
            return False
        responses = [future.result() for future in futures]
        if any(response is None for response in responses):
            self.get_logger().error("Nav2 goal cancellation returned no response")
            return False
        self.get_logger().info(
            "Nav2 cancel acknowledged; goals_canceling="
            f"{sum(len(response.goals_canceling) for response in responses)}"
        )
        return True

    def stop_exploration(self) -> None:
        try:
            self.zero_pub.publish(Twist())
            session = self.active_mapping_session()
            explore_active = subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", self.explore_unit],
                check=False, timeout=4,
            ).returncode == 0
            manual_session = bool(
                session and session.get("mode") == "manual_teaching"
            )
            if not session or (not explore_active and not manual_session):
                self.cancel_all_nav_goals()
                self.zero_pub.publish(Twist())
                self.status("MAPPING NOT ACTIVE; ACCEPTED MAP PRESERVED")
                return
            if explore_active:
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
            candidate_prefix = self.map_prefix.parent / (
                f".atlas_candidate_{session['id']}"
            )
            save = subprocess.run(
                [
                    "ros2", "run", "nav2_map_server", "map_saver_cli",
                    "-f", str(candidate_prefix),
                    "--ros-args", "-p", "save_map_timeout:=18.0",
                ],
                check=False, timeout=30, capture_output=True, text=True
            )
            self.zero_pub.publish(Twist())
            if save.returncode:
                raise RuntimeError(save.stderr.strip() or "map save failed; accepted map preserved")
            map_id = self.accept_saved_map(candidate_prefix, session)
            self.mapping_session_file.unlink(missing_ok=True)
            self.status(
                f"EXPLORATION STOPPED; MAP ACCEPTED id={map_id} "
                f"path={self.map_prefix}.yaml"
            )
        finally:
            self.stop_mapping_recording()
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
        self.refresh_localization_before_motion()
        self.require_known_saved_map_start()
        self.require_scan_map_agreement()
        if not self.nav.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("Nav2 NavigateToPose action is unavailable")
        pose = json.loads(self.home_file.read_text(encoding="utf-8"))
        self.require_matching_map(pose, "home pose")
        current = self.current_pose()
        if current.get("frame_id") == pose.get("frame_id", "map"):
            distance = math.hypot(
                float(current["x"]) - float(pose["x"]),
                float(current["y"]) - float(pose["y"]),
            )
            current_yaw = 2.0 * math.atan2(
                float(current["qz"]), float(current["qw"])
            )
            home_yaw = 2.0 * math.atan2(float(pose["qz"]), float(pose["qw"]))
            yaw_error = abs(math.degrees(self.angle_delta(current_yaw, home_yaw)))
            if (
                distance <= self.home_already_reached_distance_m
                and yaw_error <= self.home_already_reached_yaw_deg
            ):
                self.zero_pub.publish(Twist())
                self.status(
                    "HOME ALREADY REACHED; ROVER STOPPED "
                    f"error={distance:.3f}m heading={yaw_error:.1f}deg"
                )
                return
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
