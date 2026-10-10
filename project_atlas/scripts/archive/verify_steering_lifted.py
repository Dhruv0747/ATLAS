#!/usr/bin/env python3
"""Visible steering-only test for lifted Project ATLAS."""
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class SteeringTest(Node):
    def __init__(self):
        super().__init__('atlas_steering_lifted_test')
        self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)

    def send(self, angular):
        message = Twist()
        message.linear.x = 0.0
        message.angular.z = float(angular)
        self.publisher.publish(message)


def hold(node, angular, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        node.send(angular)
        rclpy.spin_once(node, timeout_sec=0.02)
        time.sleep(0.03)


def main():
    rclpy.init()
    node = SteeringTest()
    try:
        hold(node, 0.0, 0.5)
        print('STEER LEFT: front and rear should move oppositely')
        hold(node, 1.5, 2.0)
        print('CENTER')
        hold(node, 0.0, 1.0)
        print('STEER RIGHT: front and rear should move oppositely')
        hold(node, -1.5, 2.0)
    finally:
        print('CENTER / MOTOR STOP')
        hold(node, 0.0, 1.0)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
