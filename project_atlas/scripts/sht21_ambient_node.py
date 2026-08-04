#!/usr/bin/env python3
import time

import rclpy
from rclpy.node import Node
from smbus2 import SMBus, i2c_msg
from std_msgs.msg import Float32, String

BUS_ID = 7
ADDRESS = 0x40


def crc_valid(data):
    remainder = (data[0] << 8) | data[1]
    remainder <<= 8
    remainder |= data[2]
    polynomial = 0x988000
    bit = 1 << 23
    while bit >= 1 << 8:
        if remainder & bit:
            remainder ^= polynomial
        polynomial >>= 1
        bit >>= 1
    return remainder == 0


class Sht21AmbientNode(Node):
    def __init__(self):
        super().__init__("sht21_ambient")
        self.temperature_pub = self.create_publisher(
            Float32, "/environment/outside_temperature_c", 10
        )
        self.humidity_pub = self.create_publisher(
            Float32, "/environment/outside_humidity_pct", 10
        )
        self.status_pub = self.create_publisher(
            String, "/environment/outside_status", 10
        )
        self.bus = None
        self.create_timer(2.0, self.poll)
        self.get_logger().info(
            f"SHT21 outside ambient node starting: bus={BUS_ID} addr=0x{ADDRESS:02x}"
        )
        self.poll()

    def open_bus(self):
        if self.bus is None:
            self.bus = SMBus(BUS_ID)

    def measure(self, command, delay):
        self.open_bus()
        self.bus.i2c_rdwr(i2c_msg.write(ADDRESS, [command]))
        time.sleep(delay)
        response = i2c_msg.read(ADDRESS, 3)
        self.bus.i2c_rdwr(response)
        data = list(response)
        if len(data) != 3 or not crc_valid(data):
            raise RuntimeError(f"invalid SHT21 response {data}")
        return ((data[0] << 8) | data[1]) & 0xFFFC

    def poll(self):
        try:
            raw_temperature = self.measure(0xF3, 0.10)
            raw_humidity = self.measure(0xF5, 0.04)
            temperature = -46.85 + 175.72 * raw_temperature / 65536.0
            humidity = -6.0 + 125.0 * raw_humidity / 65536.0
            humidity = max(0.0, min(100.0, humidity))
            self.temperature_pub.publish(Float32(data=float(temperature)))
            self.humidity_pub.publish(Float32(data=float(humidity)))
            self.status_pub.publish(
                String(
                    data=(
                        f"SHT21_OK addr=0x{ADDRESS:02x} "
                        f"temperature={temperature:.2f}C humidity={humidity:.1f}%"
                    )
                )
            )
        except Exception as error:
            self.status_pub.publish(String(data=f"SHT21_OFFLINE error={error}"))
            self.get_logger().warn(f"SHT21 read failed: {error}")
            if self.bus is not None:
                try:
                    self.bus.close()
                except Exception:
                    pass
                self.bus = None


def main():
    rclpy.init()
    node = Sht21AmbientNode()
    try:
        rclpy.spin(node)
    finally:
        if node.bus is not None:
            node.bus.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
