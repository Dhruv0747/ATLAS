#!/usr/bin/env python3
"""Compare live ATLAS scan, odom TF, and ROS clock timestamps."""
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage
from tf2_ros import Buffer, TransformListener
from rclpy.time import Time


def stamp_seconds(stamp):
    return float(stamp.sec) + float(stamp.nanosec) / 1e9


class Check(Node):
    def __init__(self):
        super().__init__('atlas_scan_tf_time_diagnostic')
        self.scan_stamp = None
        self.tf_stamp = None
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)
        reliable = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                              durability=DurabilityPolicy.VOLATILE,
                              history=HistoryPolicy.KEEP_LAST, depth=10)
        self.create_subscription(LaserScan, '/scan', self._scan, reliable)
        self.create_subscription(TFMessage, '/tf', self._tf, 20)

    def _scan(self, message):
        self.scan_stamp = stamp_seconds(message.header.stamp)

    def _tf(self, message):
        for transform in message.transforms:
            if transform.header.frame_id.lstrip('/') == 'odom' and transform.child_frame_id.lstrip('/') == 'base_link':
                self.tf_stamp = stamp_seconds(transform.header.stamp)


def main():
    rclpy.init()
    node = Check()
    end = time.monotonic() + 12.0
    while time.monotonic() < end and (node.scan_stamp is None or node.tf_stamp is None):
        rclpy.spin_once(node, timeout_sec=0.1)
    settle = time.monotonic() + 1.0
    while time.monotonic() < settle:
        rclpy.spin_once(node, timeout_sec=0.05)
    now = node.get_clock().now().nanoseconds / 1e9
    print(f'NOW {now:.6f}')
    scan_age = '--' if node.scan_stamp is None else f'{now-node.scan_stamp:.6f}'
    tf_age = '--' if node.tf_stamp is None else f'{now-node.tf_stamp:.6f}'
    print(f'SCAN {node.scan_stamp} age={scan_age}')
    print(f'TF {node.tf_stamp} age={tf_age}')
    if node.scan_stamp is not None and node.tf_stamp is not None:
        print(f'TF_MINUS_SCAN {node.tf_stamp-node.scan_stamp:+.6f}')
    if node.scan_stamp is not None:
        scan_time = Time(nanoseconds=int(node.scan_stamp * 1e9))
        try:
            transform = node.buffer.lookup_transform('odom', 'laser_frame', scan_time)
            print('ODOM_FROM_LASER_AT_SCAN OK', stamp_seconds(transform.header.stamp))
        except Exception as error:
            print('ODOM_FROM_LASER_AT_SCAN FAILED', repr(error))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
