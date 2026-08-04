#!/usr/bin/env python3
import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float32, String

import smbus2


PCA_ADDR = 0x42
CH_ULTRA_LEFT = 0
CH_CAMERA_BOTTOM = 1
CH_ULTRA_RIGHT = 3

SCAN_SEQUENCE = [-80.0, 0.0, 80.0, 0.0]
SCAN_STEP_SEC = 0.45
LEFT_ULTRA_HOME_US = 2000
RIGHT_ULTRA_HOME_US = 700
MANUAL_HOLD_SEC = 8.0

CENTER_US = 1500
MIN_US = 1000
MAX_US = 2000


def clamp(value, low, high):
    return max(low, min(high, value))


class Pca9685:
    def __init__(self, address=PCA_ADDR, bus_id=1):
        self.address = address
        self.bus = smbus2.SMBus(bus_id)
        self.write8(0x00, 0x10)
        time.sleep(0.005)
        prescale = round(25000000 / (4096 * 50)) - 1
        self.write8(0xFE, prescale)
        self.write8(0x00, 0x00)
        time.sleep(0.005)
        self.write8(0x00, 0xA0)

    def write8(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value & 0xFF)

    def pulse(self, channel, pulse_us):
        pulse_us = int(clamp(pulse_us, 700, 2300))
        ticks = int(pulse_us * 4096 / 20000)
        reg = 0x06 + 4 * int(channel)
        self.write8(reg, 0)
        self.write8(reg + 1, 0)
        self.write8(reg + 2, ticks & 0xFF)
        self.write8(reg + 3, ticks >> 8)


class AtlasPcaServoNode(Node):
    def __init__(self):
        super().__init__("atlas_pca_servo_node")
        self.pca = Pca9685()
        self.angles = {
            "ultrasonic_left_deg": 0.0,
            "ultrasonic_right_deg": 0.0,
            "camera_bottom_deg": 0.0,
        }
        self.auto_scan = False
        self.scan_index = 0
        self.manual_until = {"left": 0.0, "right": 0.0}
        self.status_pub = self.create_publisher(String, "/atlas/pca_servo/status", 10)
        self.left_scan_pub = self.create_publisher(Float32, "/ultrasonic/left_scan_angle", 10)
        self.right_scan_pub = self.create_publisher(Float32, "/ultrasonic/right_scan_angle", 10)
        self.create_subscription(Float32, "/ultrasonic/left_servo_angle", self.left_ultra_cb, 10)
        self.create_subscription(Float32, "/ultrasonic/right_servo_angle", self.right_ultra_cb, 10)
        self.create_subscription(Bool, "/ultrasonic/scan_enable", self.scan_enable_cb, 10)
        self.create_subscription(Float32, "/camera/bottom_angle", self.camera_bottom_cb, 10)
        self.create_subscription(Float32, "/camera/pan", self.camera_bottom_cb, 10)
        self.create_timer(1.0, self.publish_status)
        self.create_timer(SCAN_STEP_SEC, self.scan_step)

        self.pca.pulse(CH_ULTRA_LEFT, LEFT_ULTRA_HOME_US)
        self.pca.pulse(CH_ULTRA_RIGHT, RIGHT_ULTRA_HOME_US)
        self.set_servo(CH_CAMERA_BOTTOM, 0.0)
        self.get_logger().info(
            f"PCA servo ready addr=0x{PCA_ADDR:02x} "
            f"left_ultra=CH{CH_ULTRA_LEFT} right_ultra=CH{CH_ULTRA_RIGHT} "
            f"camera_bottom=CH{CH_CAMERA_BOTTOM}"
        )

    def angle_to_pulse(self, deg):
        deg = clamp(float(deg), -80.0, 80.0)
        return CENTER_US + (deg / 80.0) * 500.0

    def set_servo(self, channel, deg):
        self.pca.pulse(channel, self.angle_to_pulse(deg))

    def publish_angle(self, pub, deg):
        msg = Float32()
        msg.data = float(deg)
        pub.publish(msg)

    def left_ultra_cb(self, msg):
        deg = clamp(msg.data, -80.0, 80.0)
        self.manual_until["left"] = time.monotonic() + MANUAL_HOLD_SEC
        self.angles["ultrasonic_left_deg"] = deg
        self.set_servo(CH_ULTRA_LEFT, deg)
        self.publish_angle(self.left_scan_pub, deg)

    def right_ultra_cb(self, msg):
        deg = clamp(msg.data, -80.0, 80.0)
        self.manual_until["right"] = time.monotonic() + MANUAL_HOLD_SEC
        self.angles["ultrasonic_right_deg"] = deg
        self.set_servo(CH_ULTRA_RIGHT, deg)
        self.publish_angle(self.right_scan_pub, deg)

    def scan_enable_cb(self, msg):
        self.auto_scan = bool(msg.data)
        if not self.auto_scan:
            self.set_servo(CH_ULTRA_LEFT, 0.0)
            self.set_servo(CH_ULTRA_RIGHT, 0.0)

    def scan_step(self):
        if not self.auto_scan:
            return
        now = time.monotonic()
        deg = SCAN_SEQUENCE[self.scan_index % len(SCAN_SEQUENCE)]
        self.scan_index += 1
        if now >= self.manual_until["left"]:
            self.angles["ultrasonic_left_deg"] = deg
            self.set_servo(CH_ULTRA_LEFT, deg)
            self.publish_angle(self.left_scan_pub, deg)
        if now >= self.manual_until["right"]:
            self.angles["ultrasonic_right_deg"] = deg
            self.set_servo(CH_ULTRA_RIGHT, deg)
            self.publish_angle(self.right_scan_pub, deg)

    def camera_bottom_cb(self, msg):
        deg = clamp(msg.data, -80.0, 80.0)
        self.angles["camera_bottom_deg"] = deg
        self.set_servo(CH_CAMERA_BOTTOM, deg)

    def publish_status(self):
        payload = {
            "ok": True,
            "pca_addr": f"0x{PCA_ADDR:02x}",
            "auto_scan": self.auto_scan,
            "scan_sequence_deg": SCAN_SEQUENCE,
            "scan_step_sec": SCAN_STEP_SEC,
            "mapping": {
                "left_ultrasonic": CH_ULTRA_LEFT,
                "right_ultrasonic": CH_ULTRA_RIGHT,
                "camera_bottom": CH_CAMERA_BOTTOM,
                "unused_no_movement": [2, 4],
            },
            **self.angles,
        }
        msg = String()
        msg.data = json.dumps(payload, separators=(",", ":"))
        self.status_pub.publish(msg)


def main():
    rclpy.init()
    node = AtlasPcaServoNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
