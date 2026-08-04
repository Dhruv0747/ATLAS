#!/usr/bin/env python3
"""Publish concise, operator-friendly autonomy and obstacle status for ATLAS."""

import json
import math
import time

import rclpy
from action_msgs.msg import GoalStatusArray
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import OccupancyGrid, Odometry, Path
from nav2_msgs.msg import BehaviorTreeLog
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, LaserScan
from std_msgs.msg import Float32, String


class AtlasSafetyStatus(Node):
    def __init__(self):
        super().__init__("atlas_safety_status")
        self.last_scan = 0.0
        self.last_map = 0.0
        self.last_plan = 0.0
        self.last_odom = 0.0
        self.last_ai_camera = 0.0
        self.last_goal_status = 0.0
        self.last_bt_action = 0.0
        self.last_map_metrics = 0.0
        self.front_lidar = math.inf
        self.left_lidar = math.inf
        self.right_lidar = math.inf
        self.front_ultrasonic = math.inf
        self.left_ultrasonic = math.inf
        self.right_ultrasonic = math.inf
        self.plan_points = 0
        self.map_width_m = 0.0
        self.map_height_m = 0.0
        self.map_known_pct = 0.0
        self.map_occupied_cells = 0
        self.pose_x = 0.0
        self.pose_y = 0.0
        self.linear_speed = 0.0
        self.angular_speed = 0.0
        self.goal_status = 0
        self.bt_action = ""
        self.motion_safety = ""
        self.odom_source = "unknown"
        self.drive_mode = "STOPPED"
        self.mission_status = "READY"

        self.create_subscription(LaserScan, "/scan", self.on_scan, 10)
        self.create_subscription(OccupancyGrid, "/map", self.on_map, 10)
        self.create_subscription(Path, "/plan", self.on_plan, 10)
        self.create_subscription(Odometry, "/odom", self.on_odom, 10)
        self.create_subscription(
            Float32, "/ultrasonic/front_mm", self.on_ultrasonic, 10
        )
        self.create_subscription(
            Float32, "/ultrasonic/left_mm",
            lambda msg: self.on_side_ultrasonic("left", msg), 10
        )
        self.create_subscription(
            Float32, "/ultrasonic/right_mm",
            lambda msg: self.on_side_ultrasonic("right", msg), 10
        )
        self.create_subscription(
            String, "/atlas/motion_safety", self.on_motion_safety, 10
        )
        self.create_subscription(
            String, "/yahboom/odom_source", self.on_odom_source, 10
        )
        self.create_subscription(String, "/atlas/drive_mode", self.on_mode, 10)
        self.create_subscription(
            String, "/atlas/mission_status", self.on_mission, 10
        )
        self.create_subscription(
            GoalStatusArray,
            "/navigate_to_pose/_action/status",
            self.on_goal_status,
            10,
        )
        self.create_subscription(
            BehaviorTreeLog,
            "/behavior_tree_log",
            self.on_behavior_tree_log,
            10,
        )
        self.create_subscription(
            CompressedImage,
            "/camera/detections/compressed",
            self.on_ai_camera,
            10,
        )
        self.status_pub = self.create_publisher(String, "/atlas/safety_status", 10)
        self.phase_pub = self.create_publisher(
            String, "/atlas/autonomy_phase", 10
        )
        self.state_pub = self.create_publisher(
            String, "/atlas/autonomy_state", 10
        )
        self.diagnostics_pub = self.create_publisher(
            DiagnosticArray, "/diagnostics", 10
        )
        self.create_timer(0.25, self.publish_status)
        self.get_logger().info("ATLAS operator safety-status monitor ready")

    def on_scan(self, msg: LaserScan) -> None:
        self.last_scan = time.monotonic()
        nearest = {"front": math.inf, "left": math.inf, "right": math.inf}
        for index, value in enumerate(msg.ranges):
            angle = msg.angle_min + index * msg.angle_increment
            if not math.isfinite(value) or not msg.range_min <= value <= msg.range_max:
                continue
            degrees = math.degrees(angle)
            if abs(degrees) <= 35.0:
                nearest["front"] = min(nearest["front"], value)
            elif 35.0 < degrees <= 120.0:
                nearest["left"] = min(nearest["left"], value)
            elif -120.0 <= degrees < -35.0:
                nearest["right"] = min(nearest["right"], value)
        clear_value = float(msg.range_max)
        self.front_lidar = (
            nearest["front"] if math.isfinite(nearest["front"]) else clear_value
        )
        self.left_lidar = (
            nearest["left"] if math.isfinite(nearest["left"]) else clear_value
        )
        self.right_lidar = (
            nearest["right"] if math.isfinite(nearest["right"]) else clear_value
        )

    def on_map(self, msg: OccupancyGrid) -> None:
        now = time.monotonic()
        self.last_map = now
        self.map_width_m = float(msg.info.width) * float(msg.info.resolution)
        self.map_height_m = float(msg.info.height) * float(msg.info.resolution)
        if now - self.last_map_metrics < 1.0:
            return
        self.last_map_metrics = now
        total = len(msg.data)
        known = sum(1 for value in msg.data if value >= 0)
        self.map_occupied_cells = sum(1 for value in msg.data if value >= 65)
        self.map_known_pct = 100.0 * known / total if total else 0.0

    def on_plan(self, msg: Path) -> None:
        self.last_plan = time.monotonic()
        self.plan_points = len(msg.poses)

    def on_odom(self, msg: Odometry) -> None:
        self.last_odom = time.monotonic()
        self.pose_x = float(msg.pose.pose.position.x)
        self.pose_y = float(msg.pose.pose.position.y)
        self.linear_speed = float(msg.twist.twist.linear.x)
        self.angular_speed = float(msg.twist.twist.angular.z)

    def on_ultrasonic(self, msg: Float32) -> None:
        self.front_ultrasonic = float(msg.data) / 1000.0

    def on_side_ultrasonic(self, side: str, msg: Float32) -> None:
        value = float(msg.data) / 1000.0
        if side == "left":
            self.left_ultrasonic = value
        else:
            self.right_ultrasonic = value

    def on_motion_safety(self, msg: String) -> None:
        self.motion_safety = msg.data

    def on_odom_source(self, msg: String) -> None:
        self.odom_source = msg.data

    def on_mode(self, msg: String) -> None:
        self.drive_mode = msg.data

    def on_mission(self, msg: String) -> None:
        self.mission_status = msg.data

    def on_goal_status(self, msg: GoalStatusArray) -> None:
        if not msg.status_list:
            return
        self.goal_status = int(msg.status_list[-1].status)
        self.last_goal_status = time.monotonic()

    def on_behavior_tree_log(self, msg: BehaviorTreeLog) -> None:
        interesting = {
            "computepath": "PLANNING PATH",
            "followpath": "FOLLOWING PATH",
            "clear": "CLEARING COSTMAP",
            "backup": "REVERSING 0.15 m",
            "wait": "WAITING FOR OBSTACLE",
        }
        for event in msg.event_log:
            node_key = event.node_name.lower().replace("_", "")
            if event.current_status == "RUNNING":
                for keyword, label in interesting.items():
                    if keyword in node_key:
                        self.bt_action = label
                        self.last_bt_action = time.monotonic()
                        break

    def on_ai_camera(self, _msg: CompressedImage) -> None:
        self.last_ai_camera = time.monotonic()

    @staticmethod
    def goal_name(value: int) -> str:
        return {
            0: "NONE",
            1: "ACCEPTED",
            2: "EXECUTING",
            3: "CANCELING",
            4: "SUCCEEDED",
            5: "CANCELED",
            6: "ABORTED",
        }.get(value, f"UNKNOWN({value})")

    def classify(self):
        now = time.monotonic()
        if now - self.last_scan > 1.5:
            return 2, "FAULT", "STOP: LIDAR DATA LOST", "Check RPLIDAR USB/power"
        if now - self.last_odom > 1.5:
            return (
                2,
                "FAULT",
                "STOP: WHEEL ODOMETRY / TF LOST",
                "Motor-base watchdog is recovering the driver",
            )
        if self.odom_source == "commanded_encoder_stale":
            return (
                2,
                "TRACTION_FAULT",
                "STOP: DRIVE COMMANDED BUT ENCODERS NOT MOVING",
                "Check wheel contact, motor power, and encoder cable",
            )
        if now - self.last_map > 3.0:
            return 2, "FAULT", "STOP: SLAM MAP DATA LOST", "Restart SLAM"

        nearest = min(self.front_lidar, self.front_ultrasonic)
        if nearest < 0.20:
            return (
                2,
                "BLOCKED",
                f"BLOCKED: OBSTACLE {nearest:.2f} m - REPLANNING",
                "Stop, update costmap, and search for another car-like path",
            )
        if self.motion_safety.startswith("AUTONOMY BLOCKED"):
            return 2, "BLOCKED", self.motion_safety, "Wait or replan around obstacle"
        if now - self.last_bt_action < 2.0 and self.bt_action:
            phase = (
                "RECOVERING"
                if self.bt_action in {
                    "CLEARING COSTMAP",
                    "REVERSING 0.15 m",
                    "WAITING FOR OBSTACLE",
                }
                else "NAVIGATING"
            )
            return 1 if phase == "RECOVERING" else 0, phase, self.bt_action, (
                "Nav2 behavior tree is choosing the next safe action"
            )
        if nearest < 0.35:
            return (
                1,
                "TIGHT_CLEARANCE",
                f"CAUTION: FRONT CLEARANCE {nearest:.2f} m",
                "Proceed slowly while preserving the 10 cm footprint margin",
            )
        if self.drive_mode == "NAV2":
            if now - self.last_plan > 4.0:
                return (
                    1,
                    "PLANNING",
                    "AUTONOMY: SEARCHING FOR A SAFE CAR-LIKE PATH",
                    "Hybrid-A* is evaluating forward and reverse routes",
                )
            return (
                0,
                "NAVIGATING",
                f"AUTONOMY: DRIVING - FRONT {nearest:.2f} m CLEAR",
                "Following the current collision-checked path",
            )
        if "EXPLORATION" in self.mission_status.upper():
            return (
                0,
                "EXPLORING",
                "AUTONOMY: EVALUATING NEXT FRONTIER",
                "Explore Lite is selecting the next unmapped reachable area",
            )
        return (
            0,
            "READY",
            f"READY: {self.drive_mode} - FRONT {nearest:.2f} m CLEAR",
            "Waiting for manual control, a navigation goal, or auto-map start",
        )

    def publish_status(self) -> None:
        now = time.monotonic()
        level, phase, text, decision = self.classify()
        self.status_pub.publish(String(data=text))
        self.phase_pub.publish(String(data=phase))
        state = {
            "phase": phase,
            "severity": ["OK", "WARN", "ERROR"][min(level, 2)],
            "summary": text,
            "decision": decision,
            "drive_mode": self.drive_mode,
            "mission": self.mission_status,
            "goal": self.goal_name(self.goal_status),
            "behavior": self.bt_action
            if now - self.last_bt_action < 2.0
            else "IDLE",
            "pose": {
                "x_m": round(self.pose_x, 3),
                "y_m": round(self.pose_y, 3),
                "linear_mps": round(self.linear_speed, 3),
                "angular_rps": round(self.angular_speed, 3),
            },
            "clearance_m": {
                "front": round(min(self.front_lidar, self.front_ultrasonic), 3),
                "left": round(min(self.left_lidar, self.left_ultrasonic), 3),
                "right": round(min(self.right_lidar, self.right_ultrasonic), 3),
            },
            "map": {
                "width_m": round(self.map_width_m, 2),
                "height_m": round(self.map_height_m, 2),
                "known_percent": round(self.map_known_pct, 1),
                "occupied_cells": self.map_occupied_cells,
                "plan_points": self.plan_points,
            },
            "sensors": {
                "lidar": "ONLINE" if now - self.last_scan <= 1.5 else "LOST",
                "odometry": "ONLINE" if now - self.last_odom <= 1.5 else "LOST",
                "slam_map": "ONLINE" if now - self.last_map <= 3.0 else "LOST",
                "ai_camera": "ONLINE"
                if now - self.last_ai_camera <= 2.5
                else "LOST",
            },
            "odometry_source": self.odom_source,
        }
        self.state_pub.publish(
            String(data=json.dumps(state, separators=(",", ":")))
        )

        array = DiagnosticArray()
        array.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        # ROS 2 Humble's generated Python binding represents uint8 as one byte.
        status.level = bytes([level])
        status.name = "Project ATLAS/Autonomy Safety"
        status.hardware_id = "project-atlas-jetson"
        status.message = text
        status.values = [
            KeyValue(key="autonomy_phase", value=phase),
            KeyValue(key="decision", value=decision),
            KeyValue(key="drive_mode", value=self.drive_mode),
            KeyValue(key="mission_status", value=self.mission_status),
            KeyValue(key="goal_status", value=self.goal_name(self.goal_status)),
            KeyValue(
                key="behavior",
                value=self.bt_action
                if now - self.last_bt_action < 2.0
                else "IDLE",
            ),
            KeyValue(
                key="front_lidar_m",
                value="unknown"
                if not math.isfinite(self.front_lidar)
                else f"{self.front_lidar:.3f}",
            ),
            KeyValue(
                key="front_ultrasonic_m",
                value="unknown"
                if not math.isfinite(self.front_ultrasonic)
                else f"{self.front_ultrasonic:.3f}",
            ),
            KeyValue(key="left_ultrasonic_m", value=f"{self.left_ultrasonic:.3f}"),
            KeyValue(key="right_ultrasonic_m", value=f"{self.right_ultrasonic:.3f}"),
            KeyValue(key="odometry_source", value=self.odom_source),
            KeyValue(key="map_known_percent", value=f"{self.map_known_pct:.1f}"),
            KeyValue(key="plan_points", value=str(self.plan_points)),
            KeyValue(
                key="ai_camera",
                value="ONLINE" if now - self.last_ai_camera <= 2.5 else "LOST",
            ),
        ]
        array.status = [status]
        self.diagnostics_pub.publish(array)


def main():
    rclpy.init()
    node = AtlasSafetyStatus()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
