import math
#!/usr/bin/env python3
"""
bno08x_node.py  ??? ROS2 Jazzy node for BNO08x IMU at I2C 0x4B
Replaces the old BNO055 node.

Fix for Pi 5: adafruit_bno08x raises RuntimeError('Unprocessable Batch bytes')
during enable_feature() ??? the command is actually sent successfully, the library
just can't parse the SHTP response. We catch it, retry, and the sensor works fine.

Published topics:
  /imu/data         sensor_msgs/Imu
  /imu/mag          sensor_msgs/MagneticField
  /imu/euler        geometry_msgs/Vector3  -- roll/pitch/yaw in degrees

Run: nohup python3 /home/jetson/project_atlas/scripts/bno08x_node.py > /tmp/bno08x.log 2>&1 &
"""
import os, sys, time, math, json

if 'ROS_DISTRO' not in os.environ:
    os.execvpe('bash', ['bash', '-c',
        'source /opt/ros/humble/setup.bash && exec python3 ' + ' '.join(sys.argv)],
        os.environ)

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu, MagneticField
from geometry_msgs.msg import Vector3
from std_msgs.msg import Float32, String

import board
import busio
from adafruit_bno08x import (
    BNO_REPORT_ACCELEROMETER,
    BNO_REPORT_GYROSCOPE,
    BNO_REPORT_MAGNETOMETER,
    BNO_REPORT_ROTATION_VECTOR,
)
from adafruit_bno08x.i2c import BNO08X_I2C

BNO_ADDR = 0x4B

def init_bno(i2c, retries=5):
    """
    Initialize BNO08x and enable features.
    On Pi 5, adafruit_bno08x raises 'Unprocessable Batch bytes' during
    enable_feature() -- library SHTP parsing bug, not a sensor failure.
    The command IS sent. We catch it, retry, and the sensor works fine.
    """
    for _attempt in range(10):
        try:
            bno = BNO08X_I2C(i2c, address=BNO_ADDR)
            break
        except (ValueError, OSError) as _e:
            import time as _t
            print(f'BNO08x I2C not ready ({_e}), retrying {_attempt+1}/10...', flush=True)
            _t.sleep(3)
    else:
        raise RuntimeError('BNO08x not found after 10 attempts')
    time.sleep(2.0)
    features = [
        BNO_REPORT_ROTATION_VECTOR,
        BNO_REPORT_ACCELEROMETER,
        BNO_REPORT_GYROSCOPE,
        BNO_REPORT_MAGNETOMETER,
    ]
    for feat in features:
        enabled = False
        for attempt in range(retries):
            try:
                bno.enable_feature(feat)
                time.sleep(0.3)
                enabled = True
                print(f'BNO08x feature {feat} enabled (attempt {attempt+1})', flush=True)
                break
            except RuntimeError as e:
                if 'Unprocessable' in str(e):
                    print(f'BNO08x feature {feat} attempt {attempt+1}/{retries}: batch error (retrying)', flush=True)
                    time.sleep(0.5)
                else:
                    raise
        if not enabled:
            print(f'BNO08x WARNING: feature {feat} could not be enabled after {retries} attempts -- continuing', flush=True)
    return bno


def quat_to_euler(x, y, z, w):
    sinr = 2.0 * (w * x + y * z)
    cosr = 1.0 - 2.0 * (x * x + y * y)
    roll = math.degrees(math.atan2(sinr, cosr))
    sinp = 2.0 * (w * y - z * x)
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, sinp))))
    siny = 2.0 * (w * z + x * y)
    cosy = 1.0 - 2.0 * (y * y + z * z)
    yaw  = math.degrees(math.atan2(siny, cosy))
    return roll, pitch, yaw


class BNO08xNode(Node):
    def __init__(self):
        super().__init__('bno08x_node')
        i2c = busio.I2C(board.SCL, board.SDA)
        self.get_logger().info('Initializing BNO08x -- this may take a few seconds...')
        self._bno = init_bno(i2c)
        self.get_logger().info(f'BNO08x node ready at I2C 0x{BNO_ADDR:02X}')

        self._pub_imu   = self.create_publisher(Imu,           '/imu/data',  10)
        self._pub_mag   = self.create_publisher(MagneticField, '/imu/mag',   10)
        self._pub_euler = self.create_publisher(Vector3,       '/imu/euler', 10)
        self._pub_roll    = self.create_publisher(Float32, '/imu/roll',    10)
        self._pub_pitch   = self.create_publisher(Float32, '/imu/pitch',   10)
        self._pub_heading = self.create_publisher(Float32, '/imu/heading', 10)
        # One compact 10 Hz dashboard stream avoids making every UI subscribe
        # to six 20 Hz navigation topics.  Nav/EKF keep the original full-rate
        # Imu and MagneticField topics.
        self._pub_dashboard = self.create_publisher(String, '/imu/dashboard_json', 10)
        self._dashboard_divider = 0

        self.create_timer(0.05, self._cb)

    def _cb(self):
        now = self.get_clock().now().to_msg()

        imu = Imu()
        imu.header.stamp    = now
        # The BNO08X is rigidly mounted to ATLAS.  Publish the navigation IMU
        # in base_link so robot_localization does not depend on a missing
        # imu_link TF.  ATLAS is a planar rover: raw roll/pitch are retained on
        # the dashboard topics, while /imu/data carries yaw-only orientation.
        imu.header.frame_id = 'base_link'

        try:
            qx, qy, qz, qw = self._bno.quaternion or (0, 0, 0, 1)
        except Exception:
            qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0
        roll, pitch, yaw = quat_to_euler(qx, qy, qz, qw)
        # BNO compass heading increases clockwise; ROS REP-103 yaw increases
        # counter-clockwise.  Convert the sign before constructing quaternion.
        ros_yaw = math.radians(-yaw)
        imu.orientation.x = 0.0
        imu.orientation.y = 0.0
        imu.orientation.z = math.sin(ros_yaw / 2.0)
        imu.orientation.w = math.cos(ros_yaw / 2.0)
        _oc=[0.002,0.0,0.0,0.0,0.002,0.0,0.0,0.0,0.002]
        _gc=[0.001,0.0,0.0,0.0,0.001,0.0,0.0,0.0,0.001]
        _ac=[0.05,0.0,0.0,0.0,0.05,0.0,0.0,0.0,0.05]
        imu.orientation_covariance=_oc
        imu.angular_velocity_covariance=_gc
        imu.linear_acceleration_covariance=_ac

        try:
            gx, gy, gz = self._bno.gyro or (0, 0, 0)
        except Exception:
            gx, gy, gz = 0.0, 0.0, 0.0
        imu.angular_velocity.x = 0.0
        imu.angular_velocity.y = 0.0
        imu.angular_velocity.z = float(-gz)

        try:
            ax, ay, az = self._bno.acceleration or (0, 0, 0)
        except Exception:
            ax, ay, az = 0.0, 0.0, 0.0
        imu.linear_acceleration.x = float(ax)
        imu.linear_acceleration.y = float(ay)
        imu.linear_acceleration.z = float(az)

        self._pub_imu.publish(imu)

        try:
            mx, my, mz = self._bno.magnetic or (0, 0, 0)
        except Exception:
            mx, my, mz = 0.0, 0.0, 0.0
        mag = MagneticField()
        mag.header.stamp    = now
        mag.header.frame_id = 'base_link'
        mag.magnetic_field.x = float(mx) * 1e-6
        mag.magnetic_field.y = float(my) * 1e-6
        mag.magnetic_field.z = float(mz) * 1e-6
        self._pub_mag.publish(mag)

        self._pub_euler.publish(Vector3(x=roll, y=pitch, z=yaw))
        self._pub_roll.publish(Float32(data=float(roll)))
        self._pub_pitch.publish(Float32(data=float(pitch)))
        self._pub_heading.publish(Float32(data=float((yaw + 360.0) % 360.0)))
        self._dashboard_divider = (self._dashboard_divider + 1) % 2
        if self._dashboard_divider == 0:
            self._pub_dashboard.publish(String(data=json.dumps({
                'roll': round(float(roll), 3),
                'pitch': round(float(pitch), 3),
                'yaw': round(float(yaw), 3),
                'heading': round(float((yaw + 360.0) % 360.0), 3),
                'qx': round(float(qx), 6), 'qy': round(float(qy), 6),
                'qz': round(float(qz), 6), 'qw': round(float(qw), 6),
                'gx': round(float(gx), 6), 'gy': round(float(gy), 6),
                'gz': round(float(gz), 6),
                'ax': round(float(ax), 6), 'ay': round(float(ay), 6),
                'az': round(float(az), 6),
                'mx_ut': round(float(mx), 3), 'my_ut': round(float(my), 3),
                'mz_ut': round(float(mz), 3),
                'frame': 'base_link',
            }, separators=(',', ':'))))


def main():
    rclpy.init()
    node = BNO08xNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

