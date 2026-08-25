#!/usr/bin/env python3
"""Run a bounded, evidence-recorded ATLAS return-home reliability campaign."""

import argparse
import json
import math
import re
import time
from pathlib import Path

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Float32, String
from std_srvs.srv import Empty, Trigger


class Campaign(Node):
    def __init__(self, home: dict, output: Path, offset_m: float):
        super().__init__("atlas_return_home_campaign")
        self.home = home
        self.output = output
        self.offset_m = offset_m
        self.pose = None
        self.amcl_samples = []
        self.safety = "UNKNOWN"
        self.battery = None
        self.mission = "UNKNOWN"
        self.mission_time = 0.0
        self.costmap = None
        self.costmap_time = 0.0
        self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", self.on_pose, 10)
        self.create_subscription(String, "/atlas/safety_status", self.on_safety, 10)
        self.create_subscription(String, "/atlas/mission_status", self.on_mission, 10)
        self.create_subscription(Float32, "/battery/percent", self.on_battery, 10)
        self.create_subscription(
            OccupancyGrid, "/global_costmap/costmap", self.on_costmap, 10
        )
        self.nav = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        self.nomotion = self.create_client(Empty, "/request_nomotion_update")
        self.return_home = self.create_client(Trigger, "/atlas/return_home")
        self.cancel = self.create_client(Trigger, "/atlas/cancel_navigation")
        self.zero = self.create_publisher(Twist, "/cmd_vel_nav", 10)

    def on_pose(self, msg):
        covariance = msg.pose.covariance
        pose = msg.pose.pose
        sample = {
            "t": time.monotonic(),
            "x": float(pose.position.x),
            "y": float(pose.position.y),
            "yaw": 2.0 * math.atan2(float(pose.orientation.z), float(pose.orientation.w)),
            "xy_std": math.sqrt(max(0.0, float(covariance[0])) + max(0.0, float(covariance[7]))),
            "yaw_std_deg": math.degrees(math.sqrt(max(0.0, float(covariance[35])))),
        }
        self.pose = sample
        self.amcl_samples.append(sample)

    def on_safety(self, msg):
        self.safety = msg.data.strip()

    def on_battery(self, msg):
        self.battery = float(msg.data)

    def on_mission(self, msg):
        self.mission = msg.data.strip()
        self.mission_time = time.monotonic()

    def on_costmap(self, msg):
        self.costmap = msg
        self.costmap_time = time.monotonic()

    def spin_for(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)

    @staticmethod
    def angle_delta(first, second):
        return math.atan2(math.sin(second - first), math.cos(second - first))

    def stationary_gate(self, duration=10.0):
        self.amcl_samples = []
        deadline = time.monotonic() + duration
        next_update = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_update and self.nomotion.service_is_ready():
                self.nomotion.call_async(Empty.Request())
                next_update = now + 2.0
            rclpy.spin_once(self, timeout_sec=0.1)
        samples = self.amcl_samples
        if len(samples) < 4:
            return False, {"reason": "insufficient AMCL samples", "count": len(samples)}
        maximum_shift = max(
            math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            for index, a in enumerate(samples)
            for b in samples[index + 1:]
        )
        reference = samples[0]["yaw"]
        yaws = [self.angle_delta(reference, item["yaw"]) for item in samples]
        maximum_yaw = math.degrees(max(yaws) - min(yaws))
        last = samples[-1]
        evidence = {
            "samples": len(samples),
            "pose_shift_m": maximum_shift,
            "heading_shift_deg": maximum_yaw,
            "xy_std_m": last["xy_std"],
            "yaw_std_deg": last["yaw_std_deg"],
            "pose": last,
        }
        passed = (
            maximum_shift <= 0.10
            and maximum_yaw <= 5.0
            and last["xy_std"] <= 0.60
            and last["yaw_std_deg"] <= 25.0
        )
        return passed, evidence

    def footprint_gate(self):
        """Reject a goal if the exact 50 x 36 cm body starts in lethal space."""
        if self.pose is None or self.costmap is None:
            return False, {"reason": "pose or global costmap unavailable"}
        age = time.monotonic() - self.costmap_time
        if age > 3.0:
            return False, {"reason": "global costmap stale", "age_s": age}
        grid = self.costmap
        resolution = float(grid.info.resolution)
        origin = grid.info.origin.position
        width, height = int(grid.info.width), int(grid.info.height)
        yaw = self.pose["yaw"]
        cosine, sine = math.cos(yaw), math.sin(yaw)
        radius = int(math.ceil(math.hypot(0.25, 0.18) / resolution))
        center_col = int(math.floor((self.pose["x"] - origin.x) / resolution))
        center_row = int(math.floor((self.pose["y"] - origin.y) / resolution))
        lethal = unknown = checked = 0
        for row in range(center_row - radius, center_row + radius + 1):
            if row < 0 or row >= height:
                continue
            for col in range(center_col - radius, center_col + radius + 1):
                if col < 0 or col >= width:
                    continue
                wx = origin.x + (col + 0.5) * resolution
                wy = origin.y + (row + 0.5) * resolution
                dx, dy = wx - self.pose["x"], wy - self.pose["y"]
                local_x = cosine * dx + sine * dy
                local_y = -sine * dx + cosine * dy
                if abs(local_x) > 0.25 or abs(local_y) > 0.18:
                    continue
                checked += 1
                value = int(grid.data[row * width + col])
                lethal += value >= 100
                unknown += value < 0
        evidence = {
            "costmap_age_s": age,
            "checked_cells": checked,
            "lethal_cells": lethal,
            "unknown_cells": unknown,
        }
        return checked > 0 and lethal == 0 and unknown == 0, evidence

    def safe_to_start(self):
        return "READY" in self.safety.upper() and "STOPPED" in self.safety.upper()

    def send_offset(self):
        if not self.nav.wait_for_server(timeout_sec=10.0):
            return False, "NavigateToPose unavailable"
        yaw = 2.0 * math.atan2(float(self.home["qz"]), float(self.home["qw"]))
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(self.home["x"]) + self.offset_m * math.cos(yaw)
        goal.pose.pose.position.y = float(self.home["y"]) + self.offset_m * math.sin(yaw)
        goal.pose.pose.orientation.x = float(self.home["qx"])
        goal.pose.pose.orientation.y = float(self.home["qy"])
        goal.pose.pose.orientation.z = float(self.home["qz"])
        goal.pose.pose.orientation.w = float(self.home["qw"])
        sent = self.nav.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, sent, timeout_sec=12.0)
        handle = sent.result() if sent.done() else None
        if handle is None or not handle.accepted:
            return False, "offset goal rejected"
        result = handle.get_result_async()
        deadline = time.monotonic() + 45.0
        while not result.done() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        if not result.done():
            handle.cancel_goal_async()
            return False, "offset goal timeout"
        status = int(result.result().status)
        return status == GoalStatus.STATUS_SUCCEEDED, f"offset status={status}"

    def request_return(self):
        if not self.return_home.wait_for_service(timeout_sec=8.0):
            return False, "return-home service unavailable"
        requested = time.monotonic()
        future = self.return_home.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
        if not future.done() or not future.result().success:
            return False, "return-home request rejected"
        deadline = time.monotonic() + 60.0
        finished_at = None
        return_started = False
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.mission_time < requested:
                continue
            upper = self.mission.upper()
            if (
                "QUEUED RETURN-HOME" in upper
                or "RETURN HOME GOAL DISPATCHED" in upper
                or "RETURN HOME ACCEPTED" in upper
            ):
                return_started = True
            if return_started and (
                "RETURN HOME VERIFIED" in upper or "HOME ALREADY REACHED" in upper
            ):
                return True, self.mission
            if return_started and ("ERROR" in upper or "REJECTED" in upper):
                return False, self.mission
            if return_started and "RETURN HOME FINISHED STATUS=4" in upper:
                finished_at = finished_at or time.monotonic()
                if time.monotonic() - finished_at > 8.0:
                    return False, "return succeeded but verification missing"
            elif return_started and "RETURN HOME FINISHED" in upper:
                return False, self.mission
        return False, "return-home timeout"

    def stop(self):
        if self.cancel.service_is_ready():
            self.cancel.call_async(Trigger.Request())
        for _ in range(8):
            self.zero.publish(Twist())
            rclpy.spin_once(self, timeout_sec=0.05)

    def record(self, result):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, separators=(",", ":")) + "\n")
        print(json.dumps(result), flush=True)

    def run(self, cycles, minimum_battery):
        self.spin_for(3.0)
        for cycle in range(1, cycles + 1):
            result = {"cycle": cycle, "started_unix": time.time()}
            if self.battery is not None and self.battery < minimum_battery:
                result.update(ok=False, stage="precheck", detail="low battery", battery=self.battery)
                self.record(result)
                return 2
            if not self.safe_to_start():
                result.update(ok=False, stage="precheck", detail=self.safety, battery=self.battery)
                self.record(result)
                return 3
            stable, evidence = self.stationary_gate()
            result["pre_offset_localization"] = evidence
            if not stable:
                result.update(ok=False, stage="localization", detail="pre-offset unstable")
                self.record(result)
                return 4
            clear, evidence = self.footprint_gate()
            result["pre_offset_footprint"] = evidence
            if not clear:
                result.update(ok=False, stage="costmap", detail="start footprint blocked")
                self.stop(); self.record(result)
                return 4
            moved, detail = self.send_offset()
            result["offset"] = detail
            if not moved:
                result.update(ok=False, stage="offset", detail=detail)
                self.stop(); self.record(result)
                return 5
            stable, evidence = self.stationary_gate()
            result["pre_return_localization"] = evidence
            if not stable:
                result.update(ok=False, stage="localization", detail="pre-return unstable")
                self.stop(); self.record(result)
                return 6
            clear, evidence = self.footprint_gate()
            result["pre_return_footprint"] = evidence
            if not clear:
                result.update(ok=False, stage="costmap", detail="return footprint blocked")
                self.stop(); self.record(result)
                return 6
            if not self.safe_to_start():
                result.update(ok=False, stage="pre-return safety", detail=self.safety)
                self.stop(); self.record(result)
                return 6
            returned, detail = self.request_return()
            result["return"] = detail
            if not returned:
                result.update(ok=False, stage="return", detail=detail)
                self.stop(); self.record(result)
                return 7
            self.spin_for(3.0)
            result.update(
                ok=True,
                completed_unix=time.time(),
                battery=self.battery,
                safety=self.safety,
                final_pose=self.pose,
            )
            self.record(result)
        self.stop()
        return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--offset", type=float, default=0.20)
    parser.add_argument("--minimum-battery", type=float, default=30.0)
    parser.add_argument("--home", type=Path, default=Path.home() / ".config/project_atlas/home_pose.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    home = json.loads(args.home.read_text(encoding="utf-8"))
    rclpy.init()
    node = Campaign(home, args.output, args.offset)
    try:
        raise SystemExit(node.run(args.cycles, args.minimum_battery))
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
