#!/usr/bin/env python3
"""Bounded, sensor-guarded recovery for ATLAS when Nav2 cannot form a path."""
import math
from enum import Enum, auto

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from nav2_msgs.srv import ClearEntireCostmap
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, Empty, Float32, String


class Phase(Enum):
    IDLE = auto()
    CLEARING = auto()
    PULSE = auto()
    SETTLE = auto()
    LOCKOUT = auto()


class TightRecovery(Node):
    def __init__(self):
        super().__init__('atlas_tight_space_recovery')
        self.declare_parameter('enabled', True)
        self.declare_parameter('request_cooldown_s', 20.0)
        self.declare_parameter('sensor_timeout_s', 1.5)
        self.declare_parameter('front_clear_m', 0.55)
        self.declare_parameter('rear_clear_m', 0.55)
        self.declare_parameter('side_clear_m', 0.28)
        self.declare_parameter('pulse_speed', 0.12)
        self.declare_parameter('pulse_duration_s', 0.8)
        self.declare_parameter('minimum_progress_m', 0.025)
        self.declare_parameter('max_attempts', 3)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel_web', 10)
        self.status_pub = self.create_publisher(String, '/atlas/tight_recovery_status', 10)
        self.resume_pub = self.create_publisher(Bool, '/explore/resume', 10)
        self.create_subscription(Empty, '/atlas/tight_recovery_request', self.request, 10)
        self.create_subscription(LaserScan, '/scan', self.scan_cb, qos_profile_sensor_data)
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)
        for name in ('front', 'left', 'right'):
            self.create_subscription(Float32, f'/ultrasonic/{name}_mm',
                                     lambda msg, n=name: self.ultra_cb(n, msg), 10)
        self.clear_clients = [
            self.create_client(ClearEntireCostmap, '/global_costmap/clear_entirely_global_costmap'),
            self.create_client(ClearEntireCostmap, '/local_costmap/clear_entirely_local_costmap')]
        self.phase = Phase.IDLE
        self.scan = None
        self.scan_time = 0.0
        self.ultra = {'front': math.inf, 'left': math.inf, 'right': math.inf}
        self.ultra_time = {'front': 0.0, 'left': 0.0, 'right': 0.0}
        self.odom = None
        self.start_xy = None
        self.deadline = 0.0
        self.last_request = -1e9
        self.attempts = 0
        self.direction = 0.0
        self.timer = self.create_timer(0.1, self.tick)
        self.report('READY: recovery idle; no motion commanded')

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def report(self, text):
        self.status_pub.publish(String(data=text))
        self.get_logger().info(text)

    def scan_cb(self, msg):
        self.scan, self.scan_time = msg, self.now_s()

    def ultra_cb(self, name, msg):
        value = float(msg.data)
        # A negative/no-echo sample is unavailable, not an obstacle. LiDAR is
        # authoritative; only a positive ultrasonic return may tighten it.
        self.ultra[name] = (
            value / 1000.0 if value > 10.0
            else value if value > 0.0
            else math.inf
        )
        self.ultra_time[name] = self.now_s()

    def odom_cb(self, msg):
        p = msg.pose.pose.position
        self.odom = (p.x, p.y)

    def sector_min(self, center_deg, width_deg):
        if self.scan is None:
            return math.inf
        vals = []
        for i, value in enumerate(self.scan.ranges):
            if not math.isfinite(value) or value < self.scan.range_min:
                continue
            angle = math.degrees(self.scan.angle_min + i * self.scan.angle_increment)
            delta = (angle - center_deg + 180.0) % 360.0 - 180.0
            if abs(delta) <= width_deg:
                vals.append(value)
        return min(vals) if vals else math.inf

    def sensors_fresh(self):
        age = self.get_parameter('sensor_timeout_s').value
        now = self.now_s()
        # Recovery requires fresh LiDAR and odometry. Ultrasonics are optional
        # close-range vetoes because open space may legitimately return no echo.
        return now - self.scan_time <= age

    def request(self, _msg):
        now = self.now_s()
        if not self.get_parameter('enabled').value or self.phase != Phase.IDLE:
            return
        if now - self.last_request < self.get_parameter('request_cooldown_s').value:
            self.report('WAIT: recovery request suppressed by cooldown')
            return
        self.last_request = now
        if not self.sensors_fresh() or self.odom is None:
            self.stop('BLOCKED: stale LiDAR/ultrasonic/odometry; no recovery motion')
            return
        self.resume_pub.publish(Bool(data=False))
        self.phase = Phase.CLEARING
        self.deadline = now + 0.8
        for client in self.clear_clients:
            if client.service_is_ready():
                client.call_async(ClearEntireCostmap.Request())
        self.report('RECOVERY: Nav2 paused; costmaps clearing')

    def choose_motion(self):
        front = min(self.sector_min(0.0, 25.0), self.ultra['front'])
        rear = self.sector_min(180.0, 25.0)
        left = min(self.sector_min(70.0, 25.0), self.ultra['left'])
        right = min(self.sector_min(-70.0, 25.0), self.ultra['right'])
        fc = self.get_parameter('front_clear_m').value
        rc = self.get_parameter('rear_clear_m').value
        sc = self.get_parameter('side_clear_m').value
        if front > fc and left > sc and right > sc:
            return self.get_parameter('pulse_speed').value, 0.0, 'forward'
        if front > fc and max(left, right) > sc:
            turn = 0.25 if left > right else -0.25
            return 0.09, turn, 'forward arc toward clearer side'
        if rear > rc:
            return -0.08, 0.0, 'reverse'
        return None

    def still_safe(self):
        if not self.sensors_fresh():
            return False
        if self.direction > 0:
            return min(self.sector_min(0.0, 25.0), self.ultra['front']) > 0.34
        return self.sector_min(180.0, 25.0) > 0.34

    def publish_cmd(self, linear=0.0, angular=0.0):
        msg = Twist()
        msg.linear.x, msg.angular.z = float(linear), float(angular)
        self.cmd_pub.publish(msg)

    def stop(self, reason):
        self.publish_cmd()
        self.phase = Phase.LOCKOUT if reason.startswith('BLOCKED') else Phase.IDLE
        self.report(reason)

    def tick(self):
        now = self.now_s()
        if self.phase == Phase.CLEARING and now >= self.deadline:
            motion = self.choose_motion()
            if motion is None:
                self.stop('BLOCKED: no sensor-confirmed escape corridor; human help required')
                return
            linear, angular, label = motion
            self.direction = linear
            self.start_xy = self.odom
            self.attempts += 1
            self.deadline = now + self.get_parameter('pulse_duration_s').value
            self.phase = Phase.PULSE
            self.report(f'RECOVERY: bounded {label} pulse, attempt {self.attempts}')
            self.publish_cmd(linear, angular)
        elif self.phase == Phase.PULSE:
            if not self.still_safe():
                self.stop('BLOCKED: obstacle or stale sensor detected during pulse')
                return
            if now < self.deadline:
                motion = self.choose_motion()
                if motion is not None:
                    self.publish_cmd(motion[0], motion[1])
                return
            self.publish_cmd()
            self.phase = Phase.SETTLE
            self.deadline = now + 0.6
        elif self.phase == Phase.SETTLE and now >= self.deadline:
            progress = 0.0
            if self.start_xy and self.odom:
                progress = math.hypot(self.odom[0] - self.start_xy[0], self.odom[1] - self.start_xy[1])
            if progress < self.get_parameter('minimum_progress_m').value:
                self.stop(f'BLOCKED: drivetrain made only {progress:.3f} m progress')
                return
            for client in self.clear_clients:
                if client.service_is_ready():
                    client.call_async(ClearEntireCostmap.Request())
            self.phase = Phase.IDLE
            self.resume_pub.publish(Bool(data=True))
            self.report(f'RECOVERED: moved {progress:.3f} m; costmaps cleared and Nav2 resumed')


def main():
    rclpy.init()
    node = TightRecovery()
    try:
        rclpy.spin(node)
    finally:
        # systemd may deliver SIGTERM after rclpy has already invalidated the
        # context. The active mux watchdog independently commands zero, so a
        # failed final courtesy publish must never turn a clean restart into a
        # traceback/restart loop.
        try:
            if rclpy.ok():
                node.publish_cmd()
        except rclpy.exceptions.RCLError:
            pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
