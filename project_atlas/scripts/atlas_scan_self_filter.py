#!/usr/bin/env python3
"""Remove Project ATLAS chassis/wheel self-returns from RPLIDAR scans."""
import math

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Int32


# Slightly larger than the verified 0.50 x 0.36 m footprint. This removes
# wheel/chassis returns but preserves the requested 0.10 m external clearance.
# The live commissioning map showed wheel/chassis returns reaching roughly
# 4.4 cm beyond the nominal 0.50 x 0.36 m body.  A 5 cm exclusion margin
# removes that self-imprint while remaining inside the 10 cm navigation
# clearance, so obstacles at the planned safety boundary are still retained.
SELF_X_M = 0.30
SELF_Y_M = 0.23
# Measured installation: LiDAR centre is 0.30 m from the front edge of a
# 0.50 m chassis, placing it 0.05 m behind base_footprint.
LASER_X_M = -0.05
LASER_YAW_RAD = math.pi
# 2026-11-13: RPLIDAR Boost mode gives ~1080 beams (96 % valid) instead of 360 (57 % valid). Every /scan consumer
# deserialises the scan in Python, so /scan is thinned to ~TARGET_BINS: each output bin = the NEAREST valid return of
# its consecutive raw beams (conservative for obstacles, fills the Standard-mode gaps). Thinning applies only when the
# raw scan has at least 1.5x TARGET_BINS beams, so a Standard-mode scan passes through unchanged.
TARGET_BINS = 360


class AtlasScanSelfFilter(Node):
    def __init__(self):
        super().__init__('atlas_scan_self_filter')
        # Keep only the newest scan. Under dashboard load, a deep reliable
        # queue delayed scans behind the current TF window and made Nav2 drop
        # otherwise valid LiDAR data.
        reliable_scan_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.publisher = self.create_publisher(LaserScan, '/scan', reliable_scan_qos)
        self.filtered_pub = self.create_publisher(Int32, '/atlas/lidar/self_filtered_points', 10)
        self.create_subscription(LaserScan, '/scan_raw', self._scan, qos_profile_sensor_data)
        self.get_logger().info(
            'ATLAS LiDAR self-filter ready: sensor x=-0.05m; '
            'body envelope x=+-0.30m y=+-0.23m'
        )

    def _scan(self, source):
        target = LaserScan()
        # A LaserScan header is the acquisition time of its first ray.  Keep
        # the driver's timestamp so SLAM/Nav2 select the rover pose that
        # produced these ranges; filter publication time is not measurement
        # time.  The TF buffer, not timestamp replacement, handles transport
        # latency.
        target.header = source.header
        target.angle_min = source.angle_min
        target.angle_max = source.angle_max
        target.angle_increment = source.angle_increment
        target.time_increment = source.time_increment
        target.scan_time = source.scan_time
        target.range_min = source.range_min
        target.range_max = source.range_max
        r = np.asarray(source.ranges, dtype=np.float64).copy()
        n = r.size
        angles = source.angle_min + np.arange(n, dtype=np.float64) * source.angle_increment
        valid = np.isfinite(r) & (r >= source.range_min) & (r <= source.range_max)
        with np.errstate(invalid='ignore'):
            laser_x = np.where(valid, r, 0.0) * np.cos(angles)
            laser_y = np.where(valid, r, 0.0) * np.sin(angles)
        cosine, sine = math.cos(LASER_YAW_RAD), math.sin(LASER_YAW_RAD)
        base_x = LASER_X_M + cosine * laser_x - sine * laser_y
        base_y = sine * laser_x + cosine * laser_y
        self_hit = valid & (np.abs(base_x) <= SELF_X_M) & (np.abs(base_y) <= SELF_Y_M)
        r[self_hit] = np.inf
        removed = int(self_hit.sum())
        intensities = np.asarray(source.intensities, dtype=np.float32)
        target_bins = getattr(self, 'target_bins', TARGET_BINS)
        factor = int(round(n / target_bins)) if target_bins and n >= 1.5 * target_bins else 1
        if factor >= 2:
            m = n // factor
            usable = valid & ~self_hit
            grouped = np.where(usable[:m * factor], r[:m * factor], np.inf).reshape(m, factor)
            pick = np.argmin(grouped, axis=1)
            nearest = grouped[np.arange(m), pick]
            # bins with no valid return keep the raw value of their first beam (inf / out-of-range, as before)
            raw_first = r[:m * factor].reshape(m, factor)[:, 0]
            r = np.where(np.isfinite(nearest), nearest, raw_first)
            if intensities.size == n:
                intensities = intensities[:m * factor].reshape(m, factor)[np.arange(m), pick]
            target.angle_min = source.angle_min + (factor - 1) / 2.0 * source.angle_increment
            target.angle_increment = source.angle_increment * factor
            target.angle_max = target.angle_min + (m - 1) * target.angle_increment
            target.time_increment = source.time_increment * factor
        target.ranges = r.tolist()
        target.intensities = intensities.tolist()
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
