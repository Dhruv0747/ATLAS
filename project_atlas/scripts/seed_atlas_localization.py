#!/usr/bin/env python3
"""Seed AMCL from a saved map-frame pose without moving the rover."""

import argparse
import json
from pathlib import Path
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node


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

    # A lifecycle node may expose /initialpose before AMCL is active. Publish
    # across the activation window so at least one seed is processed before
    # the delayed Nav2 costmaps start and require map -> odom.
    for _ in range(20):
        # Zero requests the latest available TF. A wall-clock stamp can be a
        # few milliseconds newer than odom and makes AMCL report avoidable
        # future-extrapolation warnings during startup.
        message.header.stamp.sec = 0
        message.header.stamp.nanosec = 0
        publisher.publish(message)
        rclpy.spin_once(node, timeout_sec=0.5)
    node.get_logger().info(
        f"Seeded AMCL from saved pose x={pose['x']:.3f} y={pose['y']:.3f}"
    )
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
