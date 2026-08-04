#!/usr/bin/env python3
"""Adapt Nav2 differential-style cmd_vel into steering-rover cmd_vel.

Nav2's default controller often sends angular-only rotate commands. Project ATLAS
uses a front steering servo, so it needs forward motion while steering.
"""
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String


class Nav2CmdAdapter(Node):
    def __init__(self):
        super().__init__('nav2_cmd_adapter')
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.status_pub = self.create_publisher(String, '/nav2_cmd_adapter/status', 10)
        self.sub = self.create_subscription(Twist, '/cmd_vel_nav', self.on_cmd, 10)
        self.last_cmd_time = 0.0
        self.last_output = Twist()
        self.create_timer(0.1, self.watchdog)
        self.get_logger().info('Nav2 cmd adapter active: /cmd_vel_nav -> /cmd_vel')

    @staticmethod
    def clamp(value, lo, hi):
        return max(lo, min(hi, value))

    def on_cmd(self, msg):
        out = Twist()
        lin = float(msg.linear.x)
        ang = float(msg.angular.z)
        mode = 'stop'

        if abs(lin) < 0.02 and abs(ang) < 0.015:
            pass
        else:
            # Automatic Nav2 is forward-only for safety. Recovery reverse can be
            # enabled later after bumper/radar supervision is added.
            if lin > 0.02:
                out.linear.x = self.clamp(lin, 0.14, 0.24)
                mode = 'linear_boost'
            elif abs(ang) >= 0.015:
                out.linear.x = 0.12
                mode = 'turn_arc'

            if abs(ang) >= 0.015:
                scaled = ang * 2.5
                if abs(scaled) < 0.18:
                    scaled = math.copysign(0.18, scaled)
                out.angular.z = self.clamp(scaled, -0.35, 0.35)

        self.last_cmd_time = time.time()
        self.last_output = out
        self.pub.publish(out)
        self.status_pub.publish(String(data=f'{mode} in_x={lin:.3f} in_z={ang:.3f} out_x={out.linear.x:.3f} out_z={out.angular.z:.3f}'))

    def watchdog(self):
        if self.last_cmd_time and time.time() - self.last_cmd_time > 0.35:
            self.last_cmd_time = 0.0
            self.last_output = Twist()
            self.pub.publish(self.last_output)
            self.status_pub.publish(String(data='watchdog_stop'))


def main():
    rclpy.init()
    node = Nav2CmdAdapter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.pub.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
