#!/usr/bin/env python3
"""Safe Arducam B0283 I2C pan/tilt driver for Project ATLAS.

The driver is inert until the commissioning marker exists. This protects the
existing camera servos while the new platform is being mounted.
"""
import os
import threading

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import Int32, String

try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None


MARKER = "/home/jetson/project_atlas/config/arducam_ptz_enabled"
I2C_BUS = 7                 # Jetson 40-pin header: physical pins 3 / 5
PCA9685_ADDRESS = 0x40      # Arducam B0283 default PWM controller address
PAN_CHANNEL = 0
TILT_CHANNEL = 1
# B0283 uses 180-degree digital servos. Keep a margin before the absolute
# 500/2500 us electrical endpoints to protect its mechanical brackets.
MIN_PULSE_US = 700
MAX_PULSE_US = 2300
MODE1, PRESCALE, LED0_ON_L = 0x00, 0xFE, 0x06


class ArducamPTZ(Node):
    def __init__(self):
        super().__init__("atlas_arducam_ptz")
        self.lock = threading.Lock()
        self.bus = None
        self.active = False
        self.pan = 1300
        self.tilt = 2100
        self.status_pub = self.create_publisher(String, "/camera/arducam/status", 10)
        self.pan_pub = self.create_publisher(Int32, "/camera/bottom_servo_us", 10)
        self.tilt_pub = self.create_publisher(Int32, "/camera/second_servo_us", 10)
        self.create_subscription(Int32, "/camera/bottom_servo_cmd_us", self.pan_cb, 10)
        self.create_subscription(Int32, "/camera/second_servo_cmd_us", self.tilt_cb, 10)
        self.create_timer(3.0, self.ensure_ready)
        self.ensure_ready()

    def status(self, text):
        self.status_pub.publish(String(data=text))
        self.get_logger().info(text)

    def ensure_ready(self):
        if self.active:
            # Periodic authoritative feedback lets newly started dashboards,
            # voice control and the Xbox node synchronize before commanding.
            self.pan_pub.publish(Int32(data=self.pan))
            self.tilt_pub.publish(Int32(data=self.tilt))
            return
        if not os.path.exists(MARKER):
            self.status("STANDBY: Arducam not commissioned; legacy camera remains active")
            return
        if SMBus is None:
            self.status("ERROR: python smbus2 is missing")
            return
        try:
            self.bus = SMBus(I2C_BUS)
            # A harmless register read verifies this exact controller address.
            self.bus.read_byte_data(PCA9685_ADDRESS, MODE1)
            self.bus.write_byte_data(PCA9685_ADDRESS, MODE1, 0x10)
            self.bus.write_byte_data(PCA9685_ADDRESS, PRESCALE, 121)  # 50 Hz
            self.bus.write_byte_data(PCA9685_ADDRESS, MODE1, 0x20)
            self.active = True
            self.set_pulse(PAN_CHANNEL, self.pan)
            self.set_pulse(TILT_CHANNEL, self.tilt)
            self.pan_pub.publish(Int32(data=self.pan))
            self.tilt_pub.publish(Int32(data=self.tilt))
            self.status("ONLINE: Arducam B0283 I2C pan/tilt active")
        except Exception as exc:
            self.bus = None
            self.status(f"WAITING: Arducam not found on i2c-{I2C_BUS} at 0x40 ({exc})")

    def set_pulse(self, channel, pulse_us):
        pulse_us = max(MIN_PULSE_US, min(MAX_PULSE_US, int(pulse_us)))
        counts = round(pulse_us * 4096 / 20000)
        base = LED0_ON_L + 4 * channel
        self.bus.write_i2c_block_data(PCA9685_ADDRESS, base, [0, 0, counts & 0xFF, counts >> 8])

    def pan_cb(self, msg):
        with self.lock:
            if not self.active:
                return
            try:
                self.pan = max(MIN_PULSE_US, min(MAX_PULSE_US, int(msg.data)))
                self.set_pulse(PAN_CHANNEL, self.pan)
                self.pan_pub.publish(Int32(data=self.pan))
            except Exception as exc:
                self.active = False
                self.status(f"ERROR: Arducam pan write failed ({exc})")

    def tilt_cb(self, msg):
        with self.lock:
            if not self.active:
                return
            try:
                self.tilt = max(MIN_PULSE_US, min(MAX_PULSE_US, int(msg.data)))
                self.set_pulse(TILT_CHANNEL, self.tilt)
                self.tilt_pub.publish(Int32(data=self.tilt))
            except Exception as exc:
                self.active = False
                self.status(f"ERROR: Arducam tilt write failed ({exc})")


def main():
    rclpy.init()
    node = ArducamPTZ()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
