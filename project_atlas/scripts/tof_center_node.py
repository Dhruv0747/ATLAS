#!/usr/bin/env python3
import os
import time

os.environ.setdefault('BLINKA_LGPIO', '1')

import board
import busio
import adafruit_vl53l0x
import Jetson.GPIO as GPIO
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

TOF_ADDR = 0x29
XSHUT_PIN = 25
MAX_VALID_MM = 8190


class TofCenterNode(Node):
    def __init__(self):
        super().__init__('tof_center')
        self.pub = self.create_publisher(Float32, '/tof/center', 10)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(XSHUT_PIN, GPIO.OUT)
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.sensor = None
        self.fail_count = 0
        self._reset_sensor_power()
        self._init_sensor()
        self.timer = self.create_timer(0.1, self.cb)

    def _reset_sensor_power(self):
        GPIO.output(XSHUT_PIN, GPIO.LOW)
        time.sleep(0.08)
        GPIO.output(XSHUT_PIN, GPIO.HIGH)
        time.sleep(0.25)

    def _init_sensor(self):
        self.sensor = None
        for attempt in range(5):
            try:
                self.sensor = adafruit_vl53l0x.VL53L0X(self.i2c, address=TOF_ADDR)
                self.fail_count = 0
                self.get_logger().info(f'VL53L0X ready at 0x{TOF_ADDR:02x}')
                return True
            except Exception as e:
                self.get_logger().warn(f'VL53L0X init attempt {attempt + 1}/5 failed: {e}')
                if attempt == 1:
                    self._reset_sensor_power()
                time.sleep(0.25)
        self.get_logger().error('VL53L0X init failed after retries')
        return False

    def cb(self):
        d = -0.001
        if self.sensor is None:
            self._init_sensor()
        if self.sensor is not None:
            try:
                r = int(self.sensor.range)
                if 0 < r < MAX_VALID_MM:
                    d = float(r)
                    self.fail_count = 0
                else:
                    self.fail_count += 1
            except Exception as e:
                self.fail_count += 1
                if self.fail_count in (1, 10, 30):
                    self.get_logger().warn(f'VL53L0X read failed: {e}')
        if self.fail_count >= 10:
            self._reset_sensor_power()
            self.sensor = None
            self.fail_count = 0
        self.pub.publish(Float32(data=d))

    def destroy_node(self):
        try:
            GPIO.output(XSHUT_PIN, GPIO.HIGH)
        except Exception:
            pass
        return super().destroy_node()


def main():
    rclpy.init()
    node = TofCenterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        GPIO.cleanup()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
