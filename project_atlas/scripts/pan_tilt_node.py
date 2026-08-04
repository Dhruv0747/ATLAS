#!/usr/bin/env python3
"""
pan_tilt_node.py - ROS2 pan/tilt servo controller for SG90 on PCA9685
ch4 = PAN  (bottom servo, left/right, 0-180deg)
ch5 = TILT (top servo, up/down, 30-150deg)

Foxglove Publish panel topics:
  /pan_tilt/pan   std_msgs/Float32  pan angle degrees (0-180)
  /pan_tilt/tilt  std_msgs/Float32  tilt angle degrees (0-180)

Run: nohup python3 /home/jetson/project_atlas/scripts/pan_tilt_node.py > /tmp/pan_tilt.log 2>&1 &
"""
import os, sys, time

if 'ROS_DISTRO' not in os.environ:
    os.execvpe('bash', ['bash', '-c',
        'source /opt/ros/humble/setup.bash && exec python3 ' + ' '.join(sys.argv)],
        os.environ)

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import smbus2

PAN_CH   = 1
TILT_CH  = 2
PAN_MIN  = 0
PAN_MAX  = 180
TILT_MIN = 30
TILT_MAX = 150
PCA_ADDR = 0x42

_bus = smbus2.SMBus(1)

def _pca_init():
    _bus.write_byte_data(PCA_ADDR, 0x00, 0x10)
    prescale = round(25_000_000 / (4096 * 50)) - 1
    _bus.write_byte_data(PCA_ADDR, 0xFE, prescale)
    _bus.write_byte_data(PCA_ADDR, 0x00, 0x00)
    time.sleep(0.005)
    _bus.write_byte_data(PCA_ADDR, 0x00, 0xA0)

def _set_pwm(ch, ticks):
    base = 0x06 + 4 * ch
    _bus.write_i2c_block_data(PCA_ADDR, base, [0, 0, ticks & 0xFF, ticks >> 8])

def _angle_to_ticks(angle_deg):
    pulse_us = 500 + (float(angle_deg) / 180.0) * 1900
    return int(pulse_us / 20000.0 * 4096)

def set_angle(ch, angle_deg):
    _set_pwm(ch, _angle_to_ticks(angle_deg))

class PanTiltNode(Node):
    def __init__(self):
        super().__init__('pan_tilt_node')
        _pca_init()
        self._pan  = 90.0
        self._tilt = 90.0
        set_angle(PAN_CH,  90)
        set_angle(TILT_CH, 90)
        self.get_logger().info('Pan/Tilt node ready -- ch1=PAN, ch2=TILT, centered at 90deg')
        self.create_subscription(Float32, '/pan_tilt/pan',  self._cb_pan,  10)
        self.create_subscription(Float32, '/pan_tilt/tilt', self._cb_tilt, 10)

    def _cb_pan(self, msg):
        self._pan = max(PAN_MIN, min(PAN_MAX, msg.data))
        set_angle(PAN_CH, self._pan)
        self.get_logger().info(f'Pan  -> {self._pan:.1f}deg')

    def _cb_tilt(self, msg):
        self._tilt = max(TILT_MIN, min(TILT_MAX, msg.data))
        set_angle(TILT_CH, self._tilt)
        self.get_logger().info(f'Tilt -> {self._tilt:.1f}deg')

def main():
    rclpy.init()
    node = PanTiltNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        set_angle(PAN_CH,  90)
        set_angle(TILT_CH, 90)
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
