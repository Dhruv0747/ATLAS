#!/usr/bin/env python3
"""Read-only diagnostic for ATLAS global-costmap/start-pose alignment."""
import math
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener


FOOTPRINT = ((0.25, 0.18), (0.25, -0.18), (-0.25, -0.18), (-0.25, 0.18), (0.0, 0.0))


class Diagnostic(Node):
    def __init__(self):
        super().__init__('atlas_costmap_alignment_diagnostic')
        self.grid = None
        self.buffer = Buffer(cache_time=Duration(seconds=10.0))
        self.listener = TransformListener(self.buffer, self)
        self.create_subscription(OccupancyGrid, '/global_costmap/costmap', self._grid, 10)

    def _grid(self, message):
        self.grid = message


def grid_cost(grid, x, y):
    info = grid.info
    col = int(math.floor((x - info.origin.position.x) / info.resolution))
    row = int(math.floor((y - info.origin.position.y) / info.resolution))
    if col < 0 or row < 0 or col >= info.width or row >= info.height:
        return None
    return int(grid.data[row * info.width + col])


def main():
    rclpy.init()
    node = Diagnostic()
    end = time.monotonic() + 8.0
    transform = None
    while time.monotonic() < end and (node.grid is None or transform is None):
        rclpy.spin_once(node, timeout_sec=0.1)
        try:
            transform = node.buffer.lookup_transform('map', 'base_link', Time())
        except Exception:
            transform = None
    if node.grid is None or transform is None:
        print('DIAGNOSTIC FAILED: map costmap or map->base_link unavailable')
    else:
        tx = transform.transform.translation.x
        ty = transform.transform.translation.y
        q = transform.transform.rotation
        yaw = 2.0 * math.atan2(q.z, q.w)
        print(f'ROBOT map x={tx:.3f} y={ty:.3f} yaw={yaw:.3f}')
        costs = []
        for px, py in FOOTPRINT:
            gx = tx + px * math.cos(yaw) - py * math.sin(yaw)
            gy = ty + px * math.sin(yaw) + py * math.cos(yaw)
            cost = grid_cost(node.grid, gx, gy)
            costs.append(cost)
            print(f'FOOTPRINT local=({px:+.2f},{py:+.2f}) global=({gx:+.3f},{gy:+.3f}) cost={cost}')
        radius_cells = int(math.ceil(0.50 / node.grid.info.resolution))
        center_col = int((tx - node.grid.info.origin.position.x) / node.grid.info.resolution)
        center_row = int((ty - node.grid.info.origin.position.y) / node.grid.info.resolution)
        counts = {'unknown': 0, 'free': 0, 'inflated': 0, 'lethal': 0, 'outside': 0}
        for dr in range(-radius_cells, radius_cells + 1):
            for dc in range(-radius_cells, radius_cells + 1):
                col, row = center_col + dc, center_row + dr
                if col < 0 or row < 0 or col >= node.grid.info.width or row >= node.grid.info.height:
                    counts['outside'] += 1
                    continue
                value = int(node.grid.data[row * node.grid.info.width + col])
                if value < 0: counts['unknown'] += 1
                elif value == 0: counts['free'] += 1
                elif value >= 99: counts['lethal'] += 1
                else: counts['inflated'] += 1
        print('AROUND_0.5M', counts)
        blocked = any(cost is None or cost < 0 or cost >= 99 for cost in costs)
        print('START_POSE', 'BLOCKED' if blocked else 'VALID')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
