#!/usr/bin/env python3
"""Air-lifted verification of ATLAS metric wheel telemetry.

Safety properties: fixed 0.8 second motion window, modest command, repeated
zero commands on normal exit and exceptions. Never run with wheels grounded.
"""
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Float32


WHEELS = ('front_right', 'front_left', 'back_right', 'back_left')


class MetricWheelTest(Node):
    def __init__(self):
        super().__init__('atlas_metric_wheel_air_test')
        self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.peaks = {name: 0.0 for name in WHEELS}
        for name in WHEELS:
            self.create_subscription(
                Float32,
                f'/yahboom/wheel/{name}/rpm',
                lambda message, wheel=name: self._rpm(wheel, message.data),
                10,
            )

    def _rpm(self, wheel, value):
        if abs(value) > abs(self.peaks[wheel]):
            self.peaks[wheel] = float(value)

    def command(self, speed):
        message = Twist()
        message.linear.x = float(speed)
        self.publisher.publish(message)


def main():
    rclpy.init()
    node = MetricWheelTest()
    try:
        # Allow DDS discovery for every wheel subscription before motion.
        start = time.monotonic()
        while time.monotonic() - start < 2.0:
            node.command(0.0)
            rclpy.spin_once(node, timeout_sec=0.02)
        start = time.monotonic()
        while time.monotonic() - start < 0.8:
            node.command(0.20)
            rclpy.spin_once(node, timeout_sec=0.02)
        start = time.monotonic()
        while time.monotonic() - start < 1.5:
            node.command(0.0)
            rclpy.spin_once(node, timeout_sec=0.02)
    finally:
        for _ in range(10):
            node.command(0.0)
            rclpy.spin_once(node, timeout_sec=0.02)
            time.sleep(0.02)
        print('SAFETY STOP: /cmd_vel zero')
        for name in WHEELS:
            print(f'{name}: peak_rpm={node.peaks[name]:+.2f}')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
