#!/usr/bin/env python3
"""Extract a map-frame ATLAS trajectory from a remapped rosbag TF stream."""

import argparse
import json
import math
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from tf2_msgs.msg import TFMessage


def yaw_of(q) -> float:
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


class RouteExtractor(Node):
    def __init__(self) -> None:
        super().__init__("atlas_tf_route_extractor")
        self.map_to_odom = None
        self.points = []
        self.received = False
        self.last_message = time.monotonic()
        self.create_subscription(TFMessage, "/analysis/tf", self.on_tf, 100)

    def on_tf(self, msg: TFMessage) -> None:
        self.received = True
        self.last_message = time.monotonic()
        for item in msg.transforms:
            parent = item.header.frame_id.lstrip("/")
            child = item.child_frame_id.lstrip("/")
            transform = item.transform
            if parent == "map" and child == "odom":
                self.map_to_odom = (
                    transform.translation.x,
                    transform.translation.y,
                    yaw_of(transform.rotation),
                )
            elif parent == "odom" and child in ("base_link", "base_footprint"):
                if self.map_to_odom is None:
                    continue
                mx, my, myaw = self.map_to_odom
                ox = transform.translation.x
                oy = transform.translation.y
                oyaw = yaw_of(transform.rotation)
                x = mx + math.cos(myaw) * ox - math.sin(myaw) * oy
                y = my + math.sin(myaw) * ox + math.cos(myaw) * oy
                yaw = math.atan2(math.sin(myaw + oyaw), math.cos(myaw + oyaw))
                if self.points:
                    previous = self.points[-1]
                    if math.hypot(x - previous[0], y - previous[1]) < 0.015:
                        continue
                self.points.append((x, y, yaw))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rclpy.init()
    node = RouteExtractor()
    started = time.monotonic()
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.2)
        if node.received and time.monotonic() - node.last_message > 2.0:
            break
        if time.monotonic() - started > 45.0:
            break
    if len(node.points) < 2:
        raise RuntimeError("recorded TF did not contain a usable map-to-base route")
    distance = sum(
        math.hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(node.points, node.points[1:])
    )
    payload = {
        "frame_id": "map",
        "point_count": len(node.points),
        "distance_m": round(distance, 3),
        "points": [
            {"x": x, "y": y, "yaw": yaw} for x, y, yaw in node.points
        ],
    }
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "points"}, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
