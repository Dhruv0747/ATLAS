#!/usr/bin/env python3
"""
Yahboom ROS robot control board driver -- ROS2 Jazzy.
Subscribes : /cmd_vel
Publishes  : battery, board motion, board IMU, encoder, and Yahboom odom topics.
"""
import math
import os
import json
from pathlib import Path
import socket
import statistics
import sys
import time

import rclpy
import yaml
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from geometry_msgs.msg import TransformStamped, Twist, Vector3, Vector3Stamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu, Joy
from std_msgs.msg import Float32, Int32, String, Empty
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import TransformBroadcaster

sys.path.insert(0, str(Path(__file__).resolve().parent))
from Rosmaster_Lib import Rosmaster
from atlas_usb_identity import open_verified
from atlas_steering_commission import SteeringCommission
from atlas_encoder_selection import (
    ENCODER_NAMES, WHEEL_NAMES, EncoderDeltaEstimator,
    feedback_state, validate_selection,
)

MAX_VX = 1.0
MAX_WZ = 2.0
MAX_PWM = 100
# Loaded-rover manual calibration.  The former 90 PWM floor translated an
# ordinary 0.52 joystick command to 95 PWM and turbo to 96 PWM, effectively
# running all four channels at the board ceiling.  Ground recordings then
# showed all four wheels stopping together under sustained load.  Retain the
# measured breakaway margin while leaving useful control/headroom.
MIN_RUN_PWM = 80
REMOTE_MAX_PWM = 90
# teleop_twist_joy publishes at most 0.52 in normal mode and 0.65 while its
# turbo button is held.  Keep high-current traction explicit and momentary:
# normal manual driving retains the stable range above, while turbo receives
# the commissioned near-maximum breakaway torque for climbing only.
REMOTE_BOOST_THRESHOLD = 0.60
REMOTE_BOOST_MIN_PWM = 94
REMOTE_BOOST_MAX_PWM = 100
# Autonomous approach commands need a lower floor than manual driving.  The
# loaded rover was previously validated at 72 PWM; retaining 90 for every small
# Nav2 command caused a repeatable 10 cm request to travel 16--19 cm.  Keep the
# stronger manual floor, but use this bounded floor for Web/Nav2/recovery motion.
AUTONOMOUS_MIN_RUN_PWM = 60
BOOST_TIME_S = 0.25
LOW_SPEED_HOLD_PWM = 45
PWM_RAMP_STEP = 8
CMD_TIMEOUT_S = 0.45
REMOTE_SOURCE_GRACE_S = 2.0
# Apply smaller steering increments at every 100 ms control tick.  This keeps
# the commissioned 30 deg/s slew rate while removing the coarse 6-degree jump
# that made low-speed right steering feel abrupt.
SERVO_UPDATE_TICKS = 1
# Two degrees per 100 ms gives a smooth 20 deg/s manual steering slew while
# remaining responsive.  The former 3-degree steps were visible as shaking on
# the large installed steering linkage.
STEER_RAMP_STEP_DEG = 2
# Four equal wheel speeds force the tyres to scrub during a 4WS turn.  Keep
# every powered wheel at or above the commissioned breakaway PWM, but give the
# outside pair a small speed advantage and the inside pair a small reduction.
TURN_PWM_BIAS = 8
CMD_ODOM_VX_SCALE = 1.0
CMD_ODOM_WZ_SCALE = 0.45
ODOM_STATE_SAVE_PERIOD_S = 0.20
ENCODER_FREEZE_S = 1.20
ENCODER_START_GRACE_S = 0.80
ENCODER_SINGLE_GRACE_S = 5.0
ENCODER_LINK_QUALIFY_S = 3.0

FRONT_STEER_SERVO_ID = 2    # Physical front confirmed by user 2026-09-09
REAR_STEER_SERVO_ID  = 1    # Physical rear confirmed by user 2026-09-09
# User requested 90/90 neutral with all wheels lifted (2026-09-18).
# Previous visually confirmed trim was front=91, rear=89. Servo commands are
# not measured wheel angles; straight-ground travel needs rechecking at 90/90.
FRONT_STEER_CENTER   = 90
REAR_STEER_CENTER    = 90
# Lifted-wheel physical commissioning (2026-08-24). These are independent
# asymmetric endpoints; do not derive rear limits from the front geometry.
# Extended right endpoint requested during supervised recommissioning.  This
# 42-degree setting must be physically validated before autonomous driving;
# immediately restore 52 if the linkage contacts, strains, or the servo buzzes.
# Preserve existing numeric endpoint envelope per physical servo channel.
# Direction and full-range travel require revalidation after channel correction.
# These names are retained for configuration-file compatibility.  Physical
# commissioning on 2026-09-20 confirmed that the installed front linkage is
# reversed: servo-low (50) is physical LEFT and servo-high (121) is RIGHT.
FRONT_STEER_RIGHT    = 50   # servo-low endpoint; physical front-left
FRONT_STEER_LEFT     = 121  # servo-high endpoint; physical front-right
REAR_STEER_RIGHT     = 59   # User-approved lifted right operating limit 2026-09-20
REAR_STEER_LEFT      = 134  # User-approved lifted left operating limit 2026-09-09
BAT_MIN_V = 10.5
BAT_MAX_V = 12.6

# Verified ATLAS wheel geometry and provisional per-channel calibration.
# Physical controller order verified 2026-09-17: M1 RL, M2 RR, M3 FL, M4 FR.
WHEEL_CIRCUMFERENCE_M = 0.392699
WHEELBASE_M = 0.367
# Ground calibration (2026-08-05): a nominal 0.0508 m odometry move covered
# approximately 0.30 m physically, establishing a 5.91x distance correction.
# Calibrated on the ground with the installed 125 mm wheels and final shafts.
# A measured 0.20 m straight run is used independently for every channel;
# the controller's four encoder channels have materially different scales.
ENCODER_COUNTS_PER_REV = (4048.7, 3300.6, 4080.1, 2697.8)
# Lifted forward signs verified for M1-M3, 2026-09-17. M4 encoder is faulty:
# its retained sign is UNVALIDATED, not inferred from PWM. Metric calibration
# above predates motor replacement and requires revalidation before driving.
ENCODER_FORWARD_SIGN = (-1.0, 1.0, 1.0, 1.0)
YAHBOOM_USB_ID = '/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0'


def motor_outputs(left_pwm, right_pwm):
    """Physical-forward side commands to verified controller PWM channels."""
    return (-left_pwm, right_pwm, -left_pwm, right_pwm)


def resolve_yahboom_port():
    """Find the Yahboom controller by identity, never by ttyUSB number."""
    configured = os.environ.get('ATLAS_YAHBOOM_PORT', '').strip()
    if configured:
        if not Path(configured).exists():
            raise RuntimeError(f'Configured Yahboom port absent: {configured}; no fallback permitted')
        return configured
    candidates = [
        configured,
        '/dev/yahboom',
        '/dev/atlas-yahboom',
        YAHBOOM_USB_ID,
    ]
    by_id = Path('/dev/serial/by-id')
    if by_id.is_dir():
        candidates.extend(str(path) for path in sorted(
            by_id.glob('usb-1a86_USB_Serial*-if00-port0')
        ))

    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            if Path(candidate).exists():
                return candidate

    checked = ', '.join(seen)
    raise RuntimeError(
        f'Yahboom motor controller not found; checked stable paths: {checked}'
    )
YAHBOOM_IMU_CALIBRATION = Path(os.environ.get(
    'ATLAS_YAHBOOM_IMU_CALIBRATION',
    '/home/jetson/project_atlas/config/yahboom_imu_calibration.yaml',
))


def _wrap_degrees(angle):
    """Return an angle in the ROS-friendly [-180, 180) interval."""
    return (float(angle) + 180.0) % 360.0 - 180.0


def _rpy_quaternion(roll_deg, pitch_deg, yaw_deg):
    """Convert calibrated board roll/pitch/yaw degrees to a quaternion."""
    roll = math.radians(float(roll_deg))
    pitch = math.radians(float(pitch_deg))
    yaw = math.radians(float(yaw_deg))
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _load_imu_calibration(path):
    """Load software offsets without making motor startup depend on the file."""
    defaults = {
        'roll_zero_deg': 0.0,
        'pitch_zero_deg': 0.0,
        'heading_zero_deg': 0.0,
        'heading_reference_mode': 'static',
        'gyro_bias_rad_s': [0.0, 0.0, 0.0],
        'accel_bias_m_s2': [0.0, 0.0, 0.0],
        'orientation_variance_rad2': 0.01,
        'angular_velocity_variance': 0.01,
        'linear_acceleration_variance': 0.10,
        'qualified_for_navigation': False,
    }
    try:
        raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        values = raw.get('yahboom_imu_calibration', raw)
        for key in defaults:
            if key in values:
                defaults[key] = values[key]
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        pass
    return defaults


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

        # Validate BEFORE opening the hardware. Missing/bad config must not
        # silently reinstate the known faulty encoder.
        selection_path = Path(__file__).resolve().parent.parent / 'config' / 'encoder_selection.yaml'
        with selection_path.open(encoding='utf-8') as stream:
            self._excluded_encoders, self._encoder_navigation_validated, self._encoder_packet_timeout = validate_selection(yaml.safe_load(stream))
        self._encoder_packet_stamp = 0.0
        self._encoder_packet_fresh = False
        self._encoder_delta_estimator = EncoderDeltaEstimator()
        if os.environ.get('ATLAS_YAHBOOM_AUTO_USB', '0') == '1':
            # No library initialization/write until receive protocol is proven.
            link = open_verified('yahboom', os.environ.get('ATLAS_YAHBOOM_PORT', ''))
            self.yahboom_port = link.port
            self.bot = Rosmaster(car_type=5, com=self.yahboom_port, serial_link=link)
        else:
            self.yahboom_port = resolve_yahboom_port()
            self.bot = Rosmaster(car_type=5, com=self.yahboom_port)
        self.bot.create_receive_threading()
        self.bot.set_car_type(5)
        self.bot.set_auto_report_state(True, False)
        time.sleep(1.0)

        self._last_vx = 0.0
        self._last_vz = 0.0
        self._drive_source = 'STOPPED'
        self._last_remote_source_time = 0.0
        self._last_cmd_time = 0.0
        self._boost_until = 0.0
        self._applied_pwm = 0
        self._steering_cal = SteeringCommission(
            Path(__file__).resolve().parents[1] / 'config' / 'steering_calibration.json',
            {'front': {'center': FRONT_STEER_CENTER, 'left': FRONT_STEER_LEFT, 'right': FRONT_STEER_RIGHT},
             'rear': {'center': REAR_STEER_CENTER, 'left': REAR_STEER_LEFT, 'right': REAR_STEER_RIGHT}})
        self._apply_steering_calibration()
        self._cal_policy_time = 0.0
        self._cal_stop_latched = False
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
        self._wheel_last_change_t = [time.monotonic()] * 4
        self._encoder_motion_started = 0.0
        self._encoder_fault_since = {}
        self._encoder_health_started = time.monotonic()
        self._encoder_stale = True
        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        runtime_dir = Path(
            os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        )
        self._odom_state_path = runtime_dir / "atlas_yahboom_odom_state.json"
        self._last_odom_state_save = 0.0
        self._restore_odom_state()
        self._last_odom_t = time.monotonic()
        self._last_watchdog_ping = 0.0
        self._imu_calibration = _load_imu_calibration(YAHBOOM_IMU_CALIBRATION)
        self._imu_heading_reference = None
        self._last_imu_status = 0.0

        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)
        self.create_subscription(
            String, '/atlas/drive_mode', self._on_drive_mode, 10
        )

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
        self._pub_imu_uncalibrated = self.create_publisher(
            Imu, '/yahboom/imu/data_uncalibrated', 10
        )
        self._pub_imu_calibrated = self.create_publisher(
            Imu, '/yahboom/imu/data_calibrated', 10
        )
        self._pub_imu_mag_raw = self.create_publisher(
            Vector3Stamped, '/yahboom/imu/mag_raw', 10
        )
        self._pub_imu_calibration_status = self.create_publisher(
            String, '/yahboom/imu/calibration_status', 10
        )
        # Canonical system IMU topics. The motor-board IMU is the only active
        # ATLAS attitude source; the retired BNO08x must not own these names.
        self._pub_system_imu = self.create_publisher(Imu, '/imu/data', 10)
        self._pub_system_imu_euler = self.create_publisher(Vector3, '/imu/euler', 10)
        self._pub_system_imu_roll = self.create_publisher(Float32, '/imu/roll', 10)
        self._pub_system_imu_pitch = self.create_publisher(Float32, '/imu/pitch', 10)
        self._pub_system_imu_yaw = self.create_publisher(Float32, '/imu/yaw', 10)
        self._pub_system_imu_heading = self.create_publisher(Float32, '/imu/heading', 10)
        self._pub_system_imu_json = self.create_publisher(String, '/imu/dashboard_json', 10)
        self._pub_system_imu_source = self.create_publisher(String, '/imu/source', 10)
        self._pub_system_imu_status = self.create_publisher(
            String, '/imu/calibration_status', 10
        )

        self._enc_pubs = [
            self.create_publisher(Int32, '/yahboom/encoder/m1', 10),
            self.create_publisher(Int32, '/yahboom/encoder/m2', 10),
            self.create_publisher(Int32, '/yahboom/encoder/m3', 10),
            self.create_publisher(Int32, '/yahboom/encoder/m4', 10),
        ]
        self._pub_encoder_health = self.create_publisher(
            String, '/atlas/encoder_health', 10
        )
        wheel_names = WHEEL_NAMES
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
        self._cal_status_pub = self.create_publisher(String, '/atlas/steering_calibration/status', 10)
        self.create_subscription(String, '/atlas/steering_calibration/request', self._cal_request, 10)
        self.create_subscription(String, '/atlas/control_policy', self._cal_policy, 10)
        self.create_subscription(Empty, '/atlas/voice/stop', lambda _: self._cal_abort('Stop requested'), 10)
        self.create_subscription(Joy, '/joy', self._cal_joy, qos_profile_sensor_data)

        self.create_timer(0.1, self._motor_keepalive)
        self.create_timer(0.1, self._publish_board_state)
        self.create_timer(1.0, self._publish_battery)
        self.create_timer(1.0, self._systemd_watchdog)

        version = self.bot.get_version()
        car_type = self.bot.get_car_type_from_machine()
        self.get_logger().info(
            f'Yahboom board ready on {self.yahboom_port}, '
            f'firmware={version}, car_type={car_type}'
        )
        self.get_logger().info(
            'Yahboom IMU calibration loaded: '
            f"roll_zero={float(self._imu_calibration['roll_zero_deg']):.3f}deg "
            f"pitch_zero={float(self._imu_calibration['pitch_zero_deg']):.3f}deg "
            f"heading_zero={float(self._imu_calibration['heading_zero_deg']):.3f}deg; "
            'navigation qualification=' +
            str(bool(self._imu_calibration['qualified_for_navigation']))
        )
        systemd_notify(
            "READY=1\n"
            "STATUS=Yahboom serial and ROS odometry publisher online"
        )

    def _restore_odom_state(self):
        """Resume the odom origin after a same-boot USB/service restart.

        XDG_RUNTIME_DIR is tmpfs and is cleared on a full Jetson reboot. This
        preserves continuity across a transient CH341 disconnect without
        carrying an old coordinate origin into the next boot.
        """
        try:
            state = json.loads(self._odom_state_path.read_text(encoding="utf-8"))
            self._x = float(state["x"])
            self._y = float(state["y"])
            self._yaw = float(state["yaw"])
            self.get_logger().warn(
                "Resuming same-boot odometry after driver restart: "
                f"x={self._x:.3f} y={self._y:.3f} yaw={math.degrees(self._yaw):.1f}deg"
            )
        except (OSError, ValueError, KeyError, TypeError):
            return

    def _save_odom_state(self, now):
        if now - self._last_odom_state_save < ODOM_STATE_SAVE_PERIOD_S:
            return
        self._last_odom_state_save = now
        try:
            self._odom_state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._odom_state_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"x": self._x, "y": self._y, "yaw": self._yaw}) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self._odom_state_path)
        except OSError as exc:
            self.get_logger().warn(
                f"Could not checkpoint same-boot odometry: {exc}",
                throttle_duration_sec=10.0,
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

    def _apply_steering_calibration(self):
        global FRONT_STEER_CENTER, FRONT_STEER_LEFT, FRONT_STEER_RIGHT
        global REAR_STEER_CENTER, REAR_STEER_LEFT, REAR_STEER_RIGHT
        f, r = self._steering_cal.saved['front'], self._steering_cal.saved['rear']
        FRONT_STEER_CENTER, FRONT_STEER_LEFT, FRONT_STEER_RIGHT = f['center'], f['left'], f['right']
        REAR_STEER_CENTER, REAR_STEER_LEFT, REAR_STEER_RIGHT = r['center'], r['left'], r['right']

    def _cal_applied(self):
        return {'front': self._front_applied_angle, 'rear': self._rear_applied_angle}

    def _cal_policy(self, msg):
        try:
            self._cal_stop_latched = json.loads(msg.data).get('stop_latched') is True
            self._cal_policy_time = time.monotonic()
        except (ValueError, AttributeError):
            self._cal_stop_latched = False

    def _cal_safe(self):
        return (self._cal_stop_latched and time.monotonic() - self._cal_policy_time < 1.0
                and self._applied_pwm == 0 and self._last_vx == 0 and self._last_vz == 0)

    def _cal_abort(self, reason):
        self._steering_cal.freeze(self._cal_applied(), reason)

    def _cal_joy(self, msg):
        if len(msg.buttons) > 1 and msg.buttons[1]:
            self._cal_abort('Remote B stop')

    def _cal_request(self, msg):
        try:
            if len(msg.data) > 1024:
                raise ValueError('Oversized request')
            self._steering_cal.command(json.loads(msg.data), time.monotonic(), self._cal_applied(), self._cal_safe())
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            self._steering_cal.result = 'REJECTED: ' + str(exc)

    def _on_cmd_vel(self, msg: Twist):
        if self._steering_cal.locked:
            self._last_vx = self._last_vz = 0.0
            self._applied_pwm = 0
            self.bot.set_motor(0, 0, 0, 0)
            return
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

    def _on_drive_mode(self, msg: String):
        """Track mux ownership so manual steering can remain responsive."""
        self._drive_source = str(msg.data).strip().upper() or 'STOPPED'
        if self._drive_source == 'REMOTE':
            self._last_remote_source_time = time.monotonic()

    def _motor_keepalive(self):
        self._watchdog_ping()
        self._steering_cal.tick(time.monotonic(), self._cal_applied(), self._cal_safe())
        self._apply_steering_calibration()
        self._cal_status_pub.publish(String(data=json.dumps(self._steering_cal.status())))
        if time.time() - self._last_cmd_time > CMD_TIMEOUT_S:
            self._last_vx = 0.0
            self._last_vz = 0.0
        if self._steering_cal.locked:
            self._last_vx = self._last_vz = 0.0
            self._applied_pwm = 0
            self.bot.set_motor(0, 0, 0, 0)
            self._front_target_angle = self._steering_cal.targets['front']
            self._rear_target_angle = self._steering_cal.targets['rear']
            self._pub_front_steer.publish(Float32(data=float(self._front_applied_angle)))
            self._pub_rear_steer.publish(Float32(data=float(self._rear_applied_angle)))
            self._pub_steer_mode.publish(String(data='steering_calibration_traction_inhibited'))
        else:
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
            # The remote keeps the commissioned high breakaway floor.  Small
            # autonomous approach commands use the separately validated lower
            # floor so Nav2 can stop accurately without weakening manual drive.
            remote_boost = (
                self._drive_source == 'REMOTE'
                and abs(drive) >= REMOTE_BOOST_THRESHOLD
            )
            if remote_boost:
                min_run_pwm = REMOTE_BOOST_MIN_PWM
                max_run_pwm = REMOTE_BOOST_MAX_PWM
            elif self._drive_source == 'REMOTE':
                min_run_pwm = MIN_RUN_PWM
                max_run_pwm = REMOTE_MAX_PWM
            else:
                min_run_pwm = AUTONOMOUS_MIN_RUN_PWM
                max_run_pwm = MAX_PWM
            magnitude = min_run_pwm + int(
                (max_run_pwm - min_run_pwm) * abs(drive)
            )
            pwm = magnitude if drive > 0.0 else -magnitude
        if self._drive_source == 'REMOTE':
            # A physical joystick requests wheel position, not chassis yaw
            # rate.  Feeding remote input through the car-like wz/vx model
            # made the target jump near zero speed and reverse direction while
            # backing up.  Use direct, speed-independent four-wheel steering
            # for the operator; the servo slew limiter below keeps it smooth.
            steer_norm = max(-1.0, min(1.0, wz / MAX_WZ))
            if steer_norm >= 0.0:
                front_angle = FRONT_STEER_CENTER + steer_norm * (
                    FRONT_STEER_RIGHT - FRONT_STEER_CENTER
                )
                rear_angle = REAR_STEER_CENTER + steer_norm * (
                    REAR_STEER_RIGHT - REAR_STEER_CENTER
                )
            else:
                turn = -steer_norm
                front_angle = FRONT_STEER_CENTER + turn * (
                    FRONT_STEER_LEFT - FRONT_STEER_CENTER
                )
                rear_angle = REAR_STEER_CENTER + turn * (
                    REAR_STEER_LEFT - REAR_STEER_CENTER
                )
        elif abs(vx) > 0.02:
            # Four-wheel opposite steering kinematics:
            #   wz = 2 * vx * tan(delta) / wheelbase
            # The former wz/MAX_WZ mapping produced only ~3-6 degrees at
            # normal Nav2 speeds, while Hybrid-A* planned a 0.35 m radius.
            # It also steered reverse commands in the wrong curvature sense.
            # Signed vx is essential: the wheel angle must reverse when the
            # same yaw rate is requested while backing up.
            steer_delta = math.degrees(math.atan(
                (WHEELBASE_M * wz) / (2.0 * vx)
            ))
            steer_delta = max(-35.0, min(35.0, steer_delta))
            # Installed front linkage is servo-reversed: decreasing command
            # angle is physical left. Rear already decreases for physical
            # right, so a positive left-curving command decreases both servo
            # command angles.
            front_angle = FRONT_STEER_CENTER - steer_delta
            rear_angle = REAR_STEER_CENTER - steer_delta
        else:
            # Steering-only operator command: no kinematic curvature exists
            # at zero speed, so retain proportional wheel positioning. A full
            # zero command therefore returns both axles to their home centres.
            steer_norm = max(-1.0, min(1.0, wz / MAX_WZ))
            if steer_norm >= 0.0:
                front_angle = FRONT_STEER_CENTER + steer_norm * (
                    FRONT_STEER_RIGHT - FRONT_STEER_CENTER
                )
                rear_angle = REAR_STEER_CENTER + steer_norm * (
                    REAR_STEER_RIGHT - REAR_STEER_CENTER
                )
            else:
                turn = -steer_norm
                front_angle = FRONT_STEER_CENTER + turn * (
                    FRONT_STEER_LEFT - FRONT_STEER_CENTER
                )
                rear_angle = REAR_STEER_CENTER + turn * (
                    REAR_STEER_LEFT - REAR_STEER_CENTER
                )
        front_angle = max(FRONT_STEER_RIGHT, min(FRONT_STEER_LEFT, front_angle))
        rear_angle = max(REAR_STEER_RIGHT, min(REAR_STEER_LEFT, rear_angle))
        self._front_target_angle = int(round(front_angle))
        self._rear_target_angle = int(round(rear_angle))
        steering_error = max(
            abs(self._front_target_angle - self._front_applied_angle),
            abs(self._rear_target_angle - self._rear_applied_angle),
        )
        # Nav2/recovery must wait for steering alignment before traction; that
        # gate prevents the rover entering a doorway on the wrong wheel angle.
        # For the physical Xbox remote, however, a complete traction cut made
        # combined forward/reverse + steering nearly unusable.  Keep a bounded
        # breakaway-speed crawl while the operator holds both sticks, allowing
        # the wheels and steering servos to move simultaneously.
        if pwm and steering_error > 8 and self._drive_source == 'REMOTE':
            sign = 1 if pwm > 0 else -1
            self._applied_pwm = self._slew_motor_pwm(sign * MIN_RUN_PWM)
        elif pwm and steering_error > 8:
            self._applied_pwm = 0
        else:
            self._applied_pwm = self._slew_motor_pwm(pwm)
        # Individually verified ATLAS polarity: positive ROS linear.x must move
        # every wheel toward the physical front of the rover.
        right_pwm = self._applied_pwm
        left_pwm = self._applied_pwm
        if self._applied_pwm and abs(wz) > 0.02:
            magnitude = abs(self._applied_pwm)
            inside = max(MIN_RUN_PWM, magnitude - TURN_PWM_BIAS)
            outside = min(MAX_PWM, magnitude + TURN_PWM_BIAS)
            sign = 1 if self._applied_pwm > 0 else -1
            # Curvature is wz/vx.  Reverse motion swaps which side follows the
            # inside arc even when the requested yaw-rate sign is unchanged.
            if vx * wz > 0.0:  # left-curving path: left wheels are inside
                left_pwm, right_pwm = sign * inside, sign * outside
            else:  # right-curving path: right wheels are inside
                right_pwm, left_pwm = sign * inside, sign * outside
        self.bot.set_motor(*motor_outputs(left_pwm, right_pwm))
        self._pub_front_steer.publish(Float32(data=float(self._front_applied_angle)))
        self._pub_rear_steer.publish(Float32(data=float(self._rear_applied_angle)))
        self._pub_steer_mode.publish(String(data='four_wheel_opposite'))

    def _servo_loop(self):
        pass  # replaced by keepalive throttle

    def _publish_board_imu(self, monotonic_now, roll, pitch, yaw_deg):
        """Publish raw, calibrated and canonical motor-board IMU data.

        Yahboom is the primary system IMU for monitoring, bags and dashboards.
        It is not fused by the navigation EKF until a recorded left/right yaw
        sign and magnitude test passes.
        """
        stamp = self.get_clock().now().to_msg()
        ax, ay, az = self.bot.get_accelerometer_data()
        gx, gy, gz = self.bot.get_gyroscope_data()
        mx, my, mz = self.bot.get_magnetometer_data()

        raw_q = _rpy_quaternion(roll, pitch, yaw_deg)
        cal = self._imu_calibration
        if (
            cal['heading_reference_mode'] == 'startup_relative'
            and self._imu_heading_reference is None
        ):
            # Motor-board absolute heading is magnetically referenced and can
            # start at a different compass value after the controller is
            # reopened. Future EKF experiments need repeatable yaw change, not
            # an untrusted absolute compass origin.
            self._imu_heading_reference = float(yaw_deg)
        heading_reference = (
            self._imu_heading_reference
            if self._imu_heading_reference is not None
            else float(cal['heading_zero_deg'])
        )
        calibrated_rpy = (
            float(roll) - float(cal['roll_zero_deg']),
            float(pitch) - float(cal['pitch_zero_deg']),
            _wrap_degrees(float(yaw_deg) - heading_reference),
        )
        calibrated_q = _rpy_quaternion(*calibrated_rpy)
        gyro_bias = [float(v) for v in cal['gyro_bias_rad_s']]
        accel_bias = [float(v) for v in cal['accel_bias_m_s2']]

        def make_imu(quaternion, gyro, accel, calibrated):
            message = Imu()
            message.header.stamp = stamp
            message.header.frame_id = 'base_link'
            message.orientation.x = quaternion[0]
            message.orientation.y = quaternion[1]
            message.orientation.z = quaternion[2]
            message.orientation.w = quaternion[3]
            message.angular_velocity.x = gyro[0]
            message.angular_velocity.y = gyro[1]
            message.angular_velocity.z = gyro[2]
            message.linear_acceleration.x = accel[0]
            message.linear_acceleration.y = accel[1]
            message.linear_acceleration.z = accel[2]
            if calibrated:
                orientation_variance = float(cal['orientation_variance_rad2'])
                gyro_variance = float(cal['angular_velocity_variance'])
                accel_variance = float(cal['linear_acceleration_variance'])
                message.orientation_covariance = [
                    orientation_variance, 0.0, 0.0,
                    0.0, orientation_variance, 0.0,
                    0.0, 0.0, orientation_variance,
                ]
                message.angular_velocity_covariance = [
                    gyro_variance, 0.0, 0.0,
                    0.0, gyro_variance, 0.0,
                    0.0, 0.0, gyro_variance,
                ]
                message.linear_acceleration_covariance = [
                    accel_variance, 0.0, 0.0,
                    0.0, accel_variance, 0.0,
                    0.0, 0.0, accel_variance,
                ]
            else:
                # Raw controller values have not yet been accuracy-qualified.
                message.orientation_covariance[0] = -1.0
                message.angular_velocity_covariance[0] = -1.0
                message.linear_acceleration_covariance[0] = -1.0
            return message

        raw_imu = make_imu(
            raw_q, (gx, gy, gz), (ax, ay, az), False
        )
        calibrated_gyro = (
            gx - gyro_bias[0], gy - gyro_bias[1], gz - gyro_bias[2]
        )
        calibrated_accel = (
            ax - accel_bias[0], ay - accel_bias[1], az - accel_bias[2]
        )
        calibrated_imu = make_imu(
            calibrated_q,
            calibrated_gyro,
            calibrated_accel,
            True,
        )
        self._pub_imu_uncalibrated.publish(raw_imu)
        self._pub_imu_calibrated.publish(calibrated_imu)
        self._pub_system_imu.publish(calibrated_imu)

        cal_roll, cal_pitch, cal_yaw = calibrated_rpy
        cal_heading = (cal_yaw + 360.0) % 360.0
        self._pub_system_imu_euler.publish(Vector3(
            x=float(cal_roll), y=float(cal_pitch), z=float(cal_yaw)
        ))
        self._pub_system_imu_roll.publish(Float32(data=float(cal_roll)))
        self._pub_system_imu_pitch.publish(Float32(data=float(cal_pitch)))
        self._pub_system_imu_yaw.publish(Float32(data=float(cal_yaw)))
        self._pub_system_imu_heading.publish(Float32(data=float(cal_heading)))
        self._pub_system_imu_json.publish(String(data=json.dumps({
            'source': 'yahboom_motor_controller',
            'role': 'primary_system_imu',
            'navigation_fusion': 'disabled_pending_dynamic_yaw_validation',
            'roll': cal_roll,
            'pitch': cal_pitch,
            'yaw': cal_yaw,
            'heading': cal_heading,
            'qx': calibrated_q[0],
            'qy': calibrated_q[1],
            'qz': calibrated_q[2],
            'qw': calibrated_q[3],
            'gx': calibrated_gyro[0],
            'gy': calibrated_gyro[1],
            'gz': calibrated_gyro[2],
            'ax': calibrated_accel[0],
            'ay': calibrated_accel[1],
            'az': calibrated_accel[2],
            'mx_raw': float(mx),
            'my_raw': float(my),
            'mz_raw': float(mz),
            'frame': 'base_link',
            'heading_reference_mode': str(cal['heading_reference_mode']),
            'qualified_for_navigation': bool(cal['qualified_for_navigation']),
        }, separators=(',', ':'))))

        # The Yahboom library does not document magnetometer engineering units,
        # so publish them honestly as controller-native raw values rather than
        # incorrectly labelling them as tesla.
        mag = Vector3Stamped()
        mag.header.stamp = stamp
        mag.header.frame_id = 'base_link'
        mag.vector.x, mag.vector.y, mag.vector.z = float(mx), float(my), float(mz)
        self._pub_imu_mag_raw.publish(mag)

        if monotonic_now - self._last_imu_status >= 1.0:
            self._last_imu_status = monotonic_now
            status = json.dumps({
                'source': 'yahboom_motor_controller',
                'calibration_file': str(YAHBOOM_IMU_CALIBRATION),
                'roll_zero_deg': float(cal['roll_zero_deg']),
                'pitch_zero_deg': float(cal['pitch_zero_deg']),
                'heading_zero_deg': float(cal['heading_zero_deg']),
                'heading_reference_mode': str(cal['heading_reference_mode']),
                'runtime_heading_reference_deg': heading_reference,
                'qualified_for_navigation': bool(cal['qualified_for_navigation']),
                'role': 'primary_system_imu',
                'navigation_fusion': 'disabled_pending_dynamic_yaw_validation',
            }, separators=(',', ':'))
            status_message = String(data=status)
            self._pub_imu_calibration_status.publish(status_message)
            self._pub_system_imu_status.publish(status_message)
            self._pub_system_imu_source.publish(String(
                data='yahboom_motor_controller'
            ))

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
        self._publish_board_imu(now, roll, pitch, yaw_deg)

        enc, self._encoder_packet_stamp = self.bot.get_motor_encoder_sample()
        now = time.monotonic()
        self._encoder_packet_fresh = (
            self._encoder_packet_stamp > 0.0
            and 0.0 <= now - self._encoder_packet_stamp <= self._encoder_packet_timeout
        )
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
            enc_delta = [0, 0, 0, 0]
        else:
            dt = max(0.001, now - self._last_enc_t)
            enc_delta = [enc[i] - self._last_enc[i] for i in range(4)]
            speeds = [enc_delta[i] / dt for i in range(4)]
            enc_changed = any(abs(v) > 2 for v in enc_delta)
            for i, delta in enumerate(enc_delta):
                if abs(delta) > 2:
                    self._wheel_last_change_t[i] = now
                    self._encoder_fault_since.pop(i, None)
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

        # Verified physical motor mapping (2026-09-17):
        # M1=rear-left, M2=rear-right, M3=front-left, M4=front-right.
        # Keep ROS wheel topics physical-position based even though the
        # controller exposes channels in a different order.
        rl, rr, fl, fr = [float(v) for v in speeds]
        self._pub_fl.publish(Float32(data=fl))
        self._pub_fr.publish(Float32(data=fr))
        self._pub_rl.publish(Float32(data=rl))
        self._pub_rr.publish(Float32(data=rr))
        self._pub_left.publish(Float32(data=(fl + rl) / 2.0))
        self._pub_right.publish(Float32(data=rr if 3 in self._excluded_encoders else (fr + rr) / 2.0))
        self._pub_speed.publish(Float32(data=float(vx)))

        self._publish_encoder_health(now)

        self._publish_yahboom_odom(vx, vy, vz, now)

    def _publish_encoder_health(self, now):
        """Detect frozen wheel feedback while traction is actually applied."""
        traction = abs(self._applied_pwm) > 0
        if traction:
            if self._encoder_motion_started <= 0.0:
                self._encoder_motion_started = now
                # Begin every traction interval with a fresh per-wheel timing
                # baseline.  Otherwise a wheel that was correctly stationary
                # between Nav2 pulses inherits an old timestamp and can be
                # declared frozen immediately when motion resumes.
                self._wheel_last_change_t = [now] * 4
            if now - self._encoder_motion_started >= ENCODER_START_GRACE_S:
                for index, changed_at in enumerate(self._wheel_last_change_t):
                    if index not in self._excluded_encoders and now - changed_at > ENCODER_FREEZE_S:
                        self._encoder_fault_since.setdefault(index, now)
        else:
            self._encoder_motion_started = 0.0

        faults = sorted(i for i in self._encoder_fault_since if i not in self._excluded_encoders)
        longest = max(
            (now - self._encoder_fault_since[i] for i in faults),
            default=0.0,
        )
        qualifying = now - self._encoder_health_started < ENCODER_LINK_QUALIFY_S
        state, scale, reason = feedback_state(
            self._excluded_encoders, faults, self._encoder_packet_fresh,
            qualifying, traction, longest,
        )
        names = ENCODER_NAMES
        payload = {
            'state': state,
            'faults': [names[i] for i in faults],
            'excluded_encoders': [i + 1 for i in self._excluded_encoders],
            'selected_encoders': [i + 1 for i in range(4) if i not in self._excluded_encoders],
            'packet_age_s': round(max(0.0, now - self._encoder_packet_stamp), 3) if self._encoder_packet_stamp > 0.0 else None,
            'packet_fresh': self._encoder_packet_fresh,
            'navigation_validated': self._encoder_navigation_validated,
            'autonomy_ready': self._encoder_navigation_validated and scale > 0.0,
            'reason': reason if self._encoder_navigation_validated else reason + '; ground distance/turn validation pending',
            'scale': scale,
            'traction': traction,
            'fault_age_s': round(longest, 2),
            'validation_remaining_s': round(
                max(0.0, ENCODER_LINK_QUALIFY_S - (now - self._encoder_health_started)), 2
            ),
            'last_change_age_s': [
                round(max(0.0, now - stamp), 2)
                for stamp in self._wheel_last_change_t
            ],
            'policy': 'M4_excluded;selected_fault_or_stale=autonomy_stop;validation_required' if self._excluded_encoders else 'single=50%_for_5s;multi_or_persistent=stop',
        }
        self._pub_encoder_health.publish(
            String(data=json.dumps(payload, separators=(',', ':')))
        )

    def _publish_yahboom_odom(self, board_vx, board_vy, board_vz, now):
        dt = max(0.0, min(0.5, now - self._last_odom_t))
        self._last_odom_t = now

        # Integrate measured encoder position deltas, not a delayed speed
        # estimate. The controller reports counts in bursts; integrating the
        # half-second CPS estimate lost the beginning and end of short moves.
        # Deliberate exclusions never rejoin merely because counts reappear.
        # Raw M4 remains diagnostic only. No fallback to rejected channels.
        valid_indexes = [i for i in range(4)
                         if i not in self._excluded_encoders
                         and i not in self._encoder_fault_since]
        if not self._encoder_packet_fresh:
            valid_indexes = []
        distance_delta = self._encoder_delta_estimator.update(
            self._wheel_distance_m, valid_indexes
        )

        encoder_motion = abs(distance_delta) > 1.0e-6 and dt > 0.0
        if encoder_motion:
            vx = distance_delta / dt
            vy = 0.0
            # Front linkage is servo-reversed: decreasing command angle is
            # physical left. Convert it to the conventional positive-left
            # wheel angle before calculating four-wheel-steering curvature.
            front_delta = math.radians(FRONT_STEER_CENTER - self._front_applied_angle)
            rear_delta = math.radians(self._rear_applied_angle - REAR_STEER_CENTER)
            curvature = (math.tan(front_delta) - math.tan(rear_delta)) / WHEELBASE_M
            vz = vx * curvature
            source = (
                'wheel_encoder_delta_4ws'
                if len(valid_indexes) == 4
                else f'wheel_encoder_delta_degraded_{len(valid_indexes)}of4'
            )
        else:
            vx = 0.0
            vy = 0.0
            vz = 0.0
            curvature = 0.0
            source = 'feedback_unavailable' if len(valid_indexes) < 3 else (
                'stopped_M1_M2_M3_M4_excluded' if self._excluded_encoders else 'stopped'
            )

        self._last_odom_source = source
        self._pub_odom_source.publish(String(data=source))

        delta_yaw = distance_delta * curvature
        yaw_mid = self._yaw + 0.5 * delta_yaw
        self._x += distance_delta * math.cos(yaw_mid)
        self._y += distance_delta * math.sin(yaw_mid)
        self._yaw += delta_yaw
        self._save_odom_state(now)

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
        if len(valid_indexes) < 4:
            # Conservative provisional uncertainty, not a measured accuracy.
            factor = 4.0 if len(valid_indexes) == 3 else 1000.0
            for index in (0, 7, 35):
                msg.pose.covariance[index] *= factor
                msg.twist.covariance[index] *= factor
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
        self._save_odom_state(time.monotonic() + ODOM_STATE_SAVE_PERIOD_S)
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
