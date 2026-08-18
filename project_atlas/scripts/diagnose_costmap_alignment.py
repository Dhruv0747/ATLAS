#!/usr/bin/env python3
"""Read-only diagnostic for ATLAS global-costmap/start-pose alignment."""
import math
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener


FOOTPRINT = ((0.25, 0.18), (0.25, -0.18), (-0.25, -0.18), (-0.25, 0.18), (0.0, 0.0))


class Diagnostic(Node):
    def __init__(self):
        super().__init__('atlas_costmap_alignment_diagnostic')
        self.grid = None
        self.scan = None
        self.buffer = Buffer(cache_time=Duration(seconds=10.0))
        self.listener = TransformListener(self.buffer, self)
        self.create_subscription(OccupancyGrid, '/global_costmap/costmap', self._grid, 10)
        self.create_subscription(LaserScan, '/scan', self._scan, qos_profile_sensor_data)

    def _grid(self, message):
        self.grid = message

    def _scan(self, message):
        self.scan = message


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

        if node.scan is not None:
            try:
                laser_tf = node.buffer.lookup_transform('base_link', node.scan.header.frame_id, Time())
                lx = laser_tf.transform.translation.x
                ly = laser_tf.transform.translation.y
                ql = laser_tf.transform.rotation
                laser_yaw = 2.0 * math.atan2(ql.z, ql.w)
                nearest = []
                inside = []
                for index, distance in enumerate(node.scan.ranges):
                    if not math.isfinite(distance):
                        continue
                    if distance < node.scan.range_min or distance > node.scan.range_max:
                        continue
                    angle = node.scan.angle_min + index * node.scan.angle_increment + laser_yaw
                    bx = lx + distance * math.cos(angle)
                    by = ly + distance * math.sin(angle)
                    item = (math.hypot(bx, by), bx, by, index)
                    nearest.append(item)
                    if abs(bx) <= 0.25 and abs(by) <= 0.18:
                        inside.append(item)
                nearest.sort()
                inside.sort()
                print(
                    f'SCAN frame={node.scan.header.frame_id} '
                    f'laser=({lx:+.3f},{ly:+.3f},{laser_yaw:+.3f}) '
                    f'finite={len(nearest)} inside_physical_footprint={len(inside)}'
                )
                for distance, bx, by, index in nearest[:12]:
                    print(
                        f'SCAN_NEAR index={index} base=({bx:+.3f},{by:+.3f}) '
                        f'distance_from_base={distance:.3f}'
                    )
                close = [item for item in nearest if item[0] <= 0.50]
                if close:
                    indices = sorted(item[3] for item in close)
                    groups = []
                    start = previous = indices[0]
                    for index in indices[1:]:
                        if index > previous + 1:
                            groups.append((start, previous))
                            start = index
                        previous = index
                    groups.append((start, previous))
                    print(
                        f'SCAN_WITHIN_0.5M count={len(close)} '
                        f'index_groups={groups} '
                        f'x_range=({min(item[1] for item in close):+.3f},'
                        f'{max(item[1] for item in close):+.3f}) '
                        f'y_range=({min(item[2] for item in close):+.3f},'
                        f'{max(item[2] for item in close):+.3f})'
                    )
                sectors = {
                    'front': (0.0, 12.5),
                    'left': (70.0, 12.5),
                    'right': (-70.0, 12.5),
                    'rear': (180.0, 12.5),
                }
                values = {}
                for name, (center, half_width) in sectors.items():
                    candidates = []
                    for distance, bx, by, _index in nearest:
                        bearing = math.degrees(math.atan2(by, bx))
                        delta = (bearing - center + 180.0) % 360.0 - 180.0
                        if abs(delta) <= half_width:
                            candidates.append(distance)
                    values[name] = min(candidates) if candidates else math.inf
                print('SCAN_SECTORS ' + ' '.join(
                    f'{name}={value:.3f}' if math.isfinite(value) else f'{name}=inf'
                    for name, value in values.items()
                ))
            except Exception as exc:
                print(f'SCAN_DIAGNOSTIC_FAILED {exc}')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
