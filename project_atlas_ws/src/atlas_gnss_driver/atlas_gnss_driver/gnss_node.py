#!/usr/bin/env python3
"""Project ATLAS L76K NMEA driver for the Jetson J12 UART."""

import math
import os
import termios
import time

import pynmea2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import Float32, String


DEFAULT_PORT = '/dev/ttyTHS1'
DEFAULT_BAUD = 9600
BAUD_CONSTANTS = {
    4800: termios.B4800,
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}


def open_raw_serial(path, baud):
    """Open a 3.3-V TTL UART read-only without modem-control side effects."""
    if baud not in BAUD_CONSTANTS:
        raise ValueError(f'unsupported baud rate: {baud}')
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[3] = 0
    attrs[4] = BAUD_CONSTANTS[baud]
    attrs[5] = BAUD_CONSTANTS[baud]
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIFLUSH)
    return fd


class GnssNode(Node):
    def __init__(self):
        super().__init__('atlas_gnss_node')
        self.declare_parameter('port', DEFAULT_PORT)
        self.declare_parameter('baud', DEFAULT_BAUD)
        self.declare_parameter('frame_id', 'gps_link')
        self.declare_parameter('poll_hz', 20.0)

        self.port = str(self.get_parameter('port').value)
        self.baud = int(self.get_parameter('baud').value)
        self.frame_id = str(self.get_parameter('frame_id').value)
        poll_hz = float(self.get_parameter('poll_hz').value)

        self.fix_pub = self.create_publisher(NavSatFix, '/gps/fix', 10)
        self.sat_pub = self.create_publisher(Float32, '/gps/satellites', 10)
        self.hdop_pub = self.create_publisher(Float32, '/gps/hdop', 10)
        self.nmea_pub = self.create_publisher(String, '/gps/nmea', 10)
        self.const_pub = self.create_publisher(String, '/gps/constellations', 10)
        self.status_pub = self.create_publisher(String, '/gps/receiver_status', 10)

        self.fd = None
        self.buffer = b''
        self.bytes_total = 0
        self.valid_lines = 0
        self.last_byte = 0.0
        self.last_nmea = 0.0
        self.last_fix = 0.0
        self.last_open_attempt = 0.0
        self.talkers = set()
        self.constellation_counts = {
            'GPS': 0, 'GLONASS': 0, 'BEIDOU': 0,
            'GALILEO': 0, 'QZSS': 0, 'NAVIC': 0,
        }

        self._open_port()
        self.create_timer(1.0 / max(1.0, poll_hz), self._poll)
        self.create_timer(1.0, self._publish_status)
        self.get_logger().info(
            f'L76K GNSS node started on {self.port} at {self.baud} baud')

    def _open_port(self):
        now = time.monotonic()
        if now - self.last_open_attempt < 2.0:
            return
        self.last_open_attempt = now
        self._close_port()
        try:
            self.fd = open_raw_serial(self.port, self.baud)
        except (OSError, ValueError) as exc:
            self.get_logger().warning(f'GNSS UART open failed: {exc}')
            self.fd = None

    def _close_port(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None

    def _poll(self):
        if self.fd is None:
            self._open_port()
            return
        try:
            chunk = os.read(self.fd, 4096)
        except BlockingIOError:
            return
        except OSError as exc:
            self.get_logger().warning(f'GNSS UART read failed, reopening: {exc}')
            self._close_port()
            return
        if not chunk:
            return
        self.bytes_total += len(chunk)
        self.last_byte = time.monotonic()
        self.buffer += chunk
        if len(self.buffer) > 32768:
            self.buffer = self.buffer[-4096:]
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            text = line.decode('ascii', errors='ignore').strip()
            if text.startswith('$'):
                self._handle_line(text)

    def _publish_constellations(self):
        order = ('GPS', 'GLONASS', 'BEIDOU', 'GALILEO', 'QZSS', 'NAVIC')
        fields = [f'{name}:{self.constellation_counts[name]}' for name in order]
        fields.append('TALKERS:' + ','.join(sorted(self.talkers)))
        self.const_pub.publish(String(data='|'.join(fields)))

    def _handle_line(self, line):
        try:
            msg = pynmea2.parse(line, check=True)
        except (pynmea2.ParseError, ValueError):
            return
        self.valid_lines += 1
        self.last_nmea = time.monotonic()
        self.nmea_pub.publish(String(data=line))
        talker = line[1:3].upper() if len(line) >= 6 else ''
        if talker:
            self.talkers.add(talker)

        if isinstance(msg, pynmea2.types.talker.GSV):
            name = {
                'GP': 'GPS', 'GL': 'GLONASS', 'BD': 'BEIDOU',
                'GB': 'BEIDOU', 'GA': 'GALILEO', 'GQ': 'QZSS',
                'QZ': 'QZSS', 'GI': 'NAVIC', 'IR': 'NAVIC',
            }.get(talker)
            try:
                count = int(msg.num_sv_in_view or 0)
            except (TypeError, ValueError):
                count = 0
            if name:
                self.constellation_counts[name] = count
            self._publish_constellations()
            return

        if not isinstance(msg, pynmea2.types.talker.GGA):
            self._publish_constellations()
            return

        try:
            quality = int(msg.gps_qual or 0)
        except (TypeError, ValueError):
            quality = 0
        try:
            satellites = int(msg.num_sats or 0)
        except (TypeError, ValueError):
            satellites = 0
        try:
            hdop = float(msg.horizontal_dil or math.nan)
        except (TypeError, ValueError):
            hdop = math.nan

        self.sat_pub.publish(Float32(data=float(satellites)))
        if math.isfinite(hdop):
            self.hdop_pub.publish(Float32(data=hdop))

        fix = NavSatFix()
        fix.header.stamp = self.get_clock().now().to_msg()
        fix.header.frame_id = self.frame_id
        fix.status.status = (NavSatStatus.STATUS_FIX if quality > 0
                             else NavSatStatus.STATUS_NO_FIX)
        service = 0
        for code in self.talkers:
            if code in ('GP', 'GN'):
                service |= NavSatStatus.SERVICE_GPS
            elif code == 'GL':
                service |= NavSatStatus.SERVICE_GLONASS
            elif code == 'GA':
                service |= NavSatStatus.SERVICE_GALILEO
            elif code in ('BD', 'GB'):
                service |= NavSatStatus.SERVICE_COMPASS
        fix.status.service = service or NavSatStatus.SERVICE_GPS
        fix.latitude = float(msg.latitude) if msg.latitude else math.nan
        fix.longitude = float(msg.longitude) if msg.longitude else math.nan
        try:
            fix.altitude = float(msg.altitude) if msg.altitude else math.nan
        except (TypeError, ValueError):
            fix.altitude = math.nan
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.fix_pub.publish(fix)
        if quality > 0:
            self.last_fix = time.monotonic()
        self._publish_constellations()

    def _publish_status(self):
        now = time.monotonic()
        if self.fd is None:
            state = 'PORT_OFFLINE'
            action = 'CHECK_TTYTHS1_AND_SERVICE'
        elif not self.last_byte or now - self.last_byte > 3.0:
            state = 'NO_UART_BYTES'
            action = 'CHECK_5V_GND_AND_GPS_TX_TO_JETSON_PIN10_RX'
        elif not self.last_nmea or now - self.last_nmea > 3.0:
            state = 'UART_BYTES_NO_VALID_NMEA'
            action = 'CHECK_9600_8N1_AND_SIGNAL_LEVEL'
        elif not self.last_fix or now - self.last_fix > 5.0:
            state = 'NMEA_LIVE_NO_FIX'
            action = 'MOVE_ANTENNA_UNDER_OPEN_SKY'
        else:
            state = 'FIXED'
            action = 'NONE'
        self.status_pub.publish(String(data=(
            f'JETSON_UART_GPS_{state} port={self.port} baud={self.baud} '
            f'bytes_total={self.bytes_total} valid_nmea={self.valid_lines} '
            f'action={action}'
        )))

    def destroy_node(self):
        self._close_port()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GnssNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
