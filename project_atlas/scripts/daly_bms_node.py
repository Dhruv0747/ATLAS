#!/usr/bin/env python3
import json
import re
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String


MAC = "41:1A:04:01:06:84"
ADDR_TYPE = "random"
NOTIFY_CCCD_HANDLE = "0x0011"
WRITE_HANDLE = "0x0014"

COMMANDS = {
    "pack": "a540900800000000000000007d",
    "cells": "a5409508000000000000000082",
    "cell_extreme": "a540910800000000000000007e",
}


class DalyBmsNode(Node):
    def __init__(self):
        super().__init__("daly_bms_node")
        self.status_pub = self.create_publisher(String, "/bms/status", 10)
        self.json_pub = self.create_publisher(String, "/bms/json", 10)
        self.voltage_pub = self.create_publisher(Float32, "/bms/voltage", 10)
        self.current_pub = self.create_publisher(Float32, "/bms/current", 10)
        self.percent_pub = self.create_publisher(Float32, "/bms/percent", 10)
        self.power_pub = self.create_publisher(Float32, "/bms/power", 10)
        self.min_cell_pub = self.create_publisher(Float32, "/bms/min_cell_voltage", 10)
        self.max_cell_pub = self.create_publisher(Float32, "/bms/max_cell_voltage", 10)
        self.cell_pubs = [
            self.create_publisher(Float32, f"/bms/cell{i}_voltage", 10)
            for i in range(1, 5)
        ]
        self.timer = self.create_timer(5.0, self.poll)
        self.last = {}
        self.poll()

    def publish_float(self, pub, value):
        msg = Float32()
        msg.data = float(value)
        pub.publish(msg)

    def poll(self):
        started = time.time()
        try:
            out = self.read_ble()
            data = self.decode(out)
            if not data:
                raise RuntimeError("no Daly notification received")
            data["mac"] = MAC
            data["age_s"] = 0
            data["ok"] = True
            data["source"] = "bluetooth"
            self.last = data
            self.publish_data(data)
            self.get_logger().info(
                f"Daly OK {data.get('voltage_v', 0):.2f}V "
                f"{data.get('current_a', 0):+.2f}A {data.get('soc_percent', 0):.1f}%"
            )
        except Exception as exc:
            fallback = dict(self.last)
            fallback["ok"] = False
            fallback["error"] = str(exc)
            fallback["age_s"] = round(time.time() - started, 1)
            self.publish_data(fallback)
            self.get_logger().warn(f"Daly read failed: {exc}")

    def read_ble(self):
        proc = subprocess.Popen(
            ["gatttool", "-b", MAC, "-t", ADDR_TYPE, "-I"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            self._send(proc, "connect", 4.0)
            self._send(proc, f"char-write-req {NOTIFY_CCCD_HANDLE} 0100", 0.8)
            for cmd in COMMANDS.values():
                self._send(proc, f"char-write-req {WRITE_HANDLE} {cmd}", 1.4)
            time.sleep(1.5)
            proc.terminate()
            out, _ = proc.communicate(timeout=3)
            return out
        except Exception:
            proc.kill()
            out, _ = proc.communicate(timeout=2)
            return out

    def _send(self, proc, text, delay):
        if proc.stdin is None:
            return
        proc.stdin.write(text + "\n")
        proc.stdin.flush()
        time.sleep(delay)

    def decode(self, text):
        frames = []
        for line in text.splitlines():
            if "Notification handle" not in line or "value:" not in line:
                continue
            hex_part = line.split("value:", 1)[1]
            vals = [int(x, 16) for x in re.findall(r"\b[0-9a-fA-F]{2}\b", hex_part)]
            frames.extend(self.split_frames(vals))

        data = {}
        cells = {}
        for frame in frames:
            if len(frame) < 7 or frame[0] != 0xA5:
                continue
            cmd = frame[2]
            payload = frame[4:12]
            if cmd in (0x90, 0x91) and len(frame) < 13:
                continue
            if cmd == 0x90:
                voltage = self.u16(payload, 0) / 10.0
                current = (self.u16(payload, 4) - 30000) / 10.0
                soc = self.u16(payload, 6) / 10.0
                data.update({
                    "voltage_v": voltage,
                    "current_a": current,
                    "soc_percent": soc,
                    "power_w": voltage * current,
                })
            elif cmd == 0x95:
                page = payload[0]
                for slot in range(3):
                    idx = (page - 1) * 3 + slot + 1
                    off = 1 + slot * 2
                    if off + 1 >= len(payload) or idx > 4:
                        continue
                    mv = self.u16(payload, off)
                    if mv > 0:
                        cells[idx] = mv / 1000.0
            elif cmd == 0x91:
                data["max_cell_voltage_v"] = self.u16(payload, 0) / 1000.0
                data["max_cell_index"] = payload[2]
                data["min_cell_voltage_v"] = self.u16(payload, 3) / 1000.0
                data["min_cell_index"] = payload[5]

        if cells:
            data["cells_v"] = [cells.get(i, 0.0) for i in range(1, 5)]
        return data

    def split_frames(self, vals):
        frames = []
        starts = [i for i, value in enumerate(vals) if value == 0xA5]
        for pos, start in enumerate(starts):
            end = starts[pos + 1] if pos + 1 < len(starts) else len(vals)
            frame = vals[start:end]
            if len(frame) >= 7:
                frames.append(frame[:13])
        return frames

    def u16(self, payload, offset):
        return (payload[offset] << 8) | payload[offset + 1]

    def publish_data(self, data):
        status = String()
        status.data = json.dumps(data, separators=(",", ":"))
        self.status_pub.publish(status)
        self.json_pub.publish(status)
        if "voltage_v" in data:
            self.publish_float(self.voltage_pub, data["voltage_v"])
        if "current_a" in data:
            self.publish_float(self.current_pub, data["current_a"])
        if "soc_percent" in data:
            self.publish_float(self.percent_pub, data["soc_percent"])
        if "power_w" in data:
            self.publish_float(self.power_pub, data["power_w"])
        if "min_cell_voltage_v" in data:
            self.publish_float(self.min_cell_pub, data["min_cell_voltage_v"])
        if "max_cell_voltage_v" in data:
            self.publish_float(self.max_cell_pub, data["max_cell_voltage_v"])
        for i, value in enumerate(data.get("cells_v", [])[:4]):
            if value > 0:
                self.publish_float(self.cell_pubs[i], value)


def main():
    rclpy.init()
    node = DalyBmsNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
