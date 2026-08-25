#!/usr/bin/env python3
"""Bounded, sensor-guarded recovery for ATLAS when Nav2 cannot form a path."""
import math
from enum import Enum, auto

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from nav2_msgs.srv import ClearEntireCostmap
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, Empty, Float32, String

from atlas_scan_geometry import ray_in_base_sector


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
        # LiDAR is mounted about 5 cm behind rover centre while the body ends
        # 30 cm ahead. Requiring 0.65 m at the sensor preserves roughly 30 cm
        # ahead of the physical nose before selecting a forward escape.
        self.declare_parameter('front_clear_m', 0.65)
        self.declare_parameter('rear_clear_m', 0.55)
        self.declare_parameter('side_clear_m', 0.28)
        self.declare_parameter('pulse_speed', 0.12)
        # The commissioned steering driver holds traction until both axles
        # settle. Allow enough wall-clock time for that safe gate, but end the
        # pulse by measured displacement so the extra time cannot create an
        # unbounded movement.
        self.declare_parameter('pulse_duration_s', 1.4)
        # ATLAS can coast several centimetres after zero is commanded. Keep
        # the powered portion short and let the settle phase measure the full
        # result.
        self.declare_parameter('pulse_max_progress_m', 0.04)
        self.declare_parameter('minimum_progress_m', 0.025)
        self.declare_parameter('max_attempts', 3)
        self.declare_parameter('laser_yaw_deg', 180.0)
        # Dedicated mux input: dashboard/web zero-heartbeats must never cancel
        # a sensor-guarded recovery pulse. The physical remote still has higher
        # priority and can immediately take control.
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel_recovery', 10)
        self.status_pub = self.create_publisher(String, '/atlas/tight_recovery_status', 10)
        self.resume_pub = self.create_publisher(Bool, '/explore/resume', 10)
        self.create_subscription(Empty, '/atlas/tight_recovery_request', self.request, 10)
        self.create_subscription(LaserScan, '/scan', self.scan_cb, qos_profile_sensor_data)
        # Short recovery displacement must come directly from wheel odometry.
        # Fused /odom can be delayed or corrected by the EKF/SLAM stack and
        # once allowed a pulse to run past its cap before reporting 0.383 m.
        self.create_subscription(Odometry, '/yahboom/odom', self.odom_cb, 20)
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
        self.previous_odom = None
        self.odom_discontinuity = False
        self.start_xy = None
        self.deadline = 0.0
        self.last_request = -1e9
        self.attempts = 0
        self.direction = 0.0
        self.angular = 0.0
        self.avoid_forward = False
        self.lockout_clear_since = None
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
        current = (p.x, p.y)
        if self.previous_odom is not None and self.phase in (
            Phase.PULSE, Phase.SETTLE
        ):
            step = math.hypot(
                current[0] - self.previous_odom[0],
                current[1] - self.previous_odom[1],
            )
            if step > 0.12:
                self.odom_discontinuity = True
        self.previous_odom = current
        self.odom = current

    def sector_min(self, center_deg, width_deg):
        if self.scan is None:
            return math.inf
        vals = []
        for i, value in enumerate(self.scan.ranges):
            if not math.isfinite(value) or value < self.scan.range_min:
                continue
            angle = math.degrees(self.scan.angle_min + i * self.scan.angle_increment)
            if ray_in_base_sector(
                angle,
                center_deg,
                width_deg,
                self.get_parameter('laser_yaw_deg').value,
            ):
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
        self.attempts = 0
        self.avoid_forward = False
        self.odom_discontinuity = False
        self.lockout_clear_since = None
        self.phase = Phase.CLEARING
        self.deadline = now + 0.8
        for client in self.clear_clients:
            if client.service_is_ready():
                client.call_async(ClearEntireCostmap.Request())
        self.report('RECOVERY: Nav2 paused; costmaps clearing')

    def choose_motion(self):
        # Match atlas_safety_status exactly.  A narrower recovery sector once
        # classified a door/wall edge as clear while the operator safety view
        # correctly reported it at 0.52 m, allowing a forward pulse into the
        # obstruction. Recovery must never be less conservative than the main
        # safety monitor.
        front = min(self.sector_min(0.0, 35.0), self.ultra['front'])
        rear = self.sector_min(180.0, 35.0)
        left = min(self.sector_min(77.5, 42.5), self.ultra['left'])
        right = min(self.sector_min(-77.5, 42.5), self.ultra['right'])
        fc = self.get_parameter('front_clear_m').value
        rc = self.get_parameter('rear_clear_m').value
        sc = self.get_parameter('side_clear_m').value
        if self.avoid_forward and rear > rc and max(left, right) > sc:
            turn = -0.25 if left > right else 0.25
            return -0.09, turn, 'alternate reverse arc toward clearer side'
        if front > fc and left > sc and right > sc:
            return self.get_parameter('pulse_speed').value, 0.0, 'forward'
        if front > fc and max(left, right) > sc:
            turn = 0.25 if left > right else -0.25
            return 0.09, turn, 'forward arc toward clearer side'
        if rear > rc and max(left, right) > sc:
            # When reversing, the rear of the rover sweeps opposite the yaw
            # direction. Choose the sign that moves the rear into the clearer
            # side corridor; signed steering kinematics handle the axle angles.
            turn = -0.25 if left > right else 0.25
            return -0.09, turn, 'reverse arc toward clearer side'
        if rear > rc:
            # Match the verified ATLAS drivetrain deadband. The previous
            # 0.08 m/s command was safe but too small to turn the wheels.
            return -self.get_parameter('pulse_speed').value, 0.0, 'reverse'
        return None

    def still_safe(self):
        if not self.sensors_fresh():
            return False
        if self.direction > 0:
            travel_clear = min(
                self.sector_min(0.0, 35.0), self.ultra['front']
            ) > 0.34
            swept_side = 77.5 if self.angular > 0 else -77.5
        else:
            travel_clear = self.sector_min(180.0, 35.0) > 0.34
            # Positive yaw while reversing sweeps the rear toward the right.
            swept_side = -77.5 if self.angular > 0 else 77.5
        if not travel_clear:
            return False
        if abs(self.angular) < 1e-3:
            return True
        return self.sector_min(swept_side, 42.5) > 0.20

    def publish_cmd(self, linear=0.0, angular=0.0):
        msg = Twist()
        msg.linear.x, msg.angular.z = float(linear), float(angular)
        self.cmd_pub.publish(msg)

    def measured_progress(self):
        if self.start_xy and self.odom:
            return math.hypot(
                self.odom[0] - self.start_xy[0],
                self.odom[1] - self.start_xy[1],
            )
        return 0.0

    def stop(self, reason):
        self.publish_cmd()
        self.phase = Phase.LOCKOUT if reason.startswith('BLOCKED') else Phase.IDLE
        if self.phase == Phase.LOCKOUT:
            self.lockout_clear_since = None
        self.report(reason)

    def tick(self):
        now = self.now_s()
        if self.phase == Phase.LOCKOUT:
            # A lockout must prevent repeated blind recovery pulses, but it
            # must not survive forever after the operator safely repositions
            # ATLAS. Re-arm only after fresh sensors show a usable corridor
            # continuously; this branch never publishes a motion command.
            corridor_clear = (
                self.sensors_fresh()
                and self.odom is not None
                and self.choose_motion() is not None
            )
            if not corridor_clear:
                self.lockout_clear_since = None
                return
            if self.lockout_clear_since is None:
                self.lockout_clear_since = now
                return
            if now - self.lockout_clear_since >= 1.0:
                self.phase = Phase.IDLE
                self.lockout_clear_since = None
                self.report(
                    'READY: sensor-confirmed manual reposition; recovery re-armed'
                )
            return
        if self.phase == Phase.CLEARING and now >= self.deadline:
            motion = self.choose_motion()
            if motion is None:
                self.stop('BLOCKED: no sensor-confirmed escape corridor; human help required')
                return
            linear, angular, label = motion
            self.direction = linear
            self.angular = angular
            self.start_xy = self.odom
            self.attempts += 1
            self.deadline = now + self.get_parameter('pulse_duration_s').value
            self.phase = Phase.PULSE
            self.report(f'RECOVERY: bounded {label} pulse, attempt {self.attempts}')
            self.publish_cmd(linear, angular)
        elif self.phase == Phase.PULSE:
            if self.odom_discontinuity:
                self.stop('BLOCKED: wheel odometry reset during recovery pulse')
                return
            if not self.still_safe():
                self.stop('BLOCKED: obstacle or stale sensor detected during pulse')
                return
            if self.measured_progress() >= self.get_parameter(
                'pulse_max_progress_m'
            ).value:
                self.publish_cmd()
                self.phase = Phase.SETTLE
                self.deadline = now + 0.6
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
            progress = self.measured_progress()
            if progress < self.get_parameter('minimum_progress_m').value:
                if self.attempts < self.get_parameter('max_attempts').value:
                    self.avoid_forward = True
                    self.phase = Phase.CLEARING
                    self.deadline = now + 1.0
                    for client in self.clear_clients:
                        if client.service_is_ready():
                            client.call_async(ClearEntireCostmap.Request())
                    self.report(
                        f'RETRYING: only {progress:.3f} m progress; '
                        'selecting a different sensor-confirmed escape'
                    )
                    return
                self.stop(
                    f'BLOCKED: drivetrain made only {progress:.3f} m '
                    f'progress after {self.attempts} attempts'
                )
                return
            for client in self.clear_clients:
                if client.service_is_ready():
                    client.call_async(ClearEntireCostmap.Request())
            self.phase = Phase.IDLE
            self.attempts = 0
            self.avoid_forward = False
            self.resume_pub.publish(Bool(data=True))
            self.report(f'RECOVERED: moved {progress:.3f} m; costmaps cleared and Nav2 resumed')


def main():
    rclpy.init()
    node = TightRecovery()
    try:
        rclpy.spin(node)
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
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
