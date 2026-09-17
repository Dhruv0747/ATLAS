#!/usr/bin/env python3
"""RD03D 24GHz radar ROS2 node publishing /radar/targets."""

import struct
import time
import os
import json
from atlas_radar_core import Decoder, ENABLE_CONFIG, QUERY_VERSION, END_CONFIG

import rclpy
import serial
from rclpy.node import Node
from std_msgs.msg import Float32, String

HEADER = b"\xaa\xff\x03\x00"
FOOTER = b"\x55\xcc"
FRAME_LEN = 30
MULTI_TARGET_CMD = bytes.fromhex("FD FC FB FA 02 00 90 00 04 03 02 01")


def decode_signed_magnitude(raw):
    magnitude = raw & 0x7FFF
    return magnitude if raw & 0x8000 else -magnitude


class RD03DNode(Node):
    def __init__(self):
        super().__init__("rd03d")
        self.pub = self.create_publisher(String, "/radar/targets", 10)
        self.frames_pub = self.create_publisher(String, '/radar/frames', 10)
        self.decoder = Decoder()
        self.pub_count = self.create_publisher(Float32, "/radar/target_count", 10)
        self.pub_nearest = self.create_publisher(Float32, "/radar/nearest_distance", 10)
        self.pub_nearest_x = self.create_publisher(Float32, "/radar/nearest_x", 10)
        self.pub_nearest_y = self.create_publisher(Float32, "/radar/nearest_y", 10)
        self.pub_nearest_speed = self.create_publisher(Float32, "/radar/nearest_speed", 10)
        self.pub_zone = self.create_publisher(String, "/radar/zone", 10)
        self.pub_decoder_status = self.create_publisher(
            String, "/radar/decoder_status", 10
        )
        self.buf = b""
        self.ser = None
        self.raw_bytes = 0
        self.valid_frames = 0
        self.bad_footers = 0
        self.discarded_bytes = 0
        self.last_chunk_hex = ""
        self.started_at = time.monotonic()
        self.last_valid_frame_at = None
        self.source = os.environ.get("ATLAS_RADAR_SOURCE", "serial").strip().lower()
        if self.source == "topic":
            self.create_subscription(
                String, "/radar/hub/raw_hex", self.raw_hex_cb, 50
            )
            self.get_logger().info("RD03D decoder using UNO R4 sensor-hub stream")
        else:
            self.port = os.environ.get("ATLAS_RADAR_PORT", "/dev/ttyTHS1")
            self.ser = serial.Serial(
                self.port, 256000, timeout=0, rtscts=False, dsrdtr=False
            )
            time.sleep(0.5)
            # V2 commands require entering configuration first. ACKs are
            # exposed by Decoder; a transmitted command is not proof of mode.
            for command in (ENABLE_CONFIG, QUERY_VERSION, MULTI_TARGET_CMD, END_CONFIG):
                self.ser.write(command)
                self.ser.flush()
                time.sleep(0.10)
            self.ser.flush()
            time.sleep(0.2)
            self.timer = self.create_timer(0.05, self.read_cb)
            self.get_logger().info(
                f"RD03D configuration requested on {self.port}; awaiting ACK"
            )
        self.status_timer = self.create_timer(1.0, self.publish_decoder_status)

    def raw_hex_cb(self, msg):
        try:
            chunk = bytes.fromhex(msg.data.strip())
        except ValueError:
            self.get_logger().warning("Discarding malformed radar hex chunk")
            return
        self.last_chunk_hex = chunk[:32].hex().upper()
        self.raw_bytes += len(chunk)
        self.buf += chunk
        self.parse_frames()

    def read_cb(self):
        chunk = self.ser.read(128)
        if chunk:
            self.raw_bytes += len(chunk)
            self.buf += chunk

        self.parse_frames()

    def parse_frames(self):
        decoded = self.decoder.feed(self.buf)
        self.buf = b''
        self.bad_footers = self.decoder.bad
        self.discarded_bytes = self.decoder.discarded
        for targets in decoded:
            self.valid_frames += 1
            self.last_valid_frame_at = time.monotonic()
            self.frames_pub.publish(String(data=json.dumps({
                'sequence': self.valid_frames,
                'stamp_s': self.get_clock().now().nanoseconds/1e9,
                'timestamp_source': 'jetson_receive_no_sensor_clock',
                'protocol': 'AAFF0300_3x8_55CC', 'targets': targets,
                'hardware_revision': 'unverified',
                'firmware_acks': self.decoder.acks,
            }, allow_nan=False)))
            target_strings = []
            target_values = []
            for target in targets:
                target_index = target['slot']
                x, y, speed = target['x_mm'], target['y_mm'], target['speed_cm_s']
                if y > 0:
                    distance = (x * x + y * y) ** 0.5
                    target_values.append((distance, x, y, speed))
                    target_strings.append(
                        f"T{target_index}:x={x}mm,y={y}mm,spd={speed}cm/s"
                    )

            msg = String()
            msg.data = " | ".join(target_strings)
            self.pub.publish(msg)
            self.pub_count.publish(Float32(data=float(len(target_values))))
            if target_values:
                distance, x, y, speed = min(target_values, key=lambda item: item[0])
                zone = "DANGER" if distance < 500 else ("CAUTION" if distance < 1000 else "CLEAR")
                self.pub_nearest.publish(Float32(data=float(distance)))
                self.pub_nearest_x.publish(Float32(data=float(x)))
                self.pub_nearest_y.publish(Float32(data=float(y)))
                self.pub_nearest_speed.publish(Float32(data=float(speed)))
                self.pub_zone.publish(String(data=zone))
            else:
                self.pub_nearest.publish(Float32(data=-1.0))
                self.pub_nearest_x.publish(Float32(data=0.0))
                self.pub_nearest_y.publish(Float32(data=0.0))
                self.pub_nearest_speed.publish(Float32(data=0.0))
                self.pub_zone.publish(String(data="NO_TARGET"))

    def publish_decoder_status(self):
        now = time.monotonic()
        if self.last_valid_frame_at is None:
            frame_age = now - self.started_at
            state = "NO_VALID_FRAMES"
        else:
            frame_age = now - self.last_valid_frame_at
            state = "VALID" if frame_age < 2.0 else "STALE"
        status = (
            f"state={state} source={self.source} bytes={self.raw_bytes} "
            f"frames={self.valid_frames} bad_footers={self.bad_footers} "
            f"discarded={self.discarded_bytes} buffer={len(self.buf)} "
            f"last_frame_age={frame_age:.1f}s "
            f"sample={self.last_chunk_hex or 'NONE'}"
        )
        self.pub_decoder_status.publish(String(data=status))
        if state != 'VALID':
            # Clear legacy display consumers on disconnection, too.
            self.pub.publish(String(data=''))
            self.pub_count.publish(Float32(data=0.0))
            self.pub_nearest.publish(Float32(data=-1.0))
            self.pub_nearest_x.publish(Float32(data=0.0))
            self.pub_nearest_y.publish(Float32(data=0.0))
            self.pub_nearest_speed.publish(Float32(data=0.0))
            self.pub_zone.publish(String(data='STALE'))


def main():
    rclpy.init()
    node = RD03DNode()
    try:
        rclpy.spin(node)
    finally:
        if node.ser is not None:
            node.ser.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
