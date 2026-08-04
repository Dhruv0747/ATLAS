#!/usr/bin/env python3
"""Bounded Nav2 response test for ATLAS with every wheel lifted."""
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Float32


class LiftedNavTest(Node):
    def __init__(self):
        super().__init__('atlas_nav2_lifted_test')
        self.client = ActionClient(self, NavigateToPose, '/navigate_to_pose')
        self.stop_pub = self.create_publisher(Twist, '/cmd_vel_nav', 10)
        self.odom = None
        self.max_nav_vx = 0.0
        self.max_nav_wz = 0.0
        self.max_rpm = 0.0
        self.create_subscription(Odometry, '/odom', self._odom, 10)
        self.create_subscription(Twist, '/cmd_vel_nav', self._cmd, 10)
        for wheel in ('front_right', 'front_left', 'back_right', 'back_left'):
            self.create_subscription(Float32, f'/yahboom/wheel/{wheel}/rpm', self._rpm, 10)

    def _odom(self, message):
        self.odom = message

    def _cmd(self, message):
        self.max_nav_vx = max(self.max_nav_vx, abs(float(message.linear.x)))
        self.max_nav_wz = max(self.max_nav_wz, abs(float(message.angular.z)))

    def _rpm(self, message):
        self.max_rpm = max(self.max_rpm, abs(float(message.data)))

    def stop(self):
        self.stop_pub.publish(Twist())


def spin_until(node, predicate, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not predicate():
        rclpy.spin_once(node, timeout_sec=0.05)
    return predicate()


def main():
    rclpy.init()
    node = LiftedNavTest()
    goal_handle = None
    try:
        if not spin_until(node, lambda: node.odom is not None, 3.0):
            raise RuntimeError('no /odom')
        if not node.client.wait_for_server(timeout_sec=3.0):
            raise RuntimeError('NavigateToPose action unavailable')
        pose = node.odom.pose.pose
        yaw = 2.0 * math.atan2(pose.orientation.z, pose.orientation.w)
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = 'odom'
        goal.pose.header.stamp = node.get_clock().now().to_msg()
        goal.pose.pose.position.x = pose.position.x + 0.20 * math.cos(yaw)
        goal.pose.pose.position.y = pose.position.y + 0.20 * math.sin(yaw)
        goal.pose.pose.orientation = pose.orientation
        future = node.client.send_goal_async(goal)
        if not spin_until(node, future.done, 3.0):
            raise RuntimeError('goal response timeout')
        goal_handle = future.result()
        if not goal_handle or not goal_handle.accepted:
            raise RuntimeError('Nav2 rejected lifted test goal')
        print('GOAL ACCEPTED: 0.20 m forward in odom')
        end = time.monotonic() + 4.0
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
        cancel = goal_handle.cancel_goal_async()
        spin_until(node, cancel.done, 2.0)
        print('GOAL CANCELLED')
    finally:
        for _ in range(15):
            node.stop()
            rclpy.spin_once(node, timeout_sec=0.02)
            time.sleep(0.02)
        print(f'NAV_CMD peak_vx={node.max_nav_vx:.3f} peak_wz={node.max_nav_wz:.3f}')
        print(f'WHEEL peak_rpm={node.max_rpm:.2f}')
        print('SAFETY STOP: /cmd_vel_nav zero')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
