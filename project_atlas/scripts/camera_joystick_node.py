#!/usr/bin/env python3
"""Xbox D-pad camera pan/tilt controller for Project ATLAS."""
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import Int32


class CameraJoystick(Node):
    def __init__(self):
        super().__init__("camera_joystick")
        self.pan = 2300
        self.tilt = 1500
        self.minimum = 700
        self.maximum = 2300
        self.step = 20
        self.tilt_step = 50
        self.last_step = 0.0
        self.last_center = False
        self.pan_pub = self.create_publisher(Int32, "/camera/bottom_servo_cmd_us", 10)
        self.tilt_pub = self.create_publisher(Int32, "/camera/second_servo_cmd_us", 10)
        self.create_subscription(Int32, "/camera/bottom_servo_us", self.pan_feedback, 10)
        self.create_subscription(Int32, "/camera/second_servo_us", self.tilt_feedback, 10)
        self.create_subscription(Joy, "/joy", self.joy_callback, 10)
        self.get_logger().info(
            "Camera remote ready: D-pad pan/tilt, A down, B up, Y centres"
        )

    def pan_feedback(self, message):
        if self.minimum <= message.data <= self.maximum:
            self.pan = message.data

    def tilt_feedback(self, message):
        if self.minimum <= message.data <= self.maximum:
            self.tilt = message.data

    def publish(self):
        self.pan_pub.publish(Int32(data=int(self.pan)))
        self.tilt_pub.publish(Int32(data=int(self.tilt)))

    def joy_callback(self, message):
        axes = list(message.axes)
        buttons = list(message.buttons)
        centre_pressed = len(buttons) > 3 and buttons[3] == 1
        if centre_pressed and not self.last_center:
            self.pan = 2300
            self.tilt = 1500
            self.publish()
        self.last_center = centre_pressed

        now = time.monotonic()
        if now-self.last_step < 0.12:
            return
        horizontal = axes[6] if len(axes) > 6 else 0.0
        vertical = axes[7] if len(axes) > 7 else 0.0
        camera_down = len(buttons) > 0 and buttons[0] == 1
        camera_up = len(buttons) > 1 and buttons[1] == 1
        button_vertical = float(camera_down) - float(camera_up)
        if abs(vertical) < 0.5:
            vertical = button_vertical
        if abs(horizontal) < 0.5 and abs(vertical) < 0.5:
            return
        self.pan = max(self.minimum, min(self.maximum, self.pan+int(horizontal*self.step)))
        self.tilt = max(
            self.minimum,
            min(self.maximum, self.tilt-int(vertical*self.tilt_step)),
        )
        self.publish()
        self.last_step = now


def main():
    rclpy.init()
    node = CameraJoystick()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
