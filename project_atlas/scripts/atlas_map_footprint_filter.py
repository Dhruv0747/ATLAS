#!/usr/bin/env python3
"""Remove only ATLAS's live physical footprint from the SLAM occupancy map.

SLAM can leave a short-lived occupied cell beneath the rover when odometry and
map corrections settle at different times.  Nav2 then rejects every plan with
"Starting point in lethal space" even though the live LiDAR is clear.  This
mapping-only relay preserves every cell outside the measured chassis envelope.
"""

import copy
import math
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener


HALF_LENGTH_M = 0.25
HALF_WIDTH_M = 0.18
# One centimetre covers cell-boundary rounding without consuming the requested
# external 10 cm navigation clearance.
CLEAR_MARGIN_M = 0.01


class AtlasMapFootprintFilter(Node):
    def __init__(self) -> None:
        super().__init__("atlas_map_footprint_filter")
        map_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.publisher = self.create_publisher(OccupancyGrid, "/map", map_qos)
        self.subscription = self.create_subscription(
            OccupancyGrid, "/map_raw", self.filter_map, map_qos
        )
        self.buffer = Buffer(cache_time=Duration(seconds=20.0))
        self.listener = TransformListener(self.buffer, self)
        self.last_warning = 0.0
        self.last_clear_log = 0.0
        self.get_logger().info(
            "Mapping footprint sanitizer ready: /map_raw -> /map, "
            "envelope 0.50 x 0.36 m plus 0.01 m rounding margin"
        )

    def filter_map(self, source: OccupancyGrid) -> None:
        try:
            transform = self.buffer.lookup_transform(
                source.header.frame_id or "map", "base_link", Time(),
                timeout=Duration(seconds=0.25),
            )
        except Exception as exc:
            now = time.monotonic()
            if now - self.last_warning >= 5.0:
                self.get_logger().warning(
                    f"Waiting for map-to-base transform; map held back: {exc}"
                )
                self.last_warning = now
            return

        target = copy.deepcopy(source)
        resolution = float(target.info.resolution)
        if resolution <= 0.0 or not target.data:
            return
        origin_x = float(target.info.origin.position.x)
        origin_y = float(target.info.origin.position.y)
        tx = float(transform.transform.translation.x)
        ty = float(transform.transform.translation.y)
        q = transform.transform.rotation
        yaw = 2.0 * math.atan2(float(q.z), float(q.w))
        cosine = math.cos(yaw)
        sine = math.sin(yaw)
        half_length = HALF_LENGTH_M + CLEAR_MARGIN_M
        half_width = HALF_WIDTH_M + CLEAR_MARGIN_M
        radius = math.hypot(half_length, half_width)
        radius_cells = int(math.ceil(radius / resolution))
        center_col = int(math.floor((tx - origin_x) / resolution))
        center_row = int(math.floor((ty - origin_y) / resolution))
        data = list(target.data)
        cleared = 0

        for row in range(center_row - radius_cells, center_row + radius_cells + 1):
            if row < 0 or row >= target.info.height:
                continue
            for col in range(center_col - radius_cells, center_col + radius_cells + 1):
                if col < 0 or col >= target.info.width:
                    continue
                world_x = origin_x + (col + 0.5) * resolution
                world_y = origin_y + (row + 0.5) * resolution
                dx = world_x - tx
                dy = world_y - ty
                local_x = cosine * dx + sine * dy
                local_y = -sine * dx + cosine * dy
                if abs(local_x) <= half_length and abs(local_y) <= half_width:
                    index = row * target.info.width + col
                    if data[index] != 0:
                        data[index] = 0
                        cleared += 1

        target.data = data
        self.publisher.publish(target)
        now = time.monotonic()
        if cleared and now - self.last_clear_log >= 10.0:
            self.get_logger().info(
                f"Cleared {cleared} stale map cells inside live rover footprint"
            )
            self.last_clear_log = now


def main() -> None:
    rclpy.init()
    node = AtlasMapFootprintFilter()
    try:
        rclpy.spin(node)
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
