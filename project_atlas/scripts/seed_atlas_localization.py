#!/usr/bin/env python3
"""Seed AMCL from a saved map-frame pose without moving the rover."""

import argparse
import json
from pathlib import Path
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from nav2_msgs.srv import SetInitialPose
from rclpy.node import Node
from std_srvs.srv import Empty


POSE_FILES = (
    Path.home() / ".config/project_atlas/localization_seed_pose.json",
    Path.home() / ".config/project_atlas/home_pose.json",
)
PLACES_FILE = Path.home() / ".config/project_atlas/named_places.json"


def load_pose(place=None):
    if place is not None:
        places = json.loads(PLACES_FILE.read_text(encoding="utf-8"))
        key = place.strip().lower().replace("_", " ")
        if key not in places:
            raise RuntimeError(f"unknown named place: {place!r}")
        pose = places[key]
        POSE_FILES[0].parent.mkdir(parents=True, exist_ok=True)
        temporary = POSE_FILES[0].with_suffix(".tmp")
        temporary.write_text(json.dumps(pose, indent=2), encoding="utf-8")
        temporary.replace(POSE_FILES[0])
        return pose
    pose_file = next((path for path in POSE_FILES if path.exists()), None)
    if pose_file is None:
        raise RuntimeError("no localization seed or home pose is saved")
    pose = json.loads(pose_file.read_text(encoding="utf-8"))
    if pose.get("frame_id") != "map":
        raise RuntimeError(f"saved pose is not in map frame: {pose.get('frame_id')!r}")
    for field in ("x", "y", "qx", "qy", "qz", "qw"):
        if field not in pose:
            raise RuntimeError(f"saved pose is missing {field}")
    return pose


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--place", help="named map place to seed and persist")
    args = parser.parse_args()
    pose = load_pose(args.place)
    rclpy.init()
    node = Node("atlas_localization_seeder")
    publisher = node.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
    pose_client = node.create_client(SetInitialPose, "/set_initial_pose")
    update_client = node.create_client(Empty, "/request_nomotion_update")
    latest_odom_stamp = {"value": None}

    def receive_odom(msg: Odometry):
        latest_odom_stamp["value"] = msg.header.stamp

    odom_subscription = node.create_subscription(
        Odometry, "/odom", receive_odom, 10
    )
    message = PoseWithCovarianceStamped()
    message.header.frame_id = "map"
    message.pose.pose.position.x = float(pose["x"])
    message.pose.pose.position.y = float(pose["y"])
    message.pose.pose.position.z = float(pose.get("z", 0.0))
    message.pose.pose.orientation.x = float(pose["qx"])
    message.pose.pose.orientation.y = float(pose["qy"])
    message.pose.pose.orientation.z = float(pose["qz"])
    message.pose.pose.orientation.w = float(pose["qw"])
    message.pose.covariance[0] = 0.25
    message.pose.covariance[7] = 0.25
    message.pose.covariance[35] = 0.068

    deadline = time.monotonic() + 20.0
    while publisher.get_subscription_count() == 0 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if publisher.get_subscription_count() == 0:
        raise RuntimeError("AMCL is not subscribed to /initialpose")

    odom_deadline = time.monotonic() + 8.0
    while latest_odom_stamp["value"] is None and time.monotonic() < odom_deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if latest_odom_stamp["value"] is None:
        raise RuntimeError("no odometry timestamp is available for AMCL seeding")
    # Freeze this known-good timestamp. The subscription continues receiving
    # newer odometry while we publish; following that moving edge would put
    # every new initial pose just ahead of the TF buffer again.
    seed_stamp = latest_odom_stamp["value"]

    # Use AMCL's direct service when available. Topic publication can report a
    # subscriber yet still be discarded during lifecycle/timestamp races.
    message.header.stamp.sec = seed_stamp.sec
    message.header.stamp.nanosec = seed_stamp.nanosec
    service_applied = False
    if pose_client.wait_for_service(timeout_sec=5.0):
        request = SetInitialPose.Request()
        request.pose = message
        future = pose_client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
        service_applied = future.done() and future.exception() is None
    if not service_applied:
        # Compatibility fallback for older AMCL builds without the service.
        for _ in range(20):
            publisher.publish(message)
            rclpy.spin_once(node, timeout_sec=0.5)
    if update_client.wait_for_service(timeout_sec=2.0):
        future = update_client.call_async(Empty.Request())
        rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
    node.get_logger().info(
        f"Seeded AMCL from saved pose x={pose['x']:.3f} y={pose['y']:.3f} "
        f"via {'service' if service_applied else 'topic fallback'}"
    )
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
