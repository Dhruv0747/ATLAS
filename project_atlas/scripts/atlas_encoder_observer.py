#!/usr/bin/env python3
"""Passive Yahboom encoder monitor during commissioning. Never transmits."""
import json
import struct
import time
import serial
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import Int32, String


def extract_frames(buffer):
    frames = []
    while len(buffer) >= 5:
        if buffer[:2] != b'\xff\xfb':
            del buffer[0]
            continue
        size = buffer[2] + 2
        if size < 5 or size > 128:
            del buffer[0]
            continue
        if len(buffer) < size:
            break
        packet = bytes(buffer[:size])
        if sum(packet[2:-1]) % 256 != packet[-1]:
            del buffer[0]
            continue
        del buffer[:size]
        frames.append((packet[3], packet[4:-1]))
    return frames


class EncoderObserver(Node):
    def __init__(self):
        super().__init__('atlas_encoder_observer')
        self.pubs = [self.create_publisher(Int32, f'/yahboom/encoder/m{i}', 10) for i in range(1, 5)]
        self.health = self.create_publisher(String, '/atlas/encoder_health', 10)
        self.link = None
        self.retry = 0.
        self.last = 0.
        self.frames = 0
        self.buffer = bytearray()
        self.create_timer(.02, self.poll)
        self.create_timer(1., self.status)

    def poll(self):
        now = time.monotonic()
        try:
            if self.link is None:
                if now < self.retry:
                    return
                self.retry = now + 3
                s = serial.Serial(port=None, baudrate=115200, timeout=0, exclusive=True)
                s.dtr = False
                s.rts = False
                s.port = '/dev/serial/by-path/platform-3610000.usb-usb-0:2.4:1.0-port0'
                s.open()
                self.link = s
                self.buffer.clear()
            self.buffer.extend(self.link.read(min(self.link.in_waiting, 4096)))
            for kind, payload in extract_frames(self.buffer):
                if kind == 0x0d and len(payload) == 16:
                    if not self.frames:
                        self.get_logger().info(f'Checksum-valid encoder channels: {struct.unpack("<4i", payload)}')
                    for pub, value in zip(self.pubs, struct.unpack('<4i', payload)):
                        pub.publish(Int32(data=value))
                    self.last = now
                    self.frames += 1
        except (OSError, serial.SerialException) as exc:
            self.get_logger().warning(str(exc))
            if self.link:
                self.link.close()
            self.link = None

    def status(self):
        age = time.monotonic() - self.last if self.last else None
        self.health.publish(String(data=json.dumps({
            'state': 'MONITOR_ONLY' if age is not None and age < .5 else 'STALE',
            'faults': ['Drive inhibited; dynamic encoder validation pending'],
            'age_s': age, 'frames': self.frames, 'motion_authorized': False,
        })))


def main():
    rclpy.init()
    node = EncoderObserver()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node.link:
            node.link.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
