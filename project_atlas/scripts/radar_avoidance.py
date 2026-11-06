#!/usr/bin/env python3
"""Radar safety relay: /cmd_vel_teleop + /radar/targets -> /cmd_vel
Blocks forward motion when T1 Y < STOP_DIST_MM."""
import rclpy, time
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String

STOP_DIST_MM = 400   # stop if target closer than this
CLEAR_DIST_MM = 500  # resume only when target farther than this (hysteresis)

class RadarAvoidance(Node):
    def __init__(self):
        super().__init__('radar_avoidance')
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(Twist, '/cmd_vel_teleop', self.cmd_cb, 10)
        self.create_subscription(String, '/radar/targets', self.radar_cb, 10)
        self.blocked = False
        self.last_radar = 0.0
        self.radar_y = -1
        self.get_logger().info(
            f'Radar avoidance active (stop <{STOP_DIST_MM}mm, clear >{CLEAR_DIST_MM}mm)')

    def radar_cb(self, msg):
        self.last_radar = time.time()
        self.radar_y = -1
        for part in msg.data.split('|'):
            part = part.strip()
            if part.startswith('T1:'):
                try:
                    self.radar_y = int(part.split('y=')[1].split('mm')[0])
                except Exception:
                    pass
                break
        # Update blocked state with hysteresis
        if self.radar_y > 0:
            if not self.blocked and self.radar_y < STOP_DIST_MM:
                self.blocked = True
                self.get_logger().warn(f'BLOCKED: obstacle at {self.radar_y}mm')
                stop = Twist()
                self.pub.publish(stop)
            elif self.blocked and self.radar_y > CLEAR_DIST_MM:
                self.blocked = False
                self.get_logger().info(f'CLEAR: obstacle now at {self.radar_y}mm')

    def cmd_cb(self, msg):
        # Radar data stale (>2s) = pass through (safe default)
        radar_stale = (time.time() - self.last_radar) > 2.0
        if self.blocked and not radar_stale:
            # Only block forward motion; allow reversing
            if msg.linear.x > 0:
                stop = Twist()
                self.pub.publish(stop)
                return
        self.pub.publish(msg)

def main():
    rclpy.init()
    node = RadarAvoidance()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
