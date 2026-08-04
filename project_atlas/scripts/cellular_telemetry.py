#!/usr/bin/env python3
"""ROS 2 telemetry for the SIM8230 modem and Waveshare 5G HAT+."""

import math
import os
import subprocess
import termios
import threading
import time

import rclpy
import smbus2
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import Bool, Float32, String

INA_ADDR = 0x40
NMEA_PORT = (
    "/dev/serial/by-id/"
    "usb-1a86_USB_Single_Serial_5A99030279-if00"
)


class HatPowerMonitor:
    CALIBRATION = 26868
    CURRENT_LSB_MA = 0.1524
    POWER_LSB_W = 0.003048

    def __init__(self):
        self.bus = smbus2.SMBus(1)
        self._write(0x05, self.CALIBRATION)
        config = (1 << 11) | (0x0D << 7) | (0x0D << 3) | 0x07
        self._write(0x00, config)

    def _read(self, register):
        data = self.bus.read_i2c_block_data(INA_ADDR, register, 2)
        return (data[0] << 8) | data[1]

    def _write(self, register, value):
        self.bus.write_i2c_block_data(
            INA_ADDR, register, [(value >> 8) & 0xFF, value & 0xFF]
        )

    def read(self):
        self._write(0x05, self.CALIBRATION)
        bus_voltage = (self._read(0x02) >> 3) * 0.004
        current_raw = self._read(0x04)
        if current_raw >= 0x8000:
            current_raw -= 0x10000
        current = current_raw * self.CURRENT_LSB_MA / 1000.0
        power = self._read(0x03) * self.POWER_LSB_W
        return bus_voltage, current, power

    def close(self):
        if self.bus is not None:
            try:
                self.bus.close()
            finally:
                self.bus = None


def parse_key_values(output):
    result = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def nmea_checksum_valid(sentence):
    if not sentence.startswith("$") or "*" not in sentence:
        return False
    payload, checksum = sentence[1:].split("*", 1)
    value = 0
    for char in payload:
        value ^= ord(char)
    try:
        return value == int(checksum[:2], 16)
    except ValueError:
        return False


def nmea_degrees(value, hemisphere):
    if not value:
        return math.nan
    raw = float(value)
    degrees = int(raw // 100)
    decimal = degrees + (raw - degrees * 100) / 60.0
    return -decimal if hemisphere in ("S", "W") else decimal


class CellularTelemetry(Node):
    def __init__(self):
        super().__init__("cellular_telemetry")
        try:
            self.power = HatPowerMonitor()
        except Exception as error:
            self.power = None
            self.power_error = str(error)
            self.get_logger().warn(f"HAT power monitor disabled: {error}")
        else:
            self.power_error = ""
        self.nmea_fd = None
        self.nmea_buffer = bytearray()
        self.next_nmea_open = 0.0

        self.pub_connected = self.create_publisher(Bool, "/cellular/connected", 10)
        self.pub_signal = self.create_publisher(Float32, "/cellular/signal_percent", 10)
        self.pub_tech = self.create_publisher(String, "/cellular/access_tech", 10)
        self.pub_operator = self.create_publisher(String, "/cellular/operator", 10)
        self.pub_registration = self.create_publisher(
            String, "/cellular/registration", 10
        )
        self.pub_hat_voltage = self.create_publisher(
            Float32, "/cellular/hat_voltage", 10
        )
        self.pub_hat_current = self.create_publisher(
            Float32, "/cellular/hat_current", 10
        )
        self.pub_hat_power = self.create_publisher(
            Float32, "/cellular/hat_power", 10
        )
        self.pub_hat_status = self.create_publisher(String, "/cellular/hat_status", 10)
        self.pub_nmea = self.create_publisher(String, "/gps/nmea", 10)
        self.pub_fix = self.create_publisher(NavSatFix, "/gps/fix", 10)
        self.pub_satellites = self.create_publisher(Float32, "/gps/satellites", 10)
        self.pub_hdop = self.create_publisher(Float32, "/gps/hdop", 10)
        self.pub_constellations = self.create_publisher(String, "/gps/constellations", 10)
        self.constellation_counts = {"GPS": 0, "GLONASS": 0, "GALILEO": 0, "BEIDOU": 0, "NAVIC": 0}

        self.create_timer(1.0, self.read_power)
        self.create_timer(0.1, self.read_nmea)
        threading.Thread(target=self.modem_loop, daemon=True).start()
        self.get_logger().info("SIM8230 and 5G HAT telemetry ready")

    def modem_loop(self):
        while rclpy.ok():
            self.read_modem()
            time.sleep(5.0)

    def read_power(self):
        if self.power is None:
            try:
                self.power = HatPowerMonitor()
                self.power_error = ""
            except Exception as error:
                self.power_error = str(error)
                self.pub_hat_voltage.publish(Float32(data=0.0))
                self.pub_hat_current.publish(Float32(data=0.0))
                self.pub_hat_power.publish(Float32(data=0.0))
                self.pub_hat_status.publish(String(data=f"INA219_OFFLINE addr=0x40 error={error}"))
                return
        try:
            voltage, current, power = self.power.read()
            self.pub_hat_voltage.publish(Float32(data=float(voltage)))
            self.pub_hat_current.publish(Float32(data=float(current)))
            self.pub_hat_power.publish(Float32(data=float(power)))
            self.pub_hat_status.publish(String(data=f"INA219_OK addr=0x40 voltage={voltage:.2f}V current={current:.3f}A power={power:.2f}W"))
        except Exception as error:
            self.get_logger().warn(f"INA219 read failed: {error}")
            self.power_error = str(error)
            self.pub_hat_status.publish(String(data=f"INA219_OFFLINE addr=0x40 error={error}"))
            try:
                self.power.close()
            except Exception:
                pass
            self.power = None
    def read_modem(self):
        try:
            output = subprocess.run(
                ["mmcli", "-m", "any", "-K"],
                check=True,
                capture_output=True,
                text=True,
                timeout=4,
            ).stdout
            data = parse_key_values(output)
        except (OSError, subprocess.SubprocessError) as error:
            self.pub_connected.publish(Bool(data=False))
            self.get_logger().warn(f"Modem status unavailable: {error}")
            return

        state = data.get("modem.generic.state", "unknown")
        signal = float(data.get("modem.generic.signal-quality.value", "0"))
        tech = data.get("modem.generic.access-technologies.value[1]", "unknown")
        operator = data.get("modem.3gpp.operator-name", "unknown")
        registration = data.get("modem.3gpp.registration-state", "unknown")
        self.pub_connected.publish(Bool(data=state == "connected"))
        self.pub_signal.publish(Float32(data=signal))
        self.pub_tech.publish(String(data=tech))
        self.pub_operator.publish(String(data=operator))
        self.pub_registration.publish(String(data=registration))

    def open_nmea(self):
        now = time.monotonic()
        if self.nmea_fd is not None or now < self.next_nmea_open:
            return
        try:
            self.nmea_fd = os.open(
                NMEA_PORT, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK
            )
            attrs = termios.tcgetattr(self.nmea_fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
            attrs[3] = 0
            attrs[4] = termios.B9600
            attrs[5] = termios.B9600
            termios.tcsetattr(self.nmea_fd, termios.TCSANOW, attrs)
            self.get_logger().info(f"GNSS NMEA open on {NMEA_PORT}")
        except OSError:
            self.next_nmea_open = now + 2.0

    def close_nmea(self):
        if self.nmea_fd is not None:
            os.close(self.nmea_fd)
            self.nmea_fd = None
        self.nmea_buffer.clear()
        self.next_nmea_open = time.monotonic() + 2.0

    def read_nmea(self):
        self.open_nmea()
        if self.nmea_fd is None:
            return
        try:
            chunk = os.read(self.nmea_fd, 4096)
        except BlockingIOError:
            return
        except OSError:
            self.close_nmea()
            return
        if not chunk:
            return

        self.nmea_buffer.extend(chunk)
        while b"\n" in self.nmea_buffer:
            raw, _, remaining = self.nmea_buffer.partition(b"\n")
            self.nmea_buffer = bytearray(remaining)
            sentence = raw.decode("ascii", errors="ignore").strip()
            if not nmea_checksum_valid(sentence):
                continue
            self.pub_nmea.publish(String(data=sentence))
            msg_type = sentence[3:6]
            if msg_type == "GGA":
                self.publish_gga(sentence)
            elif msg_type == "GSV":
                self.publish_gsv(sentence)

    def publish_gsv(self, sentence):
        fields = sentence.split("*")[0].split(",")
        if len(fields) < 4:
            return
        talker = sentence[1:3]
        name = {
            "GP": "GPS",
            "GL": "GLONASS",
            "GA": "GALILEO",
            "GB": "BEIDOU",
            "BD": "BEIDOU",
            "QZ": "QZSS",
            "GI": "NAVIC",
            "IR": "NAVIC",
        }.get(talker)
        if name is None:
            return
        try:
            count = int(fields[3] or "0")
        except ValueError:
            return
        self.constellation_counts[name] = count
        order = ("GPS", "GLONASS", "GALILEO", "BEIDOU", "QZSS", "NAVIC")
        payload = "|".join(f"{key}:{self.constellation_counts.get(key, 0)}" for key in order)
        self.pub_constellations.publish(String(data=payload))
    def publish_gga(self, sentence):
        fields = sentence.split("*")[0].split(",")
        if len(fields) < 10:
            return
        try:
            quality = int(fields[6] or "0")
            satellites = int(fields[7] or "0")
            hdop = float(fields[8]) if fields[8] else math.nan
            altitude = float(fields[9]) if fields[9] else math.nan
            latitude = nmea_degrees(fields[2], fields[3])
            longitude = nmea_degrees(fields[4], fields[5])
        except ValueError:
            return

        self.pub_satellites.publish(Float32(data=float(satellites)))
        self.pub_hdop.publish(Float32(data=float(hdop)))

        fix = NavSatFix()
        fix.header.stamp = self.get_clock().now().to_msg()
        fix.header.frame_id = "gps_link"
        fix.status.status = (
            NavSatStatus.STATUS_FIX if quality > 0 else NavSatStatus.STATUS_NO_FIX
        )
        fix.status.service = (
            NavSatStatus.SERVICE_GPS
            | NavSatStatus.SERVICE_GLONASS
            | NavSatStatus.SERVICE_COMPASS
            | NavSatStatus.SERVICE_GALILEO
        )
        fix.latitude = latitude
        fix.longitude = longitude
        fix.altitude = altitude
        if quality > 0 and math.isfinite(hdop):
            variance = (hdop * 5.0) ** 2
            fix.position_covariance[0] = variance
            fix.position_covariance[4] = variance
            fix.position_covariance[8] = variance * 4.0
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_APPROXIMATED
        else:
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.pub_fix.publish(fix)


def main():
    rclpy.init()
    node = CellularTelemetry()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close_nmea()
        if node.power is not None:
            node.power.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
