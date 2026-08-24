#!/usr/bin/env python3
"""Inspect Nav2 costmap values and locate a nearby traversable goal."""

import argparse
import math

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy


class Probe(Node):
    def __init__(self, topic: str) -> None:
        super().__init__("atlas_costmap_probe")
        self.grid = None
        qos = QoSProfile(depth=1)
        qos.reliability = ReliabilityPolicy.RELIABLE
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        self.create_subscription(OccupancyGrid, topic, self.on_grid, qos)

    def on_grid(self, msg: OccupancyGrid) -> None:
        self.grid = msg


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("x", type=float)
    parser.add_argument("y", type=float)
    parser.add_argument("--radius", type=float, default=0.6)
    parser.add_argument("--max-cost", type=int, default=40)
    parser.add_argument("--topic", default="/global_costmap/costmap")
    args = parser.parse_args()
    rclpy.init()
    node = Probe(args.topic)
    deadline = node.get_clock().now().nanoseconds + 5_000_000_000
    while rclpy.ok() and node.grid is None:
        rclpy.spin_once(node, timeout_sec=0.2)
        if node.get_clock().now().nanoseconds >= deadline:
            raise SystemExit("NO_COSTMAP")
    grid = node.grid
    info = grid.info

    def cell(wx, wy):
        mx = int(math.floor((wx - info.origin.position.x) / info.resolution))
        my = int(math.floor((wy - info.origin.position.y) / info.resolution))
        if not 0 <= mx < info.width or not 0 <= my < info.height:
            return mx, my, None
        return mx, my, int(grid.data[my * info.width + mx])

    mx, my, cost = cell(args.x, args.y)
    print(f"TARGET x={args.x:.3f} y={args.y:.3f} cell=({mx},{my}) cost={cost}")
    limit = int(math.ceil(args.radius / info.resolution))
    candidates = []
    for dy in range(-limit, limit + 1):
        for dx in range(-limit, limit + 1):
            cx, cy = mx + dx, my + dy
            if not 0 <= cx < info.width or not 0 <= cy < info.height:
                continue
            value = int(grid.data[cy * info.width + cx])
            if 0 <= value <= args.max_cost:
                wx = info.origin.position.x + (cx + 0.5) * info.resolution
                wy = info.origin.position.y + (cy + 0.5) * info.resolution
                distance = math.hypot(wx - args.x, wy - args.y)
                if distance <= args.radius:
                    candidates.append((distance, value, wx, wy))
    if candidates:
        distance, value, wx, wy = min(candidates)
        print(
            f"NEAREST_FREE x={wx:.3f} y={wy:.3f} "
            f"distance={distance:.3f} cost={value}"
        )
    else:
        print("NEAREST_FREE none")
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
