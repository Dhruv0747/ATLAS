#!/usr/bin/env python3
"""Relay /cmd_vel_teleop -> /cmd_vel  (fixes Foxglove gamepad topic mismatch)"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

class Relay(Node):
    def __init__(self):
        super().__init__('cmd_vel_relay')
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.sub = self.create_subscription(Twist, '/cmd_vel_teleop', self.cb, 10)
        self.get_logger().info('Relay active: /cmd_vel_teleop -> /cmd_vel')

    def cb(self, msg):
        self.pub.publish(msg)

def main():
    rclpy.init()
    node = Relay()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
