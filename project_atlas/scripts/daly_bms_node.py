#!/usr/bin/env python3
import json
import re
import subprocess
import time
from atlas_daly_transport import read_snapshot

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

# Conservative resting-voltage estimate for the installed 4S LiFePO4 pack.
# LiFePO4 has a very flat discharge curve, so this is a safe fallback rather
# than a precision fuel gauge.  Prefer the DALY coulomb counter whenever its
# value is plausible.
LIFEPO4_CELL_SOC_CURVE = (
    (2.90, 0.0),
    (3.10, 5.0),
    (3.20, 10.0),
    (3.25, 20.0),
    (3.28, 30.0),
    (3.30, 45.0),
    (3.32, 60.0),
    (3.33, 70.0),
    (3.34, 80.0),
    (3.36, 90.0),
    (3.40, 95.0),
    (3.50, 98.0),
    (3.60, 100.0),
)


def interpolate_lifepo4_soc(cell_voltage):
    voltage = float(cell_voltage)
    if voltage <= LIFEPO4_CELL_SOC_CURVE[0][0]:
        return LIFEPO4_CELL_SOC_CURVE[0][1]
    for (low_v, low_soc), (high_v, high_soc) in zip(
        LIFEPO4_CELL_SOC_CURVE, LIFEPO4_CELL_SOC_CURVE[1:]
    ):
        if voltage <= high_v:
            fraction = (voltage - low_v) / (high_v - low_v)
            return low_soc + fraction * (high_soc - low_soc)
    return LIFEPO4_CELL_SOC_CURVE[-1][1]


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
            data["ok"] = all(key in data for key in ("voltage_v", "current_a", "soc_percent")) and data.get("cells_complete", False)
            if not data["ok"]:
                data["error"] = "Incomplete Daly snapshot; missing pack or cell frames"
            data["source"] = "bluetooth"
            self.last = data
            self.publish_data(data)
            self.get_logger().info(
                f"Daly {'OK' if data['ok'] else 'INCOMPLETE'} {data.get('voltage_v', 0):.2f}V "
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
        return read_snapshot(MAC, ADDR_TYPE, NOTIFY_CCCD_HANDLE, WRITE_HANDLE,
                             COMMANDS, self.decode)

    def decode(self, text):
        stream = []
        for line in text.splitlines():
            if "Notification handle" not in line or "value:" not in line:
                continue
            hex_part = line.split("value:", 1)[1]
            vals = [int(x, 16) for x in re.findall(r"\b[0-9a-fA-F]{2}\b", hex_part)]
            stream.extend(vals)

        frames = self.split_frames(stream)

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

        if data or cells:
            data["cells_complete"] = all(i in cells for i in range(1, 5))
            data["missing_cell_indices"] = [i for i in range(1, 5) if i not in cells]
            # Never fabricate zero volts for a cell whose frame was not received.
            # Omit the array entirely so consumers cannot mistake a partial pack
            # for a fresh four-cell measurement. Do not merge previous polls.
            if data["cells_complete"]:
                data["cells_v"] = [cells[i] for i in range(1, 5)]
        self.correct_soc(data)
        return data

    def correct_soc(self, data):
        """Replace an impossible DALY SOC with a conservative voltage estimate."""
        if "voltage_v" not in data:
            return
        native_soc = data.get("soc_percent")
        valid_cells = [
            float(value) for value in data.get("cells_v", [])
            if 2.0 <= float(value) <= 4.0
        ]
        cell_voltage = min(valid_cells) if valid_cells else float(data["voltage_v"]) / 4.0
        estimate = round(interpolate_lifepo4_soc(cell_voltage), 1)

        # A 4S LiFePO4 pack above 3.20 V/cell cannot truthfully be at 0%.
        native_invalid = (
            native_soc is None
            or not 0.0 <= float(native_soc) <= 100.0
            or (float(native_soc) <= 0.5 and cell_voltage >= 3.20)
        )
        data["soc_native_percent"] = native_soc
        data["soc_estimated_percent"] = estimate
        data["battery_chemistry"] = "4S_LiFePO4"
        data["soc_cell_voltage_v"] = round(cell_voltage, 3)
        if native_invalid:
            data["soc_percent"] = estimate
            data["soc_source"] = "voltage_estimate_lifepo4"
            data["soc_estimated"] = True
        else:
            data["soc_percent"] = float(native_soc)
            data["soc_source"] = "daly_coulomb_counter"
            data["soc_estimated"] = False

    def split_frames(self, vals):
        frames = []
        i = 0
        while i + 13 <= len(vals):
            frame = vals[i:i + 13]
            if (frame[0] == 0xA5 and frame[3] == 8
                    and (sum(frame[:12]) & 0xFF) == frame[12]):
                frames.append(frame)
                i += 13
            else:
                i += 1
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
