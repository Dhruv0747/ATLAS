#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from gpiozero import Motor, PWMOutputDevice

class MotorController(Node):
    def __init__(self):
        super().__init__('motor_controller')
        # Left motor: forward=16, backward=20
        self.left_motor = Motor(forward=16, backward=20, enable=None)
        # Right motor: forward=6, backward=5
        self.right_motor = Motor(forward=6, backward=5, enable=None)
        # Enable pin (PWM) on GPIO13
        self.enable = PWMOutputDevice(13, frequency=1000)
        self.enable.value = 0  # start stopped

        self.subscription = self.create_subscription(
            Twist, '/cmd_vel', self.cmd_vel_callback, 10)
        self.get_logger().info('Motor node ready (gpiozero)')

    def cmd_vel_callback(self, msg):
        linear = msg.linear.x
        angular = msg.angular.z
        left = linear - angular
        right = linear + angular

        # Clamp to [-1, 1]
        left = max(-1.0, min(1.0, left))
        right = max(-1.0, min(1.0, right))

        # Set motor speeds (positive = forward, negative = backward)
        self.left_motor.value = left
        self.right_motor.value = right

        # Enable PWM based on max absolute speed
        self.enable.value = max(abs(left), abs(right))

    def __del__(self):
        self.left_motor.value = 0
        self.right_motor.value = 0
        self.enable.value = 0
        self.left_motor.close()
        self.right_motor.close()
        self.enable.close()

def main(args=None):
    rclpy.init(args=args)
    node = MotorController()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
