#!/usr/bin/env python3
"""
camera_gimbal_node.py  --  Camera pan/tilt via PCA9685
  Subscribes /camera/pan  /camera/tilt  (Float32, degrees -90..+90)

  Change CH_PAN / CH_TILT to match your wiring.
  pip3 install adafruit-circuitpython-servokit --break-system-packages
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from adafruit_servokit import ServoKit

CH_PAN   = 2
CH_TILT  = 3
PAN_MIN  = -90.0
PAN_MAX  =  90.0
TILT_MIN = -45.0
TILT_MAX =  45.0
CENTER   = 90.0


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


class CameraGimbalNode(Node):
    def __init__(self):
        super().__init__('camera_gimbal_node')
        self._kit = ServoKit(channels=16)
        self._kit.servo[CH_PAN].angle  = CENTER
        self._kit.servo[CH_TILT].angle = CENTER
        self.create_subscription(Float32, '/camera/pan',  self._cb_pan,  10)
        self.create_subscription(Float32, '/camera/tilt', self._cb_tilt, 10)
        self.get_logger().info(f'Camera gimbal ready  PAN=CH{CH_PAN}  TILT=CH{CH_TILT}')

    def _deg_to_servo(self, deg, lo, hi):
        deg = clamp(deg, lo, hi)
        return (deg - lo) / (hi - lo) * 180.0

    def _cb_pan(self, msg):
        self._kit.servo[CH_PAN].angle = self._deg_to_servo(msg.data, PAN_MIN, PAN_MAX)

    def _cb_tilt(self, msg):
        self._kit.servo[CH_TILT].angle = self._deg_to_servo(msg.data, TILT_MIN, TILT_MAX)


def main():
    rclpy.init()
    node = CameraGimbalNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
