#!/usr/bin/env python3
"""
BNO055 IMU Node for ROS 2 Jazzy (TortoiseBot)
Replaces the old MPU6050 imu_node.py

Publishes:
  /imu        (sensor_msgs/Imu)              - quaternion + angular velocity + linear accel
  /imu/euler  (geometry_msgs/Vector3Stamped) - heading, roll, pitch in degrees (for Foxglove)

I2C bus 1, address 0x28 (BNO055 default, ADR pin low)
20 Hz publish rate, NDOF 9-DOF fusion mode
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from geometry_msgs.msg import Vector3Stamped
import smbus
import struct
import time
import math

BNO055_ADDRESS = 0x28
BNO055_I2C_BUS = 1
TCA9548A_ADDR = 0x70   # I2C mux
TCA9548A_CH0  = 0x01   # channel 0 = BNO055


REG_CHIP_ID       = 0x00
REG_OPR_MODE      = 0x3D
REG_CALIB_STAT    = 0x35

REG_EULER_H_LSB   = 0x1A
REG_QUA_W_LSB     = 0x20
REG_LIA_X_LSB     = 0x28
REG_GYR_X_LSB     = 0x14

MODE_CONFIG = 0x00
MODE_NDOF   = 0x0C

BNO055_CHIP_ID_VAL = 0xA0


class BNO055:
    """Minimal smbus driver for BNO055 in NDOF fusion mode."""

    def __init__(self, bus=BNO055_I2C_BUS, address=BNO055_ADDRESS):
        self.bus     = smbus.SMBus(bus)
        self.address = address
        self._mux_select()   # open mux ch0 before any I2C traffic
        self._setup()

    def _mux_select(self):
        """Select TCA9548A channel 0 (BNO055 channel)."""
        try:
            self.bus.write_byte(TCA9548A_ADDR, TCA9548A_CH0)
        except Exception as e:
            pass  # mux may not be available

    def _setup(self):
        chip = self.bus.read_byte_data(self.address, REG_CHIP_ID)
        if chip != BNO055_CHIP_ID_VAL:
            raise RuntimeError(
                'BNO055 chip ID mismatch: expected 0xA0, got 0x{:02X}. '
                'Check wiring and I2C address.'.format(chip)
            )
        self.bus.write_byte_data(self.address, REG_OPR_MODE, MODE_CONFIG)
        time.sleep(0.025)
        self.bus.write_byte_data(self.address, REG_OPR_MODE, MODE_NDOF)
        time.sleep(0.8)

    def _read_vector(self, reg, count):
        """Read `count` signed 16-bit little-endian values starting at `reg`."""
        self._mux_select()  # ensure mux on ch0 before every read
        raw = self.bus.read_i2c_block_data(self.address, reg, count * 2)
        return struct.unpack('<' + 'h' * count, bytes(raw))

    def quaternion(self):
        """(w, x, y, z) unit quaternion."""
        w, x, y, z = self._read_vector(REG_QUA_W_LSB, 4)
        s = 1.0 / (1 << 14)
        return w * s, x * s, y * s, z * s

    def euler_deg(self):
        """(heading, roll, pitch) in degrees."""
        h, r, p = self._read_vector(REG_EULER_H_LSB, 3)
        s = 1.0 / 16.0
        return h * s, r * s, p * s

    def linear_acceleration(self):
        """(x, y, z) in m/s2 - gravity-compensated."""
        x, y, z = self._read_vector(REG_LIA_X_LSB, 3)
        s = 1.0 / 100.0
        return x * s, y * s, z * s

    def gyro_rad(self):
        """(x, y, z) in rad/s."""
        x, y, z = self._read_vector(REG_GYR_X_LSB, 3)
        s = math.radians(1.0 / 16.0)
        return x * s, y * s, z * s

    def calibration_status(self):
        """(sys, gyro, accel, mag) each 0-3; 3 = fully calibrated."""
        c = self.bus.read_byte_data(self.address, REG_CALIB_STAT)
        return (c >> 6) & 3, (c >> 4) & 3, (c >> 2) & 3, c & 3


class IMUNode(Node):
    def __init__(self):
        super().__init__('imu_node')

        self.pub_imu   = self.create_publisher(Imu,            '/imu',       10)
        self.pub_euler = self.create_publisher(Vector3Stamped, '/imu/euler', 10)

        self.bno = BNO055(bus=BNO055_I2C_BUS, address=BNO055_ADDRESS)
        self.get_logger().info(
            'BNO055 IMU node started  address=0x{:02X}  bus={}  rate=20Hz  mode=NDOF'.format(
                BNO055_ADDRESS, BNO055_I2C_BUS)
        )

        self._low_calib_warned = False
        self.timer = self.create_timer(0.05, self._cb)   # 20 Hz

    def _cb(self):
        try:
            qw, qx, qy, qz              = self.bno.quaternion()
            ax, ay, az                  = self.bno.linear_acceleration()
            gx, gy, gz                  = self.bno.gyro_rad()
            heading, roll, pitch        = self.bno.euler_deg()
            # Compute quaternion from euler (BNO055 quat regs = identity at sys_calib=0)
            _h = math.radians(heading); _r = math.radians(roll); _p = math.radians(pitch)
            _cy, _sy = math.cos(_h/2), math.sin(_h/2)
            _cr, _sr = math.cos(_r/2), math.sin(_r/2)
            _cp, _sp = math.cos(_p/2), math.sin(_p/2)
            qw = _cr*_cp*_cy + _sr*_sp*_sy
            qx = _sr*_cp*_cy - _cr*_sp*_sy
            qy = _cr*_sp*_cy + _sr*_cp*_sy
            qz = _cr*_cp*_sy - _sr*_sp*_cy
            sys_c, gyr_c, acc_c, mag_c  = self.bno.calibration_status()

            if sys_c < 2:
                if not self._low_calib_warned:
                    self.get_logger().warn(
                        'BNO055 calibration low: sys={} groo={} accel={} mag={} '
                        '(move robot in figure-8 to calibrate magnetometer) '.format(
                            sys_c, gyr_c, acc_c, mag_c)
                    )
                    self._low_calib_warned = True
            else:
                self._low_calib_warned = False

            now = self.get_clock().now().to_msg()

            imu = Imu()
            imu.header.stamp    = now
            imu.header.frame_id = 'imu_link'
            imu.orientation.w = qw
            imu.orientation.x = qx
            imu.orientation.y = qy
            imu.orientation.z = qz
            imu.angular_velocity.x = gx
            imu.angular_velocity.y = gy
            imu.angular_velocity.z = gz
            imu.linear_acceleration.x = ax
            imu.linear_acceleration.y = ay
            imu.linear_acceleration.z = az
            imu.orientation_covariance[0]         = -1.0
            imu.angular_velocity_covariance[0]    = -1.0
            imu.linear_acceleration_covariance[0] = -1.0
            self.pub_imu.publish(imu)

            ev = Vector3Stamped()
            ev.header.stamp    = now
            ev.header.frame_id = 'imu_link'
            ev.vector.x = heading
            ev.vector.y = roll
            ev.vector.z = pitch
            self.pub_euler.publish(ev)

        except Exception as exc:
            self.get_logger().error('BNO055 read error: {}'.format(exc))


def main(args=None):
    rclpy.init(args=args)
    node = IMUNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
