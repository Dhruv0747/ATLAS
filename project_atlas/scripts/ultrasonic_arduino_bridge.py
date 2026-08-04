#!/usr/bin/env python3
import re
import time
import os

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String, Int32

try:
    import serial
except Exception as exc:
    serial = None
    SERIAL_IMPORT_ERROR = exc
else:
    SERIAL_IMPORT_ERROR = None

PORT = '/dev/serial/by-id/usb-Arduino_UNO_WiFi_R4_CMSIS-DAP_E4B063836708-if01'
BAUD = 115200
ARDUCAM_MARKER = '/home/jetson/project_atlas/config/arducam_ptz_enabled'
LINE_RE = re.compile(r'F=(-?\d+),L=(-?\d+),R=(-?\d+)(?:,LA=(-?\d+),RA=(-?\d+),C1=(-?\d+),C2=(-?\d+),PCA=(\d+))?,OK=(\d+)')


class UltrasonicArduinoBridge(Node):
    def __init__(self):
        super().__init__('ultrasonic_arduino_bridge')
        self.front_pub = self.create_publisher(Float32, '/ultrasonic/front_mm', 10)
        self.left_pub = self.create_publisher(Float32, '/ultrasonic/left_mm', 10)
        self.right_pub = self.create_publisher(Float32, '/ultrasonic/right_mm', 10)
        self.status_pub = self.create_publisher(String, '/ultrasonic/status', 10)
        self.pca_status_pub = self.create_publisher(String, '/arduino/pca9685/status', 10)
        self.left_servo_pub = self.create_publisher(Int32, '/ultrasonic/left_servo_us', 10)
        self.right_servo_pub = self.create_publisher(Int32, '/ultrasonic/right_servo_us', 10)
        self.camera_bottom_pub = self.create_publisher(Int32, '/camera/bottom_servo_us', 10)
        self.camera_second_pub = self.create_publisher(Int32, '/camera/second_servo_us', 10)
        self.arducam_active = os.path.exists(ARDUCAM_MARKER)
        self.create_subscription(Int32, '/arduino/pca9685/servo_us', self.servo_cmd_cb, 10)
        self.create_subscription(Int32, '/ultrasonic/left_servo_cmd_us', lambda m: self.send_servo(0, m.data), 10)
        if not self.arducam_active:
            self.create_subscription(Int32, '/camera/bottom_servo_cmd_us', lambda m: self.send_servo(1, m.data), 10)
            self.create_subscription(Int32, '/camera/second_servo_cmd_us', lambda m: self.send_servo(2, m.data), 10)
        self.create_subscription(Int32, '/ultrasonic/right_servo_cmd_us', lambda m: self.send_servo(3, m.data), 10)
        self.ser = None
        self.last_ok = 0.0
        self.create_timer(0.05, self.tick)
        route = 'Arducam I2C' if self.arducam_active else 'legacy Arduino PCA'
        self.get_logger().info(f'Ultrasonic Arduino bridge starting on {PORT}; camera route: {route}')

    def connect(self):
        if serial is None:
            self.status_pub.publish(String(data=f'pyserial_missing {SERIAL_IMPORT_ERROR}'))
            return False
        try:
            self.ser = serial.Serial(PORT, BAUD, timeout=0.02)
            time.sleep(1.8)
            self.status_pub.publish(String(data='connected'))
            self.write_line('PCA?')
            self.write_line('HOME')
            return True
        except Exception as exc:
            self.ser = None
            self.status_pub.publish(String(data=f'connect_error {exc}'))
            return False

    @staticmethod
    def publish_mm(pub, value):
        pub.publish(Float32(data=float(value if value >= 0 else -1)))

    def write_line(self, line):
        if self.ser is None:
            return False
        try:
            self.ser.write((line.strip() + '\n').encode())
            return True
        except Exception as exc:
            self.status_pub.publish(String(data=f'write_error {exc}'))
            return False

    def send_servo(self, channel, pulse_us):
        pulse_us = int(pulse_us)
        if pulse_us <= 0:
            self.write_line(f'FREE,{int(channel)}')
            return
        pulse_us = max(500, min(2500, pulse_us))
        self.write_line(f'SERVO,{int(channel)},{pulse_us}')

    def servo_cmd_cb(self, msg):
        value = int(msg.data)
        channel = (value // 10000) & 0xFF
        pulse = value % 10000
        self.send_servo(channel, pulse)

    def tick(self):
        if self.ser is None:
            self.connect()
            return
        try:
            raw = self.ser.readline().decode(errors='replace').strip()
        except Exception as exc:
            self.status_pub.publish(String(data=f'read_error {exc}'))
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            return
        if not raw:
            if time.time() - self.last_ok > 2.5:
                self.status_pub.publish(String(data='waiting_for_data'))
            return
        if raw.startswith('ATLAS_ULTRASONIC'):
            self.status_pub.publish(String(data=raw))
            return
        if raw.startswith('ACK,') or raw.startswith('ERR,'):
            self.pca_status_pub.publish(String(data=raw))
            return
        m = LINE_RE.fullmatch(raw)
        if not m:
            self.status_pub.publish(String(data=f'parse_error {raw[:80]}'))
            return
        groups = m.groups()
        front, left, right = [int(v) for v in groups[:3]]
        la, ra, c1, c2, pca, ok = groups[3:]
        self.publish_mm(self.front_pub, front)
        self.publish_mm(self.left_pub, left)
        self.publish_mm(self.right_pub, right)
        if la is not None:
            self.left_servo_pub.publish(Int32(data=int(la)))
            self.right_servo_pub.publish(Int32(data=int(ra)))
            if not self.arducam_active:
                self.camera_bottom_pub.publish(Int32(data=int(c1)))
                self.camera_second_pub.publish(Int32(data=int(c2)))
            self.pca_status_pub.publish(String(data=f'pca={pca} left_us={la} right_us={ra} cam1_us={c1} cam2_us={c2}'))
        self.last_ok = time.time()
        self.status_pub.publish(String(data=f'ok front={front} left={left} right={right}'))

    def destroy_node(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        super().destroy_node()


def main():
    rclpy.init()
    node = UltrasonicArduinoBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
