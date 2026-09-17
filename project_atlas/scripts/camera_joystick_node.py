#!/usr/bin/env python3
"""Xbox D-pad camera pan/tilt controller for Project ATLAS."""
import time
import math
from atlas_serial_lines import CameraReplyGuard

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Joy
from std_msgs.msg import Bool, Int32


def camera_input(axes, buttons):
    """D-pad only; B is exclusively the rover stop. Reject malformed input."""
    if len(axes) < 8 or len(buttons) < 4 or not all(math.isfinite(x) for x in axes):
        return 0, 0, False
    if buttons[1]:
        return 0, 0, False
    horizontal = axes[6] if abs(axes[6]) >= .5 else 0
    vertical = axes[7] if abs(axes[7]) >= .5 else 0
    return horizontal, vertical, bool(buttons[3])


def camera_step(pan, tilt, horizontal, vertical, pan_step, tilt_step):
    # D-pad positive is left/up. Match the installed dashboard servo directions.
    return (max(700, min(2300, pan-int(horizontal*pan_step))),
            max(700, min(2300, tilt+int(vertical*tilt_step))))


def bounded_step(now, previous, rate):
    """Never catch up missed packets with a large physical jump."""
    dt = .04 if previous == 0.0 else max(0., min(.06, now-previous))
    return max(1, int(rate*dt))


class CameraJoystick(Node):
    def __init__(self):
        super().__init__("camera_joystick")
        self.pan = 2300
        self.tilt = 1500
        self.minimum = 700
        self.maximum = 2300
        self.step = 50
        self.tilt_step = 50
        self.declare_parameter('command_interval_s', 0.04)
        self.command_interval = max(.04, float(self.get_parameter('command_interval_s').value))
        self.declare_parameter('servo_rate_us_s', 400.0)
        self.servo_rate = max(100., min(600., float(self.get_parameter('servo_rate_us_s').value)))
        self.last_step = 0.0
        self.last_center = False
        self.have_pan = False
        self.have_tilt = False
        self.pan_reply = CameraReplyGuard()
        self.tilt_reply = CameraReplyGuard()
        self.last_manual = -10.0
        self.pan_pub = self.create_publisher(Int32, "/camera/bottom_servo_cmd_us", 1)
        self.tilt_pub = self.create_publisher(Int32, "/camera/second_servo_cmd_us", 1)
        self.create_subscription(Int32, "/camera/bottom_servo_us", self.pan_feedback, 10)
        self.create_subscription(Int32, "/camera/second_servo_us", self.tilt_feedback, 10)
        self.tracking_pub = self.create_publisher(Bool, '/atlas/camera_tracking/enabled', 10)
        self.create_subscription(Joy, "/joy", self.joy_callback,
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        self.get_logger().info(
            "Camera remote ready: D-pad pan/tilt, Y home; B reserved for stop"
        )

    def pan_feedback(self, message):
        if self.minimum <= message.data <= self.maximum:
            self.have_pan = True
            if self.pan_reply.accept(message.data) and time.monotonic()-self.last_manual > .4:
                self.pan = message.data

    def tilt_feedback(self, message):
        if self.minimum <= message.data <= self.maximum:
            self.have_tilt = True
            if self.tilt_reply.accept(message.data) and time.monotonic()-self.last_manual > .4:
                self.tilt = message.data

    def publish(self, pan_changed=True, tilt_changed=True):
        # A deliberate manual camera action pauses tracking so it cannot undo it.
        self.tracking_pub.publish(Bool(data=False))
        self.last_manual = time.monotonic()
        if pan_changed:
            self.pan_reply.sent(int(self.pan))
            self.pan_pub.publish(Int32(data=int(self.pan)))
        if tilt_changed:
            self.tilt_reply.sent(int(self.tilt))
            self.tilt_pub.publish(Int32(data=int(self.tilt)))

    def joy_callback(self, message):
        horizontal, vertical, centre_pressed = camera_input(message.axes, message.buttons)
        stamp = message.header.stamp.sec + message.header.stamp.nanosec/1e9
        age = self.get_clock().now().nanoseconds/1e9 - stamp
        if age < -.1 or age > .5:
            return
        if centre_pressed and not self.last_center:
            self.pan = 2300
            self.tilt = 1500
            self.publish()
        self.last_center = centre_pressed
        if centre_pressed:
            self.last_manual = time.monotonic()
            return
        if not (self.have_pan and self.have_tilt):
            return

        now = time.monotonic()
        if abs(horizontal) < 0.5 and abs(vertical) < 0.5:
            self.last_step = 0.0  # next deliberate press responds immediately
            return
        # Keep ownership through the entire hold, INCLUDING at a limit where
        # no command is published. Otherwise old hub reports restart motion.
        self.last_manual = now
        if now-self.last_step < self.command_interval:
            return
        old_pan, old_tilt = self.pan, self.tilt
        increment = bounded_step(now, self.last_step, self.servo_rate)
        self.pan, self.tilt = camera_step(self.pan, self.tilt, horizontal, vertical,
                                         increment, increment)
        if self.pan != old_pan or self.tilt != old_tilt:
            self.publish(self.pan != old_pan, self.tilt != old_tilt)
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
