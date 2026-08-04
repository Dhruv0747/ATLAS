#!/usr/bin/env python3
"""
rover_foxglove.py v5.4 - ROS2 /cmd_vel + USB gamepad + dead-reckoning odometry
for ROVER 4WDXL60R by AMRobotics.

New in v5.4:
  - Dead-reckoning Ackermann odometry (from commanded speed + steering angle)
  - Publishes /odom (nav_msgs/Odometry) at 20 Hz
  - Broadcasts TF odom->base_footprint dynamically (replaces static odom_tf node)
  - Heartbeat timer: publishes idle state at 2 Hz for Foxglove plot continuity
  - New constants: WHEELBASE, WHEEL_RADIUS, MAX_LINEAR_SPEED, MAX_STEER_RAD

Inherited from v5.3:
  - MOTOR_MAX = 0.20 (~24 RPM of 60 max)
  - Car-like creep when steering with no linear input (STEER_CREEP)
  - Servo writes every cmd_vel (no delay)
  - Publishes /steering_angle + /motor_speed for Foxglove Plot
  - Rear board reversed (REAR_REVERSED = True)
  - USB gamepad (Xbox360-style) priority over /cmd_vel when connected
"""
import os, sys

if 'ROS_DISTRO' not in os.environ:
    script = os.path.abspath(sys.argv[0])
    args   = ' '.join(sys.argv[1:])
    cmd    = f'source /opt/ros/humble/setup.bash && exec python3 {script} {args}'
    os.execv('/bin/bash', ['/bin/bash', '-c', cmd])

import json, math, struct, threading, time, logging, fcntl

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s: [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)
log.info('rover_driver v5.4 - ROS2 env ready, starting...')

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped
from std_msgs.msg import Float32
from nav_msgs.msg import Odometry
import tf2_ros
import serial
import smbus2
import subprocess

# Hardware constants
FRONT_PORT    = '/dev/rover_front'
REAR_PORT     = '/dev/rover_rear'
REAR_REVERSED = True
BAUD          = 115200
I2C_BUS       = 1
PCA9685_ADDR  = 0x42
SERVO_CH      = 0
SERVO_CENTER  = 1500
SERVO_RANGE   = 400

# Speed / kinematics constants
MOTOR_MAX       = 0.45
TELEOP_LX_MAX    = 0.30
STEER_CREEP      = 0.08
WHEELBASE        = 0.30
WHEEL_RADIUS     = 0.0625
MAX_LINEAR_SPEED = 0.157
MAX_STEER_RAD    = 0.524

# Gamepad
JOYSTICK_DEV = '/dev/input/js0'
JS_AXIS_LY   = 1
JS_AXIS_LX = 0
JS_DEADZONE  = 0.08
JS_FMT       = 'IhBB'
JS_SIZE      = struct.calcsize(JS_FMT)
JS_TYPE_AXIS   = 0x02
JS_TYPE_BUTTON = 0x01
# Camera pan/tilt via D-pad disc (axis 6=L/R, axis 7=U/D)
CAM_PAN_AXIS    = 6
CAM_TILT_AXIS   = 7
CAM_PAN_CH      = 1     # PCA9685 CH1 -- pan servo
CAM_TILT_CH     = 2     # PCA9685 CH2 -- tilt servo
CAM_CENTER_US   = 1500
CAM_PAN_MIN_US  = 700
CAM_PAN_MAX_US  = 2300
CAM_TILT_MIN_US = 700
CAM_TILT_MAX_US = 2300
CAM_STEP_US     = 15    # us per 50ms odom tick while held
SPEED_STEP     = 0.10
JS_BTN_L1      = 4
JS_BTN_L2      = 6
AUTO_SWITCH_TIMEOUT = 15.0


class RoverDriver(Node):
    def __init__(self):
        super().__init__('rover_driver')
        self._lock   = threading.Lock()
        self._joy_ok = False
        try:
            self._front = serial.Serial(FRONT_PORT, BAUD, timeout=0.1)
            self._rear  = serial.Serial(REAR_PORT,  BAUD, timeout=0.1)
            self.get_logger().info(
                f'Motor serial open (USB0=front, USB1=rear rev={REAR_REVERSED})')
        except Exception as e:
            self.get_logger().error(f'Motor serial open failed: {e}')
            self._front = self._rear = None


        try:
            self._i2c = smbus2.SMBus(I2C_BUS)
            self._pca_init()
            self.get_logger().info('Steering servo (PCA9685 ch0) ready')
        except Exception as e:
            self.get_logger().error(f'PCA9685 init failed: {e}')
            self._i2c = None

        self._steer_pub = self.create_publisher(Float32,  '/steering_angle', 10)
        self._speed_pub = self.create_publisher(Float32,  '/motor_speed',    10)
        self._odom_pub  = self.create_publisher(Odometry, '/odom',           10)
        self._odom_x_pub = self.create_publisher(Float32, '/odom/x',         10)
        self._odom_y_pub = self.create_publisher(Float32, '/odom/y',         10)
        self._odom_yaw_pub = self.create_publisher(Float32, '/odom/yaw',     10)

        self._tf_broadcaster = tf2_ros.TransformBroadcaster(self)

        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)

        self._odom_x      = 0.0
        self._odom_y      = 0.0
        self._odom_theta  = 0.0
        self._odom_v      = 0.0
        self._odom_omega  = 0.0
        self._odom_last_t = self.get_clock().now()

        self.create_timer(0.05, self._odom_timer)
        self.create_timer(0.5,  self._heartbeat)
        self._last_cmd_time = time.time()
        self._speed_scale   = 1.0
        self._manual_mode       = False
        self._last_joy_time     = 0.0
        self._gamepad_ever_used = False
        self._joy_pan     = 0.0
        self._joy_tilt    = 0.0
        self._cam_pan_us  = CAM_CENTER_US
        self._cam_tilt_us = CAM_CENTER_US

        threading.Thread(target=self._joystick_loop, daemon=True).start()

        self.get_logger().info(
            f'rover_driver v5.4 ready - '
            f'MOTOR_MAX={MOTOR_MAX} (~{round(MOTOR_MAX * 120)} RPM) | '
            f'gamepad={JOYSTICK_DEV} | odom+TF active')

    def _pca_init(self):
        A = PCA9685_ADDR
        self._i2c.write_byte_data(A, 0x00, 0x10)
        time.sleep(0.005)
        pre = round(25000000 / (4096 * 50)) - 1
        self._i2c.write_byte_data(A, 0xFE, pre)
        self._i2c.write_byte_data(A, 0x00, 0x00)
        time.sleep(0.005)
        self._i2c.write_byte_data(A, 0x00, 0xA0)
        self._set_servo(SERVO_CENTER)

    def _reconnect_serial(self, port, attr):
        import os, time as _t
        self.get_logger().warn("[serial] " + port + " lost, reconnecting...")
        try: getattr(self, attr).close()
        except Exception: pass
        for _ in range(120):
            if os.path.exists(port):
                try:
                    s = serial.Serial(port, BAUD, timeout=0.1)
                    setattr(self, attr, s)
                    self.get_logger().warn("[serial] " + port + " reconnected!")
                    return
                except Exception as ex:
                    self.get_logger().warn("[serial] open fail: " + str(ex))
            _t.sleep(1.0)
        self.get_logger().error("[serial] " + port + " gave up after 2min")

    def _set_servo(self, pulse_us: int):
        pulse_us = max(1000, min(2000, pulse_us))
        ticks    = int(pulse_us * 4096 / 20000)
        try:
            self._i2c.write_i2c_block_data(
                PCA9685_ADDR, 0x06 + 4 * SERVO_CH,
                [0x00, 0x00, ticks & 0xFF, ticks >> 8])
        except Exception as e:
            self.get_logger().warn(f'Servo write error: {e}')

    def _set_cam_servo(self, ch: int, pulse_us: int):
        pulse_us = max(500, min(2500, pulse_us))
        ticks = int(pulse_us * 4096 / 20000)
        try:
            self._i2c.write_i2c_block_data(
                PCA9685_ADDR, 0x06 + 4 * ch,
                [0x00, 0x00, ticks & 0xFF, ticks >> 8])
        except Exception as e:
            self.get_logger().warn(f'Cam servo error: {e}')

    def _drive(self, lx: float, az: float, src: str = ''):
        if src != 'watchdog':
            self._last_cmd_time = time.time()
        spd = max(-MOTOR_MAX, min(MOTOR_MAX, lx * MOTOR_MAX / TELEOP_LX_MAX))

        if src == "pad" and abs(az) > 0.1 and abs(spd) < STEER_CREEP:
            spd = STEER_CREEP

        rear_spd  = -spd if REAR_REVERSED else spd
        angle_deg = max(-90.0, min(90.0, -az * 90.0))
        pulse_us  = SERVO_CENTER + int(angle_deg * SERVO_RANGE / 90)

        if src != 'watchdog':
            self.get_logger().info(
                f'[{src}] lx={lx:.2f} az={az:.2f} '
                f'spd={spd:.3f} steer={angle_deg:.1f}d {pulse_us}us',
                throttle_duration_sec=0.2)

        if self._front and self._rear:
            fc = (json.dumps({'T': 1, 'L': spd,     'R': spd})      + '\n').encode()
            rc = (json.dumps({'T': 1, 'L': rear_spd, 'R': rear_spd}) + '\n').encode()
            with self._lock:
                try:
                    self._front.write(fc)
                except Exception as e:
                    self.get_logger().warn(f'Motor write error: {e}')
                    self._reconnect_serial(FRONT_PORT, '_front')
                try:
                    self._rear.write(rc)
                except Exception as e:
                    self.get_logger().warn(f'Motor write error: {e}')
                    self._reconnect_serial(REAR_PORT, '_rear')

        if self._i2c:
            self._set_servo(pulse_us)

        self._steer_pub.publish(Float32(data=float(angle_deg)))
        self._speed_pub.publish(Float32(data=float(spd)))

        actual_v  = spd / MOTOR_MAX * MAX_LINEAR_SPEED
        steer_rad = math.radians(angle_deg)
        steer_rad = max(-MAX_STEER_RAD, min(MAX_STEER_RAD, steer_rad))

        if abs(steer_rad) < 0.005 or abs(actual_v) < 1e-4:
            actual_omega = 0.0
        else:
            R = WHEELBASE / math.tan(steer_rad)
            actual_omega = actual_v / R

        self._odom_v     = actual_v
        self._odom_omega = actual_omega

    def _on_cmd_vel(self, msg: Twist):
        self._last_cmd_time = time.time()
        self._drive(msg.linear.x, msg.angular.z, 'ros')

    def _odom_timer(self):
        now = self.get_clock().now()
        dt  = (now - self._odom_last_t).nanoseconds * 1e-9
        self._odom_last_t = now

        if dt <= 0 or dt > 1.0:
            return

        v     = self._odom_v
        omega = self._odom_omega
        theta = self._odom_theta

        dtheta = omega * dt
        dx     = v * math.cos(theta + dtheta * 0.5) * dt
        dy     = v * math.sin(theta + dtheta * 0.5) * dt

        self._odom_x     += dx
        self._odom_y     += dy
        self._odom_theta += dtheta
        self._odom_theta  = math.atan2(
            math.sin(self._odom_theta), math.cos(self._odom_theta))

        half_yaw = self._odom_theta * 0.5
        qz = math.sin(half_yaw)
        qw = math.cos(half_yaw)

        odom = Odometry()
        odom.header.stamp    = now.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id  = 'base_footprint'
        odom.pose.pose.position.x    = self._odom_x
        odom.pose.pose.position.y    = self._odom_y
        odom.pose.pose.position.z    = 0.0
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        odom.twist.twist.linear.x  = v
        odom.twist.twist.angular.z = omega
        odom.pose.covariance[0]  = 0.1
        odom.pose.covariance[7]  = 0.1
        odom.pose.covariance[35] = 0.2
        odom.twist.covariance[0]  = 0.05
        odom.twist.covariance[35] = 0.1
        self._odom_pub.publish(odom)
        self._odom_x_pub.publish(Float32(data=float(self._odom_x)))
        self._odom_y_pub.publish(Float32(data=float(self._odom_y)))
        self._odom_yaw_pub.publish(Float32(data=float(math.degrees(self._odom_theta))))

        t = TransformStamped()
        t.header.stamp    = now.to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id  = 'base_footprint'
        t.transform.translation.x = self._odom_x
        t.transform.translation.y = self._odom_y
        t.transform.translation.z = 0.0
        t.transform.rotation.x    = 0.0
        t.transform.rotation.y    = 0.0
        t.transform.rotation.z    = qz
        t.transform.rotation.w    = qw
        self._tf_broadcaster.sendTransform(t)
        if (self._joy_pan != 0.0 or self._joy_tilt != 0.0) and self._i2c:
            self._cam_pan_us  = max(CAM_PAN_MIN_US, min(CAM_PAN_MAX_US,
                                    self._cam_pan_us  + int(self._joy_pan  * CAM_STEP_US)))
            self._cam_tilt_us = max(CAM_TILT_MIN_US, min(CAM_TILT_MAX_US,
                                    self._cam_tilt_us + int(self._joy_tilt * CAM_STEP_US)))
            self._set_cam_servo(CAM_PAN_CH,  self._cam_pan_us)
            self._set_cam_servo(CAM_TILT_CH, self._cam_tilt_us)


    def _on_explore_cmd(self, msg):
        if msg.data:
            self.get_logger().info('explore_cmd: START autonomous')
            self._manual_mode = False
            self._start_explorer()
        else:
            self.get_logger().info('explore_cmd: STOP autonomous')
            self._manual_mode = True
            self._last_joy_time = 9e18
            self._stop_explorer()

    def _stop_explorer(self):
        r = subprocess.call(['pkill','-f','rover_explore_camera.py'],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if r == 0: self.get_logger().warn('AUTO: explorer stopped->MANUAL')

    def _start_explorer(self):
        self.get_logger().info('AUTO: explorer starting->AUTONOMOUS')
        subprocess.Popen(['python3','-u','/home/jetson/project_atlas/scripts/rover_explore_camera.py'],
            stdout=open('/tmp/explore_cam.log','a'),stderr=subprocess.STDOUT)

    def _heartbeat(self):
        if time.time() - self._last_cmd_time > 5.0:
            self._drive(0.0, 0.0, "watchdog")
            if self._i2c:
                self._set_servo(SERVO_CENTER)
            self.get_logger().warn("watchdog: no cmd_vel, stopping motors", throttle_duration_sec=10.0)
        if (self._gamepad_ever_used and self._manual_mode
                and time.time()-self._last_joy_time > AUTO_SWITCH_TIMEOUT):
            self._manual_mode = False
            self._start_explorer()
        if abs(self._odom_v) < 1e-4:
            self._steer_pub.publish(Float32(data=0.0))
            self._speed_pub.publish(Float32(data=0.0))

    def _joystick_loop(self):
        joy_lx = 0.0
        joy_az = 0.0
        joy_was_active = False
        while True:
            try:
                self.get_logger().info(f'Gamepad: waiting for {JOYSTICK_DEV}')
                with open(JOYSTICK_DEV, 'rb') as js:
                    self._joy_ok = True
                    self.get_logger().info(
                        'Gamepad connected! Left-stick Y=throttle X=steer')
                    while True:
                        data = js.read(JS_SIZE)
                        if len(data) < JS_SIZE:
                            break
                        _, value, js_type, number = struct.unpack(JS_FMT, data)
                        if js_type & JS_TYPE_BUTTON:
                            if value == 1:
                                self._last_joy_time = time.time()
                                self._gamepad_ever_used = True
                                if not self._manual_mode:
                                    self._manual_mode = True
                                    self._stop_explorer()
                                if number == JS_BTN_L1:
                                    self._speed_scale = min(1.0,round(self._speed_scale+SPEED_STEP,2))
                                    self.get_logger().info(f"Speed UP: {self._speed_scale:.0%}")
                                elif number == JS_BTN_L2:
                                    self._speed_scale = max(0.2,round(self._speed_scale-SPEED_STEP,2))
                                    self.get_logger().info(f"Speed DOWN: {self._speed_scale:.0%}")
                                else:
                                    self.get_logger().info(f"Btn {number} pressed (not mapped)")
                            continue
                        if not (js_type & JS_TYPE_AXIS):
                            continue
                        norm = value / 32767.0
                        if abs(norm) < JS_DEADZONE:
                            norm = 0.0
                        changed = False
                        if number == JS_AXIS_LY:
                            joy_lx  = -norm
                            changed = True
                        elif number == 3:
                            joy_az  = -norm
                            changed = True
                        if changed:
                            joy_active = abs(joy_lx) > JS_DEADZONE or abs(joy_az) > JS_DEADZONE
                            if joy_active:
                                self._last_joy_time = time.time()
                                self._gamepad_ever_used = True
                                if not self._manual_mode:
                                    self._manual_mode = True
                                    self._stop_explorer()

                            if joy_active or joy_was_active:
                                self._drive(joy_lx * TELEOP_LX_MAX, joy_az, 'pad')
                            joy_was_active = joy_active
                self._joy_ok = False
                self.get_logger().info(
                    'Gamepad disconnected - falling back to Foxglove Teleop')
            except FileNotFoundError:
                self._joy_ok = False
                time.sleep(2)
            except Exception as e:
                self.get_logger().warn(f'Gamepad error: {e}')
                self._joy_ok = False
                time.sleep(1)


_LOCK_FILE = None

def main():
    global _LOCK_FILE
    _LOCK_FILE = open('/tmp/rover_foxglove.lock', 'w')
    try:
        fcntl.lockf(_LOCK_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print('rover_foxglove already running; exiting duplicate')
        return
    rclpy.init()
    node = RoverDriver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()




