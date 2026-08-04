#!/usr/bin/env python3
"""
motor_diff_node.py  --  Differential drive via PCA9685 continuous-rotation servos
  Subscribes /cmd_vel (geometry_msgs/Twist)
  Maps linear.x + angular.z -> left/right throttle on PCA9685.

  CH_LEFT / CH_RIGHT: PCA9685 channels for your left and right motors.
  If one motor spins backwards, flip its LEFT_SIGN or RIGHT_SIGN.
  pip3 install adafruit-circuitpython-servokit --break-system-packages
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32
from adafruit_servokit import ServoKit

CH_LEFT   = 4
CH_RIGHT  = 5
MAX_LINEAR  = 0.5
MAX_ANGULAR = 1.5
LEFT_SIGN  =  1.0
RIGHT_SIGN = -1.0


def clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


class MotorDiffNode(Node):
    def __init__(self):
        super().__init__('motor_diff_node')
        self._kit = ServoKit(channels=16, address=0x42)
        self._kit.continuous_servo[CH_LEFT].throttle  = 0.0
        self._kit.continuous_servo[CH_RIGHT].throttle = 0.0
        self.create_subscription(Twist, '/cmd_vel', self._cb_cmd, 10)
        self._pub_l = self.create_publisher(Float32, '/motors/left',  10)
        self._pub_r = self.create_publisher(Float32, '/motors/right', 10)
        self._last_cmd = self.get_clock().now()
        self.create_timer(0.1, self._watchdog)
        self.get_logger().info(f'Motor diff node ready  L=CH{CH_LEFT}  R=CH{CH_RIGHT}')

    def _cb_cmd(self, msg: Twist):
        self._last_cmd = self.get_clock().now()
        lin = msg.linear.x  / MAX_LINEAR
        ang = msg.angular.z / MAX_ANGULAR
        left  = clamp((lin + ang) * LEFT_SIGN)
        right = clamp((lin - ang) * RIGHT_SIGN)
        self._kit.continuous_servo[CH_LEFT].throttle  = left
        self._kit.continuous_servo[CH_RIGHT].throttle = right
        self._pub_l.publish(Float32(data=float(left)))
        self._pub_r.publish(Float32(data=float(right)))

    def _watchdog(self):
        dt = (self.get_clock().now() - self._last_cmd).nanoseconds * 1e-9
        if dt > 0.5:
            self._kit.continuous_servo[CH_LEFT].throttle  = 0.0
            self._kit.continuous_servo[CH_RIGHT].throttle = 0.0
            self._pub_l.publish(Float32(data=0.0))
            self._pub_r.publish(Float32(data=0.0))


def main():
    rclpy.init()
    node = MotorDiffNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node._kit.continuous_servo[CH_LEFT].throttle  = 0.0
    node._kit.continuous_servo[CH_RIGHT].throttle = 0.0
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
