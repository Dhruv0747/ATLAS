#!/usr/bin/env python3
"""Safety-bounded person-follow controller for Project ATLAS.

The node starts disabled, accepts an explicit Bool enable command, publishes on
the lowest-priority autonomous velocity channel, and continuously publishes
zero when target/sensor data is stale or an obstacle is too close.
"""

import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, Float32, Int32, String


class AtlasFollowPerson(Node):
    def __init__(self):
        super().__init__('atlas_follow_person')
        self.enabled = False
        self.person = None
        self.person_at = 0.0
        self.front_mm = -1.0
        self.front_at = 0.0
        self.lidar_front_m = math.inf
        self.lidar_at = 0.0
        self.pan_us = 1300
        self.pub = self.create_publisher(Twist, '/cmd_vel_nav', 10)
        self.status = self.create_publisher(String, '/atlas/follow_person/status', 10)
        self.create_subscription(Bool, '/atlas/follow_person/enabled', self.enable_cb, 10)
        self.create_subscription(String, '/camera/detections/json', self.detections_cb, 10)
        self.create_subscription(Float32, '/ultrasonic/front_mm', self.front_cb, 10)
        self.create_subscription(Int32, '/camera/bottom_servo_us', self.pan_cb, 10)
        self.create_subscription(LaserScan, '/scan', self.scan_cb, 10)
        self.create_timer(0.10, self.control)
        self.publish_status('OFF - awaiting confirmed command')

    def publish_status(self, text):
        self.status.publish(String(data=text))

    def stop(self):
        self.pub.publish(Twist())

    def enable_cb(self, msg):
        self.enabled = bool(msg.data)
        self.stop()
        self.publish_status('ARMED - finding person' if self.enabled else 'OFF - stopped')

    def detections_cb(self, msg):
        try:
            data = json.loads(msg.data)
            width = float(data.get('width', 0))
            height = float(data.get('height', 0))
            people = [d for d in data.get('detections', [])
                      if d.get('label') == 'person' and float(d.get('confidence', 0)) >= 0.50]
            if width <= 0 or height <= 0 or not people:
                return
            # Prefer the largest person, which is normally the intended nearby leader.
            target = max(people, key=lambda d: (d['x2']-d['x1']) * (d['y2']-d['y1']))
            self.person = {
                'x_error': ((target['x1'] + target['x2']) * 0.5 - width * 0.5) / (width * 0.5),
                'height_ratio': (target['y2'] - target['y1']) / height,
                'confidence': float(target.get('confidence', 0)),
            }
            self.person_at = time.monotonic()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

    def front_cb(self, msg):
        self.front_mm = float(msg.data)
        self.front_at = time.monotonic()

    def pan_cb(self, msg):
        self.pan_us = int(msg.data)

    def scan_cb(self, msg):
        nearest = math.inf
        angle = msg.angle_min
        for value in msg.ranges:
            if abs(angle) <= math.radians(24) and math.isfinite(value) and value >= msg.range_min:
                nearest = min(nearest, value)
            angle += msg.angle_increment
        self.lidar_front_m = nearest
        self.lidar_at = time.monotonic()

    def control(self):
        if not self.enabled:
            return
        now = time.monotonic()
        if self.person is None or now - self.person_at > 0.75:
            self.stop()
            self.publish_status('PAUSED - person lost; camera searching')
            return

        ultrasonic_valid = now - self.front_at < 0.8 and self.front_mm > 0
        lidar_valid = now - self.lidar_at < 0.8 and math.isfinite(self.lidar_front_m)
        if not ultrasonic_valid and not lidar_valid:
            self.stop()
            self.publish_status('BLOCKED - front safety sensors stale')
            return
        if (ultrasonic_valid and self.front_mm < 380) or (lidar_valid and self.lidar_front_m < 0.38):
            self.stop()
            distance = min(self.front_mm / 1000.0 if ultrasonic_valid else math.inf,
                           self.lidar_front_m if lidar_valid else math.inf)
            self.publish_status(f'BLOCKED - obstacle {distance:.2f} m')
            return

        target = self.person
        # Camera tracker keeps the person centered, so pan displacement is also
        # steering error. Positive pan values correspond to the current rig's left.
        pan_error = max(-1.0, min(1.0, (self.pan_us - 1300) / 700.0))
        steering_error = max(-1.0, min(1.0, 0.65 * pan_error - 0.35 * target['x_error']))
        cmd = Twist()
        cmd.angular.z = max(-0.42, min(0.42, 0.55 * steering_error))

        # Bounding-box size is a conservative monocular distance proxy. Never
        # reverse automatically; stop when the leader is close enough.
        size = target['height_ratio']
        if size < 0.52 and abs(steering_error) < 0.72:
            cmd.linear.x = max(0.07, min(0.14, (0.52 - size) * 0.55))
            if abs(steering_error) > 0.38:
                cmd.linear.x *= 0.55
        self.pub.publish(cmd)
        self.publish_status(
            f'FOLLOWING - person {target["confidence"]*100:.0f}% '
            f'size {size:.2f} v {cmd.linear.x:.2f} w {cmd.angular.z:.2f}'
        )


def main():
    rclpy.init()
    node = AtlasFollowPerson()
    try:
        rclpy.spin(node)
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
