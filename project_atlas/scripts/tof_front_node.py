#!/usr/bin/env python3
"""ROS2 node: VL53L0X @ 0x2d — publishes /tof/front (Float32, metres)."""
import os
os.environ.setdefault('BLINKA_LGPIO', '1')

# Monkey-patch: sensor at 0x2d has a corrupted timing-budget register.
# On init, the library reads the register and immediately writes it back
# via the measurement_timing_budget setter, which asserts value >= 20000.
# Patch the setter to clamp bad values before the assert runs.
import adafruit_vl53l0x as _vl_mod
_orig_prop = _vl_mod.VL53L0X.measurement_timing_budget
_orig_fset = _orig_prop.fset
def _safe_fset(self, budget_us):
    if budget_us < 20000:
        budget_us = 33823
    _orig_fset(self, budget_us)
_vl_mod.VL53L0X.measurement_timing_budget = property(_orig_prop.fget, _safe_fset)

import board, busio
import adafruit_vl53l0x
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

class TofFrontNode(Node):
    def __init__(self):
        super().__init__('tof_front')
        i2c = busio.I2C(board.SCL, board.SDA)
        try:
            self.sensor = adafruit_vl53l0x.VL53L0X(i2c, address=0x2d)
            self.sensor.measurement_timing_budget = 200000
            self.get_logger().info('tof_front_node ready (VL53L0X @ 0x2d)')
        except Exception as e:
            self.get_logger().error(f'VL53L0X @ 0x2d init failed: {e}')
            self.sensor = None
        self.pub = self.create_publisher(Float32, '/tof/front', 10)
        self.create_timer(0.1, self.cb)

    def cb(self):
        if self.sensor is None:
            return
        try:
            r = self.sensor.range
            d = r / 1000.0 if r < 8190 else -0.001
        except Exception as e:
            self.get_logger().warn(f'TOF front read: {e}')
            d = -0.001
        self.pub.publish(Float32(data=d))

def main():
    rclpy.init()
    n = TofFrontNode()
    try:
        rclpy.spin(n)
    except Exception:
        pass
    n.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
