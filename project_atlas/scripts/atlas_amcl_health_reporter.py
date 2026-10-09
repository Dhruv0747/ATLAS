#!/usr/bin/env python3
"""Diagnostic-only reporter. Never publishes pose, TF, commands or services."""
import json
import time
import rclpy
from rclpy.node import Node
from rclpy.clock import Clock, ClockType
from std_msgs.msg import String
from atlas_amcl_processing_health import ProcessingHealth


class Reporter(Node):
    def __init__(self):
        super().__init__('atlas_amcl_health_reporter')
        self.health = ProcessingHealth()
        self.create_subscription(String, 'atlas_amcl/processing', self.receive, 1)
        self.output = self.create_publisher(String, 'atlas/localization_health', 1)
        # A stopped simulated/system ROS clock must not freeze failure reports.
        self.wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(.2, self.publish, clock=self.wall_clock)

    def receive(self, msg):
        try:
            data = json.loads(msg.data)
        except (ValueError, TypeError):
            data = None
        self.health.ingest(data, self.get_clock().now().nanoseconds/1e9, time.monotonic())

    def publish(self):
        # A timer may report STALE; it never refreshes source timestamps.
        data = self.health.snapshot(self.get_clock().now().nanoseconds/1e9, time.monotonic())
        self.output.publish(String(data=json.dumps(data, allow_nan=False)))


def main():
    rclpy.init()
    node = Reporter()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
