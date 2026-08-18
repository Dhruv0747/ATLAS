#!/usr/bin/env python3
"""Ask Nav2 to plan to a saved ATLAS place without dispatching motion."""

import argparse
import json
import math
from pathlib import Path

import rclpy
from nav2_msgs.action import ComputePathToPose
from rclpy.action import ActionClient
from rclpy.node import Node


PLACES_FILE = Path.home() / ".config/project_atlas/named_places.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    args = parser.parse_args()
    places = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
    if args.name not in places:
        raise RuntimeError(f"unknown place: {args.name}")
    pose = places[args.name]

    rclpy.init()
    node = Node("atlas_named_path_validator")
    client = ActionClient(node, ComputePathToPose, "/compute_path_to_pose")
    if not client.wait_for_server(timeout_sec=8.0):
        raise RuntimeError("Nav2 path planner is unavailable")
    goal = ComputePathToPose.Goal()
    goal.goal.header.frame_id = "map"
    goal.goal.header.stamp = node.get_clock().now().to_msg()
    goal.goal.pose.position.x = float(pose["x"])
    goal.goal.pose.position.y = float(pose["y"])
    goal.goal.pose.position.z = float(pose.get("z", 0.0))
    goal.goal.pose.orientation.x = float(pose["qx"])
    goal.goal.pose.orientation.y = float(pose["qy"])
    goal.goal.pose.orientation.z = float(pose["qz"])
    goal.goal.pose.orientation.w = float(pose["qw"])
    goal.use_start = False

    send_future = client.send_goal_async(goal)
    rclpy.spin_until_future_complete(node, send_future, timeout_sec=10.0)
    handle = send_future.result()
    if handle is None or not handle.accepted:
        raise RuntimeError("Nav2 rejected the planning request")
    result_future = handle.get_result_async()
    rclpy.spin_until_future_complete(node, result_future, timeout_sec=15.0)
    wrapped = result_future.result()
    if wrapped is None:
        raise RuntimeError("Nav2 planning timed out")
    poses = wrapped.result.path.poses
    if not poses:
        raise RuntimeError("Nav2 returned no collision-free path")
    length = 0.0
    for first, second in zip(poses, poses[1:]):
        length += math.hypot(
            second.pose.position.x - first.pose.position.x,
            second.pose.position.y - first.pose.position.y,
        )
    print(json.dumps({
        "name": args.name,
        "status": int(wrapped.status),
        "poses": len(poses),
        "path_length_m": round(length, 3),
        "goal_x_m": round(float(pose["x"]), 3),
        "goal_y_m": round(float(pose["y"]), 3),
    }, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
