#!/usr/bin/env python3
"""Virtual obstacles for objects the RPLIDAR cannot see (2026-11-16, owner-confirmed: black leather sofa, glass coffee
table, black cabinet in the hall).

The saved map (atlas_latest, used by AMCL) is NOT changed. This node republishes /map as /map_nav with the polygons from
config/virtual_obstacles.json marked occupied (100). Nav2's static layers read /map_nav, so planning and the controller
keep clear of them. The cmd_vel mux applies the same polygons (overlay_grid) to its copy of /map, so the LiDAR guard
treats the gap toward the sofa as a known wall at the polygon edge instead of an unexplained blind spot.

Polygons only ADD occupied cells; they never clear anything. If the config is missing or bad, /map_nav is the plain map
(same as before this change) and an error is logged.
"""
import json
import math
from pathlib import Path

DEFAULT_CONFIG = '/home/jetson/project_atlas/config/virtual_obstacles.json'
OCCUPIED = 100


def load_polygons(path):
    """[(name, [(x, y), ...]), ...] from the JSON config. Raises ValueError on a malformed file."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    out = []
    for i, ob in enumerate(data.get('obstacles', [])):
        pts = ob.get('polygon')
        if not isinstance(pts, list) or len(pts) < 3:
            raise ValueError(f'obstacle {i}: polygon needs >= 3 corners')
        poly = []
        for p in pts:
            x, y = float(p[0]), float(p[1])
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f'obstacle {i}: non-finite corner')
            poly.append((x, y))
        out.append((str(ob.get('name', f'obstacle {i}')), poly))
    return out


def point_in_polygon(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def overlay_data(width, height, resolution, origin_x, origin_y, data, polygons):
    """Copy of row-major occupancy data (nav_msgs layout, row 0 at origin_y) with every cell whose centre lies inside a
    polygon set to OCCUPIED. Returns (new_data, cells_marked)."""
    out = list(data)
    marked = 0
    for _, poly in polygons:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        gx0 = max(0, int(math.floor((min(xs) - origin_x) / resolution)))
        gx1 = min(width - 1, int(math.floor((max(xs) - origin_x) / resolution)))
        gy0 = max(0, int(math.floor((min(ys) - origin_y) / resolution)))
        gy1 = min(height - 1, int(math.floor((max(ys) - origin_y) / resolution)))
        for gy in range(gy0, gy1 + 1):
            cy = origin_y + (gy + 0.5) * resolution
            row = gy * width
            for gx in range(gx0, gx1 + 1):
                cx = origin_x + (gx + 0.5) * resolution
                if point_in_polygon(cx, cy, poly) and out[row + gx] != OCCUPIED:
                    out[row + gx] = OCCUPIED
                    marked += 1
    return out, marked


def overlay_grid(grid, polygons):
    """Same as overlay_data for an atlas_lidar_availability.OccGrid; returns a new grid of the same class."""
    data, _ = overlay_data(grid.w, grid.h, grid.res, grid.ox, grid.oy, grid.data, polygons)
    return type(grid)(grid.w, grid.h, grid.res, grid.ox, grid.oy, data, grid.occ, grid.free)


def main():
    import rclpy
    from nav_msgs.msg import OccupancyGrid
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

    class VirtualObstacles(Node):
        def __init__(self):
            super().__init__('atlas_virtual_obstacles')
            self.declare_parameter('config', DEFAULT_CONFIG)
            self.declare_parameter('output_topic', '/map_nav')
            qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
            path = str(self.get_parameter('config').value)
            try:
                self.polygons = load_polygons(path)
                self.get_logger().info(f'{len(self.polygons)} virtual obstacles from {path}: '
                                       + ', '.join(n for n, _ in self.polygons))
            except (OSError, ValueError, TypeError, IndexError, KeyError) as exc:
                self.polygons = []
                self.get_logger().error(f'virtual obstacles NOT applied ({path}): {exc}; /map_nav = plain /map')
            self.pub = self.create_publisher(OccupancyGrid, str(self.get_parameter('output_topic').value), qos)
            self.create_subscription(OccupancyGrid, '/map', self.on_map, qos)

        def on_map(self, msg):
            info = msg.info
            out = OccupancyGrid()
            out.header = msg.header
            out.info = info
            o = info.origin.orientation
            if self.polygons and abs(o.x) < 1e-6 and abs(o.y) < 1e-6 and abs(o.z) < 1e-6:
                data, marked = overlay_data(info.width, info.height, info.resolution, info.origin.position.x,
                                            info.origin.position.y, msg.data, self.polygons)
                self.get_logger().info(f'/map {info.width}x{info.height}: {marked} cells marked as virtual obstacles')
            else:
                data = list(msg.data)
                if self.polygons:
                    self.get_logger().error('rotated map origin: virtual obstacles NOT applied')
            out.data = data
            self.pub.publish(out)

    rclpy.init()
    node = VirtualObstacles()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
