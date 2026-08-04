#!/usr/bin/env python3
import json
import math
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String

try:
    from smbus2 import SMBus
except Exception:
    from smbus import SMBus

BUS_ID = 7
ADDRS = [0x69, 0x68]
PIXEL_BASE = 0x80


def signed_12(raw):
    raw &= 0x0FFF
    if raw & 0x800:
        raw -= 0x1000
    return raw


class AMG8833Node(Node):
    def __init__(self):
        super().__init__('amg8833_thermal')
        self.bus = SMBus(BUS_ID)
        self.addr = None
        self.last_detect = 0.0
        self.pub_json = self.create_publisher(String, '/thermal/amg8833/json', 10)
        self.pub_status = self.create_publisher(String, '/thermal/amg8833/status', 10)
        self.pub_min = self.create_publisher(Float32, '/thermal/amg8833/min_c', 10)
        self.pub_max = self.create_publisher(Float32, '/thermal/amg8833/max_c', 10)
        self.pub_avg = self.create_publisher(Float32, '/thermal/amg8833/avg_c', 10)
        self.pub_center = self.create_publisher(Float32, '/thermal/amg8833/center_c', 10)
        self.create_timer(0.5, self.tick)
        self.get_logger().info('AMG8833 thermal node starting: bus=7 addr candidates=0x69,0x68')

    def detect(self):
        now = time.time()
        if self.addr is not None and now - self.last_detect < 10:
            return True
        for addr in ADDRS:
            try:
                self.bus.write_byte_data(addr, 0x00, 0x00)  # normal mode
                time.sleep(0.01)
                self.bus.write_byte_data(addr, 0x01, 0x3F)  # initial reset
                time.sleep(0.01)
                self.bus.write_byte_data(addr, 0x02, 0x00)  # 10 fps
                self.addr = addr
                self.last_detect = now
                return True
            except Exception:
                pass
        self.addr = None
        self.last_detect = now
        return False

    def read_pixels(self):
        data = []
        for offset in range(0, 128, 32):
            data.extend(self.bus.read_i2c_block_data(self.addr, PIXEL_BASE + offset, 32))
        vals = []
        for i in range(64):
            raw = data[i * 2] | (data[i * 2 + 1] << 8)
            vals.append(round(signed_12(raw) * 0.25, 2))
        return vals

    def tick(self):
        if not self.detect():
            self.pub_status.publish(String(data='AMG8833_OFFLINE expected=0x69_or_0x68 bus=7'))
            self.pub_json.publish(String(data=json.dumps({'ok': False, 'status': 'offline', 'addr': None, 'pixels': []})))
            return
        try:
            pix = self.read_pixels()
            mn, mx = min(pix), max(pix)
            avg = sum(pix) / len(pix)
            center = sum([pix[27], pix[28], pix[35], pix[36]]) / 4.0
            payload = {
                'ok': True,
                'status': 'ok',
                'addr': hex(self.addr),
                'min_c': round(mn, 2),
                'max_c': round(mx, 2),
                'avg_c': round(avg, 2),
                'center_c': round(center, 2),
                'pixels': pix,
            }
            self.pub_json.publish(String(data=json.dumps(payload, separators=(',', ':'))))
            self.pub_status.publish(String(data=f'AMG8833_OK addr={hex(self.addr)} min={mn:.1f}C max={mx:.1f}C avg={avg:.1f}C'))
            self.pub_min.publish(Float32(data=float(mn)))
            self.pub_max.publish(Float32(data=float(mx)))
            self.pub_avg.publish(Float32(data=float(avg)))
            self.pub_center.publish(Float32(data=float(center)))
        except Exception as exc:
            self.pub_status.publish(String(data=f'AMG8833_ERROR {exc}'))
            self.addr = None


def main():
    rclpy.init()
    node = AMG8833Node()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
