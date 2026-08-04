#!/usr/bin/env python3
"""ROS2 node: VL6180X @ 0x2d (left front TOF) — publishes /tof/left (Float32, metres)."""
import os
os.environ.setdefault('BLINKA_LGPIO', '1')

import board, busio
import adafruit_vl6180x
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

class TofLeftNode(Node):
    def __init__(self):
        super().__init__('tof_left')
        i2c = busio.I2C(board.SCL, board.SDA)
        try:
            self.sensor = adafruit_vl6180x.VL6180X(i2c, address=0x2d)
            self.get_logger().info('tof_left_node ready (VL6180X @ 0x2d)')
        except Exception as e:
            self.get_logger().error(f'VL6180X @ 0x2d init failed: {e}')
            self.sensor = None
        self.pub = self.create_publisher(Float32, '/tof/left', 10)
        self.create_timer(0.1, self.cb)

    def cb(self):
        if self.sensor is None:
            return
        try:
            r = self.sensor.range          # millimetres, VL6180X max ~200mm
            status = self.sensor.range_status
            if status == adafruit_vl6180x.ERROR_NONE:
                d = float(r) / 1000.0
            else:
                d = -0.001
        except Exception as e:
            self.get_logger().warn(f'TOF left read: {e}')
            d = -0.001
        self.pub.publish(Float32(data=d))

def main():
    rclpy.init()
    n = TofLeftNode()
    try:
        rclpy.spin(n)
    except Exception:
        pass
    n.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
