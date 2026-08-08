#!/usr/bin/env python3
"""Non-blocking Foxglove mission bindings for Project ATLAS."""

from concurrent.futures import ThreadPoolExecutor
import json
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
from std_msgs.msg import Empty, String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


class AtlasMissionControl(Node):
    """Expose topic and service controls without blocking the ROS executor."""

    def __init__(self):
        super().__init__("atlas_mission_control")
        self.declare_parameter(
            "map_prefix", "/home/jetson/project_atlas/maps/atlas_latest"
        )
        self.declare_parameter("explore_unit", "atlas-explore.service")
        self.home_file = Path.home() / ".config/project_atlas/home_pose.json"
        self.map_prefix = Path(str(self.get_parameter("map_prefix").value))
        self.map_prefix.parent.mkdir(parents=True, exist_ok=True)
        self.explore_unit = str(self.get_parameter("explore_unit").value)

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.nav = ActionClient(self, NavigateToPose, "/navigate_to_pose")
        self.cancel_nav = self.create_client(
            CancelGoal, "/navigate_to_pose/_action/cancel_goal"
        )
        self.zero_pub = self.create_publisher(Twist, "/cmd_vel_nav", 10)
        self.status_pub = self.create_publisher(
            String, "/atlas/mission_status", 10
        )
        self.current_status = "STARTING"
        self.create_timer(1.0, self.publish_current_status)

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
        for topic, callback in bindings.items():
            self.create_subscription(Empty, topic, callback, 10)

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
        pose = self.current_pose()
        self.home_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.home_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(pose, indent=2), encoding="utf-8")
        temporary.replace(self.home_file)
        self.status(
            f"HOME SAVED frame={pose['frame_id']} "
            f"x={pose['x']:.2f} y={pose['y']:.2f}"
        )

    def start_exploration(self) -> None:
        # Start always records the present SLAM pose as mission home.
        self.set_home()
        result = subprocess.run(
            ["systemctl", "--user", "start", self.explore_unit],
            check=False, timeout=8, capture_output=True, text=True
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "systemctl start failed")
        self.status("EXPLORATION ACTIVE")

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
        self.zero_pub.publish(Twist())
        map_yaml = self.map_prefix.with_suffix(".yaml")
        previous_mtime = map_yaml.stat().st_mtime if map_yaml.exists() else 0.0
        result = subprocess.run(
            ["systemctl", "--user", "stop", self.explore_unit],
            check=False, timeout=15, capture_output=True, text=True
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "systemctl stop failed")
        if not self.cancel_all_nav_goals():
            raise RuntimeError("exploration stopped but Nav2 goal cancellation was not acknowledged")
        self.zero_pub.publish(Twist())

        # ExecStopPost normally saves the map. Avoid racing it with a second
        # map_saver; only run the explicit saver when no fresh YAML appeared.
        saved_by_unit = map_yaml.exists() and map_yaml.stat().st_mtime > previous_mtime
        if not saved_by_unit:
            save = subprocess.run(
                [
                    "ros2", "run", "nav2_map_server", "map_saver_cli",
                    "-f", str(self.map_prefix)
                ],
                check=False, timeout=30, capture_output=True, text=True
            )
            self.zero_pub.publish(Twist())
            if save.returncode:
                raise RuntimeError(save.stderr.strip() or "map save failed")
        if not map_yaml.exists():
            raise RuntimeError("map saver returned success but YAML is absent")
        self.status(f"EXPLORATION STOPPED; MAP SAVED {self.map_prefix}.yaml")

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
        if not self.nav.wait_for_server(timeout_sec=3.0):
            raise RuntimeError("Nav2 NavigateToPose action is unavailable")
        pose = json.loads(self.home_file.read_text(encoding="utf-8"))
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
        future.add_done_callback(self.home_goal_response)
        self.status("RETURN HOME GOAL DISPATCHED")

    def home_goal_response(self, future) -> None:
        try:
            handle = future.result()
            if not handle.accepted:
                self.status("RETURN HOME REJECTED")
                return
            self.status("RETURN HOME ACCEPTED")
            result = handle.get_result_async()
            result.add_done_callback(
                lambda done: self.status(
                    f"RETURN HOME FINISHED status={done.result().status}"
                )
            )
        except Exception as exc:
            self.error("return-home action", exc)

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
