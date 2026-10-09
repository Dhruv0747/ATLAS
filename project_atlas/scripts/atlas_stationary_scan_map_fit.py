#!/usr/bin/env python3
"""Read-only LiDAR/saved-map alignment clues for a stopped ATLAS rover.

Endpoint agreement is not proof of physical localization: moving objects,
unknown space and a symmetric room can create false matches. This script never
publishes a pose, goal or motor command.
"""

import argparse
import ast
import json
import math
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from atlas_map_acceptance_core import _map_yaml_values, _read_pgm, map_pair_id


def yaw_from_quaternion(qz, qw):
    return 2.0 * math.atan2(float(qz), float(qw))


def rotated(points, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return points @ np.array([[c, s], [-s, c]])


def make_map(yaml_path):
    yaml_path = Path(yaml_path)
    metadata = _map_yaml_values(yaml_path)
    origin_line = next(
        (line.split(":", 1)[1].strip()
         for line in yaml_path.read_text(encoding="utf-8").splitlines()
         if line.strip().startswith("origin:")),
        None,
    )
    origin = ast.literal_eval(origin_line) if origin_line is not None else None
    if not isinstance(origin, (list, tuple)) or len(origin) < 3 or abs(float(origin[2])) > 1e-6:
        raise ValueError("diagnostic requires a zero-yaw map origin")
    if metadata["negate"] != 0:
        raise ValueError("diagnostic requires the commissioned non-negated trinary map")
    image = yaml_path.parent / metadata["image"]
    width, height, pixels = _read_pgm(image)
    grid = np.asarray(pixels, dtype=np.uint8).reshape(height, width)
    resolution = float(metadata["resolution"])
    origin_x, origin_y = metadata["origin"]
    occupied_row, occupied_col = np.nonzero(grid <= 1)
    occupied = np.column_stack((
        origin_x + (occupied_col + 0.5) * resolution,
        origin_y + (height - occupied_row - 0.5) * resolution,
    ))
    if not len(occupied):
        raise ValueError("saved map has no occupied cells")
    return metadata, grid, cKDTree(occupied)


def score_pose(laser_points, pose, metadata, grid, occupied_tree):
    """Report raw map agreement; never turn the score into navigation authority."""
    height, width = grid.shape
    resolution = float(metadata["resolution"])
    origin_x, origin_y = metadata["origin"]
    world = rotated(laser_points, pose[2]) + np.array(pose[:2])
    col = np.floor((world[:, 0] - origin_x) / resolution).astype(int)
    row = height - 1 - np.floor((world[:, 1] - origin_y) / resolution).astype(int)
    inside = (col >= 0) & (col < width) & (row >= 0) & (row < height)
    cells = np.full(len(world), 205, dtype=np.uint8)
    cells[inside] = grid[row[inside], col[inside]]
    distances, _ = occupied_tree.query(world)
    center_col = math.floor((pose[0] - origin_x) / resolution)
    center_row = height - 1 - math.floor((pose[1] - origin_y) / resolution)
    center = (int(grid[center_row, center_col])
              if 0 <= center_col < width and 0 <= center_row < height else None)
    return {
        "pose": [round(float(value), 4) for value in pose],
        "map_center_value": center,
        "endpoints": len(world),
        "inside_map_fraction": round(float(np.mean(inside)), 3),
        "known_endpoint_fraction": round(float(np.mean(inside & (cells != 205))), 3),
        "occupied_endpoint_fraction": round(float(np.mean(inside & (cells <= 1))), 3),
        "within_15cm_of_wall_fraction": round(float(np.mean(distances <= 0.15)), 3),
        "median_wall_distance_m": round(float(np.median(distances)), 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", default="/home/jetson/project_atlas/maps/atlas_latest.yaml")
    parser.add_argument("--places", default="/home/jetson/.config/project_atlas/named_places.json")
    args = parser.parse_args()

    # ROS imports are delayed so score_pose can be tested offline.
    import rclpy
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan

    class Snapshot(Node):
        def __init__(self):
            super().__init__("atlas_stationary_scan_map_fit")
            self.scan = None
            self.pose = None
            self.create_subscription(LaserScan, "/scan", self.on_scan,
                                     qos_profile_sensor_data)
            self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose",
                                     self.on_pose, 10)

        def on_scan(self, msg):
            self.scan = msg

        def on_pose(self, msg):
            self.pose = msg

    rclpy.init()
    node = Snapshot()
    deadline = time.monotonic() + 8.0
    try:
        while (node.scan is None or node.pose is None) and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
        if node.scan is None or node.pose is None:
            raise RuntimeError("fresh /scan and /amcl_pose were not both received")
        scan, amcl = node.scan, node.pose
        if scan.header.frame_id.strip("/") != "laser_frame":
            raise ValueError(f"unexpected LiDAR frame: {scan.header.frame_id}")
        now = node.get_clock().now().nanoseconds * 1e-9
        scan_time = scan.header.stamp.sec + scan.header.stamp.nanosec * 1e-9
        pose_time = amcl.header.stamp.sec + amcl.header.stamp.nanosec * 1e-9
        if not (0 <= now - scan_time <= 1.0 and 0 <= now - pose_time <= 3.0):
            raise RuntimeError("scan or AMCL pose was stale; no comparison made")

        ranges = np.asarray(scan.ranges, dtype=float)
        angles = scan.angle_min + np.arange(len(ranges)) * scan.angle_increment
        valid = np.isfinite(ranges) & (ranges >= max(0.3, scan.range_min)) & (
            ranges <= min(5.0, scan.range_max))
        # Verified live TF on this rover: base_link -> laser_frame is 180-degree
        # yaw and -0.05 m X. Check this mounting before reuse after hardware
        # changes.
        laser_points = np.column_stack((
            ranges[valid] * np.cos(angles[valid] + math.pi) - 0.05,
            ranges[valid] * np.sin(angles[valid] + math.pi),
        ))
        if len(laser_points) < 30:
            raise RuntimeError("too few finite LiDAR endpoints")
        metadata, grid, tree = make_map(args.map)
        p = amcl.pose.pose
        live = (float(p.position.x), float(p.position.y),
                yaw_from_quaternion(p.orientation.z, p.orientation.w))
        places = json.loads(Path(args.places).read_text(encoding="utf-8"))
        accepted_map_id = map_pair_id(Path(args.map), Path(args.map).parent / metadata["image"])
        if not accepted_map_id or places.get("map_id") != accepted_map_id:
            raise RuntimeError("named places do not match exact accepted map bytes")
        home = places["dhruv room"]
        home_pose = (float(home["x"]), float(home["y"]),
                     yaw_from_quaternion(home["qz"], home["qw"]))
        hall = places["hall"]
        hall_pose = (float(hall["x"]), float(hall["y"]),
                     yaw_from_quaternion(hall["qz"], hall["qw"]))
        live_result = score_pose(laser_points, live, metadata, grid, tree)
        home_result = score_pose(laser_points, home_pose, metadata, grid, tree)
        hall_result = score_pose(laser_points, hall_pose, metadata, grid, tree)
        home_headings = [
            score_pose(laser_points, (home_pose[0], home_pose[1],
                                      -math.pi + 2 * math.pi * index / 24),
                       metadata, grid, tree)
            for index in range(24)
        ]
        best_heading = max(home_headings, key=lambda item:
                           item["within_15cm_of_wall_fraction"])
        print(json.dumps({
            "scan_age_s": round(now - scan_time, 3),
            "amcl_age_s": round(now - pose_time, 3),
            "laser_mount_live_tf": "base_link -> laser_frame: -0.05m X, 180deg yaw",
            "live_amcl": live_result,
            "saved_dhruv_point": home_result,
            "saved_hall_point": hall_result,
            "best_of_24_headings_at_saved_point": best_heading,
            "limitation": "Endpoint agreement is only a clue. No pose was seeded, "
                          "saved, or promoted; no motor command was sent.",
        }, indent=2))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
