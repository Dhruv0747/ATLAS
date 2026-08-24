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
import statistics
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
# Loaded-rover breakaway calibration. Commands below this floor only twitch;
# keep a usable control range above it instead of forcing every Nav2 request
# to near-full power.
MIN_RUN_PWM = 90
BOOST_TIME_S = 0.25
LOW_SPEED_HOLD_PWM = 45
PWM_RAMP_STEP = 8
CMD_TIMEOUT_S = 0.45
SERVO_UPDATE_TICKS = 2
STEER_RAMP_STEP_DEG = 6
CMD_ODOM_VX_SCALE = 1.0
CMD_ODOM_WZ_SCALE = 0.45

FRONT_STEER_SERVO_ID = 1    # Front steering servo port on Yahboom board (1-4)
REAR_STEER_SERVO_ID  = 2    # Rear steering servo port on Yahboom board (1-4)
# Ground trim after the replacement steering motors (2026-08-11).  A 90/90
# command produced a repeatable left arc.  Four-wheel opposite steering needs
# equal and opposite centre correction so angular.z=0 is physically straight.
FRONT_STEER_CENTER   = 83   # Straight-ahead angle (commissioned 2026-08-24)
REAR_STEER_CENTER    = 106  # Straight-ahead angle (commissioned 2026-08-24)
# Lifted-wheel physical commissioning (2026-08-24). These are independent
# asymmetric endpoints; do not derive rear limits from the front geometry.
FRONT_STEER_RIGHT    = 58
FRONT_STEER_LEFT     = 130
REAR_STEER_RIGHT     = 58
REAR_STEER_LEFT      = 142
BAT_MIN_V = 10.5
BAT_MAX_V = 12.6

# Verified ATLAS wheel geometry and provisional per-channel calibration.
# Physical order is the controller order: M1 FR, M2 FL, M3 BR, M4 BL.
WHEEL_CIRCUMFERENCE_M = 0.392699
WHEELBASE_M = 0.367
# Ground calibration (2026-08-05): a nominal 0.0508 m odometry move covered
# approximately 0.30 m physically, establishing a 5.91x distance correction.
# Calibrated on the ground with the installed 125 mm wheels and final shafts.
# A measured 0.20 m straight run is used independently for every channel;
# the controller's four encoder channels have materially different scales.
ENCODER_COUNTS_PER_REV = (4048.7, 3300.6, 4080.1, 2697.8)
# Individually verified physical-forward polarity (wheels lifted, 2026-08-05):
# M1/M4 require positive PWM; M2/M3 require negative PWM. Encoder polarity
# follows those physical-forward raw signs, so normalize them all positive.
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
        self._front_applied_angle = FRONT_STEER_CENTER
        self._rear_applied_angle = REAR_STEER_CENTER
        self._last_enc = None
        self._enc_origin = None
        self._enc_rate_anchor = None
        self._enc_rate_anchor_t = time.monotonic()
        self._wheel_cps = [0.0, 0.0, 0.0, 0.0]
        self._wheel_mps = [0.0, 0.0, 0.0, 0.0]
        self._wheel_distance_m = [0.0, 0.0, 0.0, 0.0]
        self._last_odom_wheel_distance = None
        self._last_enc_t = time.monotonic()
        self._last_enc_change_t = time.monotonic()
        self._encoder_stale = True
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._last_odom_t = time.monotonic()
        self._last_watchdog_ping = 0.0

        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)

        self._pub_volt = self.create_publisher(Float32, '/battery/voltage', 10)
        self._pub_curr = self.create_publisher(Float32, '/battery/current', 10)
        self._pub_pct = self.create_publisher(Float32, '/battery/percent', 10)

        self._pub_motion_vx = self.create_publisher(Float32, '/yahboom/motion/vx', 10)
        self._pub_motion_vy = self.create_publisher(Float32, '/yahboom/motion/vy', 10)
        self._pub_motion_vz = self.create_publisher(Float32, '/yahboom/motion/vz', 10)
        self._pub_odom = self.create_publisher(Odometry, '/yahboom/odom', 10)
        self._pub_odom_source = self.create_publisher(String, '/yahboom/odom_source', 10)

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
        self._watchdog_ping(force=True)

    def _watchdog_ping(self, force=False):
        """Feed systemd from the critical motor loop, at most once per second.

        A standalone ROS timer can be delayed behind other ready callbacks when
        the Jetson is busy.  Feeding from the motor keepalive proves that the
        actual safety/control loop is still being scheduled, while the existing
        five-second systemd watchdog continues to restart a genuinely wedged
        driver.
        """
        now = time.monotonic()
        if not force and now - self._last_watchdog_ping < 1.0:
            return
        self._last_watchdog_ping = now
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
            self._applied_pwm = 0
            self.bot.set_motor(0, 0, 0, 0)

    def _motor_keepalive(self):
        self._watchdog_ping()
        if time.time() - self._last_cmd_time > CMD_TIMEOUT_S:
            self._last_vx = 0.0
            self._last_vz = 0.0
        self._drive_pwm(self._last_vx, self._last_vz)
        self._servo_tick = getattr(self, '_servo_tick', 0) + 1
        if self._servo_tick >= SERVO_UPDATE_TICKS:
            self._servo_tick = 0
            try:
                self._front_applied_angle = self._step_toward(
                    self._front_applied_angle,
                    self._front_target_angle,
                    STEER_RAMP_STEP_DEG,
                )
                self._rear_applied_angle = self._step_toward(
                    self._rear_applied_angle,
                    self._rear_target_angle,
                    STEER_RAMP_STEP_DEG,
                )
                self.bot.set_pwm_servo(FRONT_STEER_SERVO_ID, self._front_applied_angle)
                self.bot.set_pwm_servo(REAR_STEER_SERVO_ID, self._rear_applied_angle)
            except Exception:
                pass

    @staticmethod
    def _step_toward(current, target, step):
        """Move one bounded step toward target without overshooting it."""
        if current < target:
            return min(current + step, target)
        if current > target:
            return max(current - step, target)
        return target

    def _slew_motor_pwm(self, target_pwm):
        """Smooth normal drive changes while retaining an immediate safe stop."""
        if target_pwm == 0:
            return 0

        current = self._applied_pwm
        if current != 0 and (current > 0) != (target_pwm > 0):
            # Never drive directly through zero when the operator reverses.
            return 0

        if current == 0:
            start = min(abs(target_pwm), LOW_SPEED_HOLD_PWM)
            return start if target_pwm > 0 else -start

        return int(self._step_toward(current, target_pwm, PWM_RAMP_STEP))

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
        self._applied_pwm = self._slew_motor_pwm(pwm)
        # Individually verified ATLAS polarity: positive ROS linear.x must move
        # every wheel toward the physical front of the rover.
        self.bot.set_motor(
            self._applied_pwm,
            -self._applied_pwm,
            -self._applied_pwm,
            self._applied_pwm,
        )
        steer_norm = max(-1.0, min(1.0, wz / MAX_WZ))
        if steer_norm >= 0.0:
            # Positive ROS angular.z is a left turn: front points left while
            # the rear counter-steers right.
            front_angle = FRONT_STEER_CENTER + steer_norm * (
                FRONT_STEER_LEFT - FRONT_STEER_CENTER
            )
            rear_angle = REAR_STEER_CENTER + steer_norm * (
                REAR_STEER_RIGHT - REAR_STEER_CENTER
            )
        else:
            turn = -steer_norm
            front_angle = FRONT_STEER_CENTER + turn * (
                FRONT_STEER_RIGHT - FRONT_STEER_CENTER
            )
            rear_angle = REAR_STEER_CENTER + turn * (
                REAR_STEER_LEFT - REAR_STEER_CENTER
            )
        self._front_target_angle = int(round(front_angle))
        self._rear_target_angle = int(round(rear_angle))
        self._pub_front_steer.publish(Float32(data=float(self._front_applied_angle)))
        self._pub_rear_steer.publish(Float32(data=float(self._rear_applied_angle)))
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
            self._wheel_distance_m[i] = distance_m
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

        # Integrate measured encoder position deltas, not a delayed speed
        # estimate. The controller reports counts in bursts; integrating the
        # half-second CPS estimate lost the beginning and end of short moves.
        # Use the median so one channel with a different encoder resolution
        # (currently M4) cannot bias navigation distance. Raw values from all
        # four channels remain published for diagnostics and later calibration.
        wheel_distance = statistics.median(self._wheel_distance_m)
        if self._last_odom_wheel_distance is None:
            distance_delta = 0.0
        else:
            distance_delta = wheel_distance - self._last_odom_wheel_distance
        self._last_odom_wheel_distance = wheel_distance

        encoder_motion = abs(distance_delta) > 1.0e-6 and dt > 0.0
        if encoder_motion:
            vx = distance_delta / dt
            vy = 0.0
            front_delta = math.radians(FRONT_STEER_CENTER - self._front_applied_angle)
            rear_delta = math.radians(REAR_STEER_CENTER - self._rear_applied_angle)
            curvature = (math.tan(front_delta) - math.tan(rear_delta)) / WHEELBASE_M
            vz = vx * curvature
            source = 'wheel_encoder_delta_4ws'
        else:
            vx = 0.0
            vy = 0.0
            vz = 0.0
            curvature = 0.0
            source = 'stopped'

        self._last_odom_source = source
        self._pub_odom_source.publish(String(data=source))

        delta_yaw = distance_delta * curvature
        yaw_mid = self._yaw + 0.5 * delta_yaw
        self._x += distance_delta * math.cos(yaw_mid)
        self._y += distance_delta * math.sin(yaw_mid)
        self._yaw += delta_yaw

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
        self._applied_pwm = 0
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
