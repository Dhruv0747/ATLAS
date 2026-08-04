#!/usr/bin/env python3
"""Relay Foxglove PoseStamped goals to the Nav2 NavigateToPose action."""

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node


class FoxgloveNavGoalBridge(Node):
    def __init__(self) -> None:
        super().__init__("foxglove_nav_goal_bridge")
        self._client = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self._active_goal = None
        self.create_subscription(
            PoseStamped, "/goal_pose", self._receive_goal, 10
        )
        self.get_logger().info(
            "Ready: Foxglove PoseStamped /goal_pose -> Nav2 /navigate_to_pose"
        )

    def _receive_goal(self, pose: PoseStamped) -> None:
        if not pose.header.frame_id:
            pose.header.frame_id = "map"
        if pose.header.frame_id != "map":
            self.get_logger().error(
                f"Rejected goal in frame '{pose.header.frame_id}'; use map"
            )
            return
        pose.header.stamp = self.get_clock().now().to_msg()

        if not self._client.wait_for_server(timeout_sec=2.0):
            self.get_logger().error("Rejected goal: Nav2 action server unavailable")
            return

        goal = NavigateToPose.Goal()
        goal.pose = pose
        future = self._client.send_goal_async(goal)
        future.add_done_callback(self._goal_response)

    def _goal_response(self, future) -> None:
        handle = future.result()
        if not handle.accepted:
            self.get_logger().warning("Nav2 rejected the Foxglove goal")
            return
        self._active_goal = handle
        self.get_logger().info("Nav2 accepted the Foxglove goal")
        result = handle.get_result_async()
        result.add_done_callback(self._goal_finished)

    def _goal_finished(self, future) -> None:
        self.get_logger().info(
            f"Foxglove navigation finished with status {future.result().status}"
        )
        self._active_goal = None


def main() -> None:
    rclpy.init()
    node = FoxgloveNavGoalBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
