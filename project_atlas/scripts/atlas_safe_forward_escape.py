#!/usr/bin/env python3
"""Guarded 18 cm forward recovery when ATLAS starts blocked at the rear."""
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Float32


TARGET_M = 0.18
FRONT_STOP_MM = 600.0
MAX_RUN_S = 3.0


class Escape(Node):
    def __init__(self):
        super().__init__('atlas_safe_forward_escape')
        self.publisher = self.create_publisher(Twist, '/cmd_vel_web', 10)
        self.front_mm = None
        self.front_time = 0.0
        self.odom = None
        self.create_subscription(Float32, '/ultrasonic/front_mm', self._front, 10)
        self.create_subscription(Odometry, '/odom', self._odom, 10)

    def _front(self, message):
        self.front_mm = float(message.data)
        self.front_time = time.monotonic()

    def _odom(self, message):
        self.odom = message.pose.pose.position

    def command(self, speed=0.0):
        message = Twist()
        message.linear.x = float(speed)
        self.publisher.publish(message)

    def stop(self):
        for _ in range(15):
            self.command(0.0)
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.02)


def main():
    rclpy.init()
    node = Escape()
    reason = 'unknown'
    try:
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and (node.odom is None or node.front_mm is None):
            rclpy.spin_once(node, timeout_sec=0.05)
        if node.odom is None or node.front_mm is None:
            raise RuntimeError('odometry or front ultrasonic unavailable')
        if node.front_mm <= FRONT_STOP_MM:
            raise RuntimeError(f'front blocked at {node.front_mm:.0f} mm')
        start_x, start_y = node.odom.x, node.odom.y
        started = time.monotonic()
        while True:
            rclpy.spin_once(node, timeout_sec=0.03)
            if time.monotonic() - node.front_time > 0.5:
                reason = 'front sensor stale'
                break
            if node.front_mm <= FRONT_STOP_MM:
                reason = f'front clearance {node.front_mm:.0f} mm'
                break
            distance = math.hypot(node.odom.x - start_x, node.odom.y - start_y)
            if distance >= TARGET_M:
                reason = f'target reached {distance:.3f} m'
                break
            if time.monotonic() - started >= MAX_RUN_S:
                reason = f'timeout distance {distance:.3f} m'
                break
            node.command(0.12)
        print('RECOVERY', reason)
    finally:
        node.stop()
        print('SAFETY STOP: /cmd_vel_web zero')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
