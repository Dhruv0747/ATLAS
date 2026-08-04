#!/usr/bin/env python3
"""ROS2 node: INA219 @ 0x40 (PCIe HAT) — publishes /hat/voltage /hat/current /hat/power."""
import board, busio
from adafruit_ina219 import INA219
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

class HatPowerNode(Node):
    def __init__(self):
        super().__init__('hat_power')
        i2c = busio.I2C(board.SCL, board.SDA)
        self.ina = INA219(i2c, addr=0x40)
        self.pub_v = self.create_publisher(Float32, '/hat/voltage', 10)
        self.pub_i = self.create_publisher(Float32, '/hat/current', 10)
        self.pub_p = self.create_publisher(Float32, '/hat/power',   10)
        self.create_timer(1.0, self.cb)
        self.get_logger().info('hat_power_node ready (INA219 @ 0x40)')

    def cb(self):
        try:
            v = self.ina.bus_voltage
            i = self.ina.current / 1000.0
            p = self.ina.power   / 1000.0
            self.pub_v.publish(Float32(data=v))
            self.pub_i.publish(Float32(data=i))
            self.pub_p.publish(Float32(data=p))
        except Exception as e:
            self.get_logger().warn(f'INA219 read: {e}')

def main():
    rclpy.init()
    rclpy.spin(HatPowerNode())
    rclpy.shutdown()

if __name__ == '__main__':
    main()
