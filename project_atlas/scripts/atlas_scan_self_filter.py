#!/usr/bin/env python3
"""Remove Project ATLAS chassis/wheel self-returns from RPLIDAR scans."""
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Int32


# Slightly larger than the verified 0.50 x 0.36 m footprint. This removes
# wheel/chassis returns but preserves the requested 0.10 m external clearance.
SELF_X_M = 0.28
SELF_Y_M = 0.21
LASER_YAW_RAD = math.pi


class AtlasScanSelfFilter(Node):
    def __init__(self):
        super().__init__('atlas_scan_self_filter')
        reliable_scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self.publisher = self.create_publisher(LaserScan, '/scan', reliable_scan_qos)
        self.filtered_pub = self.create_publisher(Int32, '/atlas/lidar/self_filtered_points', 10)
        self.create_subscription(LaserScan, '/scan_raw', self._scan, qos_profile_sensor_data)
        self.get_logger().info('ATLAS LiDAR self-filter ready: body envelope x=+-0.28m y=+-0.21m')

    def _scan(self, source):
        target = LaserScan()
        target.header = source.header
        # The RPLIDAR composition driver on this Jetson reports scans roughly
        # 1.6 s behind receipt time.  That predates the available odom TF and
        # causes SLAM Toolbox to drop every message.  The cleaned scan is a new
        # transport boundary, so timestamp it when published.
        target.header.stamp = self.get_clock().now().to_msg()
        target.angle_min = source.angle_min
        target.angle_max = source.angle_max
        target.angle_increment = source.angle_increment
        target.time_increment = source.time_increment
        target.scan_time = source.scan_time
        target.range_min = source.range_min
        target.range_max = source.range_max
        ranges = list(source.ranges)
        removed = 0
        angle = source.angle_min
        cosine = math.cos(LASER_YAW_RAD)
        sine = math.sin(LASER_YAW_RAD)
        for index, distance in enumerate(ranges):
            if math.isfinite(distance) and source.range_min <= distance <= source.range_max:
                laser_x = distance * math.cos(angle)
                laser_y = distance * math.sin(angle)
                base_x = cosine * laser_x - sine * laser_y
                base_y = sine * laser_x + cosine * laser_y
                if abs(base_x) <= SELF_X_M and abs(base_y) <= SELF_Y_M:
                    ranges[index] = float('inf')
                    removed += 1
            angle += source.angle_increment
        target.ranges = ranges
        target.intensities = list(source.intensities)
        self.publisher.publish(target)
        self.filtered_pub.publish(Int32(data=removed))


def main():
    rclpy.init()
    node = AtlasScanSelfFilter()
    try:
        rclpy.spin(node)
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
