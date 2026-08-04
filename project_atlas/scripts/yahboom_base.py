#!/usr/bin/env python3
"""
Yahboom ROS robot control board driver -- ROS2 Jazzy.
Subscribes : /cmd_vel
Publishes  : battery, board motion, board IMU, encoder, and Yahboom odom topics.
"""
import math
import os
from pathlib import Path
import socket
import sys
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import Float32, Int32, String
from tf2_ros import TransformBroadcaster

sys.path.insert(0, str(Path(__file__).resolve().parent))
from Rosmaster_Lib import Rosmaster

MAX_VX = 1.0
MAX_WZ = 2.0
MAX_PWM = 100
MIN_RUN_PWM = 72
BOOST_TIME_S = 0.25
LOW_SPEED_HOLD_PWM = 45
PWM_RAMP_STEP = 4
CMD_ODOM_VX_SCALE = 1.0
CMD_ODOM_WZ_SCALE = 0.45

FRONT_STEER_SERVO_ID = 1    # Front steering servo port on Yahboom board (1-4)
REAR_STEER_SERVO_ID  = 2    # Rear steering servo port on Yahboom board (1-4)
FRONT_STEER_CENTER   = 90   # Straight-ahead angle (degrees)
REAR_STEER_CENTER    = 90   # Straight-ahead angle (degrees)
STEER_RANGE          = 30   # Normal/right max deflection each side
STEER_LEFT_RANGE     = 42   # Extra left throw to match right mechanical angle
STEER_RIGHT_RANGE    = 30
REAR_STEER_GAIN      = 1.0  # 1.0 = full opposite rear steering
BAT_MIN_V = 10.5
BAT_MAX_V = 12.6

# Verified ATLAS wheel geometry and provisional per-channel calibration.
# Physical order is the controller order: M1 FR, M2 FL, M3 BR, M4 BL.
WHEEL_CIRCUMFERENCE_M = 0.392699
WHEELBASE_M = 0.367
ENCODER_COUNTS_PER_REV = (6077.0, 5579.0, 6157.0, 6494.0)
# Normal forward drive commands M1/M4 positive and M2/M3 negative.
ENCODER_FORWARD_SIGN = (1.0, -1.0, -1.0, 1.0)


def systemd_notify(message: str) -> None:
    """Send a readiness/watchdog message without requiring python3-systemd."""
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notify_socket:
            notify_socket.settimeout(0.2)
            notify_socket.connect(address)
            notify_socket.sendall(message.encode("utf-8"))
    except OSError:
        # The motor safety path must never depend on status notification.
        pass


class YahboomBase(Node):
    def __init__(self):
        super().__init__('yahboom_base')

        self.bot = Rosmaster(car_type=5, com='/dev/yahboom')
        self.bot.create_receive_threading()
        self.bot.set_car_type(5)
        self.bot.set_auto_report_state(True, False)
        time.sleep(1.0)

        self._last_vx = 0.0
        self._last_vz = 0.0
        self._last_cmd_time = 0.0
        self._boost_until = 0.0
        self._applied_pwm = 0
        self._front_target_angle = FRONT_STEER_CENTER
        self._rear_target_angle = REAR_STEER_CENTER
        self._last_enc = None
        self._enc_origin = None
        self._enc_rate_anchor = None
        self._enc_rate_anchor_t = time.monotonic()
        self._wheel_cps = [0.0, 0.0, 0.0, 0.0]
        self._wheel_mps = [0.0, 0.0, 0.0, 0.0]
        self._last_enc_t = time.monotonic()
        self._last_enc_change_t = time.monotonic()
        self._encoder_stale = True
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._last_odom_t = time.monotonic()

        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)

        self._pub_volt = self.create_publisher(Float32, '/battery/voltage', 10)
        self._pub_curr = self.create_publisher(Float32, '/battery/current', 10)
        self._pub_pct = self.create_publisher(Float32, '/battery/percent', 10)

        self._pub_motion_vx = self.create_publisher(Float32, '/yahboom/motion/vx', 10)
        self._pub_motion_vy = self.create_publisher(Float32, '/yahboom/motion/vy', 10)
        self._pub_motion_vz = self.create_publisher(Float32, '/yahboom/motion/vz', 10)
        self._pub_odom = self.create_publisher(Odometry, '/yahboom/odom', 10)
        self._pub_main_odom = self.create_publisher(Odometry, '/odom', 10)
        self._pub_odom_source = self.create_publisher(String, '/yahboom/odom_source', 10)
        self._tf_broadcaster = TransformBroadcaster(self)

        self._pub_roll = self.create_publisher(Float32, '/yahboom/imu/roll', 10)
        self._pub_pitch = self.create_publisher(Float32, '/yahboom/imu/pitch', 10)
        self._pub_heading = self.create_publisher(Float32, '/yahboom/imu/heading', 10)

        self._enc_pubs = [
            self.create_publisher(Int32, '/yahboom/encoder/m1', 10),
            self.create_publisher(Int32, '/yahboom/encoder/m2', 10),
            self.create_publisher(Int32, '/yahboom/encoder/m3', 10),
            self.create_publisher(Int32, '/yahboom/encoder/m4', 10),
        ]
        wheel_names = ('front_right', 'front_left', 'back_right', 'back_left')
        self._wheel_rpm_pubs = [self.create_publisher(Float32, f'/yahboom/wheel/{name}/rpm', 10) for name in wheel_names]
        self._wheel_mps_pubs = [self.create_publisher(Float32, f'/yahboom/wheel/{name}/speed_mps', 10) for name in wheel_names]
        self._wheel_distance_pubs = [self.create_publisher(Float32, f'/yahboom/wheel/{name}/distance_m', 10) for name in wheel_names]
        self._pub_fl = self.create_publisher(Float32, '/motor/front_left', 10)
        self._pub_fr = self.create_publisher(Float32, '/motor/front_right', 10)
        self._pub_rl = self.create_publisher(Float32, '/motor/rear_left', 10)
        self._pub_rr = self.create_publisher(Float32, '/motor/rear_right', 10)
        self._pub_left = self.create_publisher(Float32, '/motors/left', 10)
        self._pub_right = self.create_publisher(Float32, '/motors/right', 10)
        self._pub_speed = self.create_publisher(Float32, '/motor_speed', 10)
        self._pub_front_steer = self.create_publisher(Float32, '/steering/front_angle_deg', 10)
        self._pub_rear_steer = self.create_publisher(Float32, '/steering/rear_angle_deg', 10)
        self._pub_steer_mode = self.create_publisher(String, '/steering/mode', 10)

        self.create_timer(0.1, self._motor_keepalive)
        self.create_timer(0.1, self._publish_board_state)
        self.create_timer(1.0, self._publish_battery)
        self.create_timer(1.0, self._systemd_watchdog)

        version = self.bot.get_version()
        car_type = self.bot.get_car_type_from_machine()
        self.get_logger().info(f'Yahboom board ready on /dev/yahboom, firmware={version}, car_type={car_type}')
        systemd_notify(
            "READY=1\n"
            "STATUS=Yahboom serial and ROS odometry publisher online"
        )

    def _systemd_watchdog(self):
        # If the ROS executor or DDS participant stalls, this timer also stops.
        # systemd then kills the wedged process and safely reopens /dev/yahboom.
        systemd_notify(
            "WATCHDOG=1\n"
            f"STATUS=Base online; odom source={getattr(self, '_last_odom_source', 'starting')}"
        )

    def _on_cmd_vel(self, msg: Twist):
        vx = max(-1.0, min(1.0, msg.linear.x / MAX_VX))
        vz = max(-5.0, min(5.0, msg.angular.z))
        # Zero commands must stop immediately. Never ignore a stop packet.
        if abs(vx) <= 0.02:
            vx = 0.0
        if abs(vz) <= 0.02:
            vz = 0.0
        self._last_vx = vx
        self._last_vz = vz
        self._last_cmd_time = time.time()
        if vx == 0.0 and vz == 0.0:
            self.bot.set_motor(0, 0, 0, 0)

    def _motor_keepalive(self):
        if time.time() - self._last_cmd_time > 0.25:
            self._last_vx = 0.0
            self._last_vz = 0.0
        self._drive_pwm(self._last_vx, self._last_vz)
        self._servo_tick = getattr(self, '_servo_tick', 0) + 1
        if self._servo_tick >= 5:
            self._servo_tick = 0
            try:
                self.bot.set_pwm_servo(FRONT_STEER_SERVO_ID, self._front_target_angle)
                self.bot.set_pwm_servo(REAR_STEER_SERVO_ID, self._rear_target_angle)
            except Exception:
                pass

    def _drive_pwm(self, vx, wz):
        drive = max(-1.0, min(1.0, vx))
        if abs(drive) <= 0.02:
            pwm = 0
        else:
            # The loaded rover cannot overcome static friction at the small
            # percentages produced by Nav2 (e.g. 0.15 -> 15 PWM). Preserve
            # direction and map every real motion request into the verified
            # usable 72..100 PWM range.
            magnitude = MIN_RUN_PWM + int(
                (MAX_PWM - MIN_RUN_PWM) * abs(drive)
            )
            pwm = magnitude if drive > 0.0 else -magnitude
        self.bot.set_motor(pwm, -pwm, -pwm, pwm)
        steer_norm = max(-1.0, min(1.0, wz / MAX_WZ))
        steer_range = STEER_LEFT_RANGE if steer_norm > 0 else STEER_RIGHT_RANGE
        steer = steer_norm * steer_range
        front_angle = int(FRONT_STEER_CENTER - steer)
        rear_angle = int(REAR_STEER_CENTER + steer * REAR_STEER_GAIN)
        min_angle = min(FRONT_STEER_CENTER - STEER_LEFT_RANGE, FRONT_STEER_CENTER - STEER_RIGHT_RANGE)
        max_angle = max(FRONT_STEER_CENTER + STEER_LEFT_RANGE, FRONT_STEER_CENTER + STEER_RIGHT_RANGE)
        self._front_target_angle = max(min_angle, min(max_angle, front_angle))
        self._rear_target_angle = max(min_angle, min(max_angle, rear_angle))
        self._pub_front_steer.publish(Float32(data=float(self._front_target_angle)))
        self._pub_rear_steer.publish(Float32(data=float(self._rear_target_angle)))
        self._pub_steer_mode.publish(String(data='four_wheel_opposite'))

    def _servo_loop(self):
        pass  # replaced by keepalive throttle

    def _publish_board_state(self):
        now = time.monotonic()
        vx, vy, vz = self.bot.get_motion_data()
        self._pub_motion_vx.publish(Float32(data=float(vx)))
        self._pub_motion_vy.publish(Float32(data=float(vy)))
        self._pub_motion_vz.publish(Float32(data=float(vz)))

        roll, pitch, yaw_deg = self.bot.get_imu_attitude_data(True)
        self._pub_roll.publish(Float32(data=float(roll)))
        self._pub_pitch.publish(Float32(data=float(pitch)))
        self._pub_heading.publish(Float32(data=float((yaw_deg + 360.0) % 360.0)))

        enc = self.bot.get_motor_encoder()
        if self._enc_origin is None:
            self._enc_origin = tuple(enc)
        if self._enc_rate_anchor is None:
            self._enc_rate_anchor = tuple(enc)
            self._enc_rate_anchor_t = now
        elif now - self._enc_rate_anchor_t >= 0.5:
            rate_dt = max(0.001, now - self._enc_rate_anchor_t)
            self._wheel_cps = [
                (float(enc[i]) - float(self._enc_rate_anchor[i])) / rate_dt
                for i in range(4)
            ]
            self._enc_rate_anchor = tuple(enc)
            self._enc_rate_anchor_t = now
        for pub, val in zip(self._enc_pubs, enc):
            pub.publish(Int32(data=int(val)))

        if self._last_enc is None:
            speeds = [0.0, 0.0, 0.0, 0.0]
            enc_changed = False
        else:
            dt = max(0.001, now - self._last_enc_t)
            enc_delta = [enc[i] - self._last_enc[i] for i in range(4)]
            speeds = [enc_delta[i] / dt for i in range(4)]
            enc_changed = any(abs(v) > 2 for v in enc_delta)
        for i in range(4):
            # Use a half-second count window.  The board reports encoder data
            # in bursts, so a single 100 ms delta produces misleading spikes.
            signed_cps = float(self._wheel_cps[i]) * ENCODER_FORWARD_SIGN[i]
            rpm = signed_cps * 60.0 / ENCODER_COUNTS_PER_REV[i]
            speed_mps = signed_cps * WHEEL_CIRCUMFERENCE_M / ENCODER_COUNTS_PER_REV[i]
            self._wheel_mps[i] = speed_mps
            signed_counts = (float(enc[i]) - float(self._enc_origin[i])) * ENCODER_FORWARD_SIGN[i]
            distance_m = signed_counts * WHEEL_CIRCUMFERENCE_M / ENCODER_COUNTS_PER_REV[i]
            self._wheel_rpm_pubs[i].publish(Float32(data=rpm))
            self._wheel_mps_pubs[i].publish(Float32(data=speed_mps))
            self._wheel_distance_pubs[i].publish(Float32(data=distance_m))
        if enc_changed:
            self._last_enc_change_t = now
            self._encoder_stale = False
        self._last_enc = enc
        self._last_enc_t = now

        # Verified physical motor mapping (2026-08-04):
        # M1=front-right, M2=front-left, M3=back-right, M4=back-left.
        # Keep ROS wheel topics physical-position based even though the
        # controller exposes channels in a different order.
        fr, fl, rr, rl = [float(v) for v in speeds]
        self._pub_fl.publish(Float32(data=fl))
        self._pub_fr.publish(Float32(data=fr))
        self._pub_rl.publish(Float32(data=rl))
        self._pub_rr.publish(Float32(data=rr))
        self._pub_left.publish(Float32(data=(fl + rl) / 2.0))
        self._pub_right.publish(Float32(data=(fr + rr) / 2.0))
        self._pub_speed.publish(Float32(data=float(vx)))

        self._publish_yahboom_odom(vx, vy, vz, now)

    def _publish_yahboom_odom(self, board_vx, board_vy, board_vz, now):
        dt = max(0.0, min(0.5, now - self._last_odom_t))
        self._last_odom_t = now

        cmd_age = time.time() - self._last_cmd_time
        cmd_active = cmd_age <= 0.35 and (
            abs(self._last_vx) > 0.02 or abs(self._last_vz) > 0.02
        )
        encoder_recent = now - self._last_enc_change_t <= 0.50
        if cmd_active and encoder_recent:
            # Real wheel odometry. Physical order is FR, FL, BR, BL. Average
            # the independently calibrated wheel speeds so one slipping wheel
            # cannot dominate the position estimate.
            vx = sum(self._wheel_mps) / 4.0
            vy = 0.0
            front_delta = math.radians(FRONT_STEER_CENTER - self._front_target_angle)
            rear_delta = math.radians(REAR_STEER_CENTER - self._rear_target_angle)
            # General bicycle relation for front and rear steering. With
            # ATLAS counter-steering, the two tangent terms add.
            vz = vx * (math.tan(front_delta) - math.tan(rear_delta)) / WHEELBASE_M
            source = 'wheel_encoder_4ws'
        else:
            vx = 0.0
            vy = 0.0
            vz = 0.0
            source = 'stopped' if not cmd_active else 'commanded_encoder_stale'

        self._last_odom_source = source
        if cmd_active and not encoder_recent:
            self._encoder_stale = True
        self._pub_odom_source.publish(String(data=source))

        self._yaw += float(vz) * dt
        cy = math.cos(self._yaw)
        sy = math.sin(self._yaw)
        self._x += (float(vx) * cy - float(vy) * sy) * dt
        self._y += (float(vx) * sy + float(vy) * cy) * dt

        stamp = self.get_clock().now().to_msg()
        qz = math.sin(self._yaw / 2.0)
        qw = math.cos(self._yaw / 2.0)

        msg = Odometry()
        msg.header.stamp = stamp
        msg.header.frame_id = 'odom'
        msg.child_frame_id = 'base_link'
        msg.pose.pose.position.x = self._x
        msg.pose.pose.position.y = self._y
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw
        msg.pose.covariance[0] = 0.05
        msg.pose.covariance[7] = 0.05
        msg.pose.covariance[35] = 0.10
        msg.twist.twist.linear.x = float(vx)
        msg.twist.twist.linear.y = float(vy)
        msg.twist.twist.angular.z = float(vz)
        msg.twist.covariance[0] = 0.10
        msg.twist.covariance[7] = 0.10
        msg.twist.covariance[35] = 0.20
        self._pub_odom.publish(msg)
        self._pub_main_odom.publish(msg)

        tf = TransformStamped()
        tf.header.stamp = stamp
        tf.header.frame_id = 'odom'
        tf.child_frame_id = 'base_link'
        tf.transform.translation.x = self._x
        tf.transform.translation.y = self._y
        tf.transform.translation.z = 0.0
        tf.transform.rotation.z = qz
        tf.transform.rotation.w = qw
        self._tf_broadcaster.sendTransform(tf)

    def _publish_battery(self):
        try:
            volt = self.bot.get_battery_voltage()
            if volt is None:
                volt = 0.0
            mv = Float32(data=float(volt))
            mc = Float32(data=0.0)
            if volt >= 5.0:
                pct = max(0.0, min(100.0, (volt - BAT_MIN_V) / (BAT_MAX_V - BAT_MIN_V) * 100.0))
            else:
                pct = 0.0
            mp = Float32(data=float(pct))
            self._pub_volt.publish(mv)
            self._pub_curr.publish(mc)
            self._pub_pct.publish(mp)
        except Exception as e:
            self.get_logger().warn(f'Battery read error: {e}')

    def stop(self):
        systemd_notify("STOPPING=1\nSTATUS=Stopping Yahboom base")
        self.bot.set_motor(0, 0, 0, 0)


def main():
    rclpy.init()
    node = YahboomBase()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
