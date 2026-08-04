#!/usr/bin/env python3
"""Waveshare UPS HAT (E) ROS2 monitor.

Publishes UPS HAT data separately from the rover 12V battery:
  /ups/status
  /ups/vbus_voltage, /ups/vbus_current, /ups/vbus_power
  /ups/battery_voltage, /ups/battery_current, /ups/battery_percent
  /ups/battery_remaining_mah, /ups/discharge_time_min, /ups/charge_time_min
  /ups/cell1_voltage ... /ups/cell4_voltage

Register source: Waveshare UPS HAT (E) register manual, address 0x2D.
"""
import json
import struct
import time

import rclpy
import smbus2
from rclpy.node import Node
from std_msgs.msg import Bool, Float32, String

ADDR = 0x2D


class UpsHatE:
    def __init__(self, bus_id=1):
        self.bus = smbus2.SMBus(bus_id)

    def u8(self, reg):
        return self.bus.read_byte_data(ADDR, reg)

    def u16(self, lo_reg):
        lo = self.u8(lo_reg)
        hi = self.u8(lo_reg + 1)
        return (hi << 8) | lo

    def i16(self, lo_reg):
        return struct.unpack("<h", self.u16(lo_reg).to_bytes(2, "little"))[0]

    def read(self):
        ident = self.u8(0x00)
        auto_reg = self.u8(0x01)
        charge_reg = self.u8(0x02)
        comm_reg = self.u8(0x03)
        sw_rev = self.u8(0x50)

        charging = bool(charge_reg & 0x80)
        fast_charging = bool(charge_reg & 0x40)
        vbus_present = bool(charge_reg & 0x20)
        charge_state_code = charge_reg & 0x07
        charge_states = {
            0: "standby",
            1: "trickle",
            2: "constant_current",
            3: "constant_voltage",
            4: "charging_pending",
            5: "full",
            6: "charge_timeout",
        }

        battery_current_ma = self.i16(0x22)
        return {
            "id": ident,
            "auto_reg": auto_reg,
            "charge_reg": charge_reg,
            "comm_reg": comm_reg,
            "sw_rev": sw_rev,
            "charging": charging,
            "fast_charging": fast_charging,
            "vbus_present": vbus_present,
            "charge_state": charge_states.get(charge_state_code, f"unknown_{charge_state_code}"),
            "vbus_voltage_v": self.u16(0x10) / 1000.0,
            "vbus_current_a": self.i16(0x12) / 1000.0,
            "vbus_power_w": self.u16(0x14) / 1000.0,
            "battery_voltage_v": self.u16(0x20) / 1000.0,
            "battery_current_a": battery_current_ma / 1000.0,
            "battery_power_w": (self.u16(0x20) / 1000.0) * (battery_current_ma / 1000.0),
            "battery_percent": float(self.u16(0x24)),
            "remaining_mah": float(self.u16(0x26)),
            "discharge_time_min": float(self.u16(0x28)),
            "charge_time_min": float(self.u16(0x2A)),
            "cell1_v": self.u16(0x30) / 1000.0,
            "cell2_v": self.u16(0x32) / 1000.0,
            "cell3_v": self.u16(0x34) / 1000.0,
            "cell4_v": self.u16(0x36) / 1000.0,
        }


class UpsNode(Node):
    def __init__(self):
        super().__init__("ups_hat_e")
        self.dev = None
        self.last_error = ""
        self.pub_status = self.create_publisher(String, "/ups/status", 10)
        self.pub_json = self.create_publisher(String, "/ups/json", 10)
        self.pub_charging = self.create_publisher(Bool, "/ups/charging", 10)
        self.pub_charge_state = self.create_publisher(String, "/ups/charge_state", 10)
        self.pubs = {
            "vbus_voltage_v": self.create_publisher(Float32, "/ups/vbus_voltage", 10),
            "vbus_current_a": self.create_publisher(Float32, "/ups/vbus_current", 10),
            "vbus_power_w": self.create_publisher(Float32, "/ups/vbus_power", 10),
            "battery_voltage_v": self.create_publisher(Float32, "/ups/battery_voltage", 10),
            "battery_current_a": self.create_publisher(Float32, "/ups/battery_current", 10),
            "battery_power_w": self.create_publisher(Float32, "/ups/battery_power", 10),
            "battery_percent": self.create_publisher(Float32, "/ups/battery_percent", 10),
            "remaining_mah": self.create_publisher(Float32, "/ups/battery_remaining_mah", 10),
            "discharge_time_min": self.create_publisher(Float32, "/ups/discharge_time_min", 10),
            "charge_time_min": self.create_publisher(Float32, "/ups/charge_time_min", 10),
            "cell1_v": self.create_publisher(Float32, "/ups/cell1_voltage", 10),
            "cell2_v": self.create_publisher(Float32, "/ups/cell2_voltage", 10),
            "cell3_v": self.create_publisher(Float32, "/ups/cell3_voltage", 10),
            "cell4_v": self.create_publisher(Float32, "/ups/cell4_voltage", 10),
        }
        self.create_timer(1.0, self.tick)
        self.get_logger().info("UPS HAT E node ready, reading MCU at 0x2D")

    def connect(self):
        try:
            self.dev = UpsHatE()
            ident = self.dev.u8(0x00)
            if ident != 0x0A:
                raise RuntimeError(f"unexpected_id=0x{ident:02x}")
            self.last_error = ""
            return True
        except Exception as exc:
            self.dev = None
            self.last_error = str(exc)
            return False

    def tick(self):
        if self.dev is None and not self.connect():
            msg = f"UPS_HAT_E_OFFLINE addr=0x2D error={self.last_error}"
            self.pub_status.publish(String(data=msg))
            return
        try:
            data = self.dev.read()
        except Exception as exc:
            self.dev = None
            self.last_error = str(exc)
            self.pub_status.publish(String(data=f"UPS_HAT_E_OFFLINE addr=0x2D error={exc}"))
            return

        for key, pub in self.pubs.items():
            pub.publish(Float32(data=float(data[key])))
        self.pub_charging.publish(Bool(data=bool(data["charging"])))
        self.pub_charge_state.publish(String(data=str(data["charge_state"])))
        status = (
            f"UPS_HAT_E_OK batt={data['battery_percent']:.0f}% "
            f"{data['battery_voltage_v']:.2f}V {data['battery_current_a']:+.2f}A "
            f"vbus={data['vbus_voltage_v']:.2f}V {data['vbus_current_a']:+.2f}A "
            f"{data['charge_state']}"
        )
        self.pub_status.publish(String(data=status))
        self.pub_json.publish(String(data=json.dumps(data, separators=(",", ":"))))


def main():
    rclpy.init()
    node = UpsNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
