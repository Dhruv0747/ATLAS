#!/usr/bin/env python3
"""Read-only primary SIM8230G USB GNSS with explicit freshness diagnostics."""

import json
import math
import os
import termios
import time

import pynmea2
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import Float32, String


DEFAULT_PORT = '/dev/serial/by-id/usb-SIMCOM_SDXBAAGHA-IDP__SN:7F8831D6_0123456789ABCDEF-if03-port0'
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
    """Open NMEA read-only; do not issue AT commands or reset the modem."""
    if baud not in BAUD_CONSTANTS:
        raise ValueError(f'unsupported baud rate: {baud}')
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[3] = 0
        attrs[4] = BAUD_CONSTANTS[baud]
        attrs[5] = BAUD_CONSTANTS[baud]
        attrs[6][termios.VMIN] = 1
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIFLUSH)
    except Exception:
        os.close(fd)
        raise
    return fd


class GnssNode(Node):
    def __init__(self):
        super().__init__('atlas_gnss_node')
        self.declare_parameter('port', DEFAULT_PORT)
        self.declare_parameter('baud', DEFAULT_BAUD)
        self.declare_parameter('frame_id', 'gps_link')
        self.declare_parameter('poll_hz', 20.0)
        self.declare_parameter('source_name', 'SIM8230G USB GNSS')
        self.source_name = str(self.get_parameter('source_name').value)

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
        self.diagnostics_pub = self.create_publisher(String, '/gps/diagnostics', 10)

        self.fd = None
        self.buffer = b''
        self.bytes_total = 0
        self.valid_lines = 0
        self.last_byte = 0.0
        self.last_nmea = 0.0
        self.last_fix = 0.0
        self.last_gga = 0.0
        self.last_combined_gga = 0.0
        self.fix_valid = False
        self.satellites_used = 0
        self.hdop = math.nan
        self.invalid_lines = 0
        self.open_count = 0
        self.opened_at = 0.0
        self.last_error = ''
        self.last_sentence = ''
        self.talker_times = {}
        self.constellation_times = {}
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
            f'{self.source_name} node started on {self.port} at {self.baud} baud')

    def _open_port(self):
        now = time.monotonic()
        if now - self.last_open_attempt < 2.0:
            return
        self.last_open_attempt = now
        self._close_port()
        try:
            self.fd = open_raw_serial(self.port, self.baud)
            self.opened_at = now
            self.open_count += 1
        except (OSError, ValueError) as exc:
            self.get_logger().warning(f'GNSS UART open failed: {exc}')
            self.last_error = str(exc)
            self.fd = None

    def _close_port(self, publish_invalid=True):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None
        self.buffer = b''
        self.last_byte = self.last_nmea = self.last_fix = self.last_gga = 0.0
        self.last_combined_gga = 0.0
        self.talkers.clear()
        self.talker_times.clear()
        self.constellation_times.clear()
        if publish_invalid:
            self._invalidate_fix()

    def _invalidate_fix(self):
        self.fix_valid = False
        self.satellites_used = 0
        self.hdop = math.nan
        fix = NavSatFix()
        fix.header.stamp = self.get_clock().now().to_msg()
        fix.header.frame_id = self.frame_id
        fix.status.status = NavSatStatus.STATUS_NO_FIX
        fix.latitude = fix.longitude = fix.altitude = math.nan
        self.fix_pub.publish(fix)
        self.sat_pub.publish(Float32(data=0.0))
        self.hdop_pub.publish(Float32(data=math.nan))

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
            self.last_error = str(exc)
            self._close_port()
            return
        if not chunk:
            self.last_error = 'NMEA device EOF (USB disconnected); reopening stable by-id path'
            self._close_port()
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
        now = time.monotonic()
        fields = [f'{name}:{self.constellation_counts[name] if now - self.constellation_times.get(name, 0) < 6 else 0}' for name in order]
        fields.append('TALKERS:' + ','.join(sorted(k for k, t in self.talker_times.items() if now - t < 6)))
        self.const_pub.publish(String(data='|'.join(fields)))

    def _handle_line(self, line):
        try:
            msg = pynmea2.parse(line, check=True)
        except (pynmea2.ParseError, ValueError):
            self.invalid_lines += 1
            return
        self.valid_lines += 1
        self.last_nmea = time.monotonic()
        self.last_sentence = line
        self.nmea_pub.publish(String(data=line))
        talker = line[1:3].upper() if len(line) >= 6 else ''
        if talker:
            self.talkers.add(talker)
            self.talker_times[talker] = self.last_nmea

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
                self.constellation_counts[name] = max(0, count)
                self.constellation_times[name] = self.last_nmea
            return

        if not isinstance(msg, pynmea2.types.talker.GGA):
            return

        # A combined GN solution is authoritative. Per-constellation GGA
        # sentences in the same burst must not overwrite its used-satellite count.
        if talker == 'GN':
            self.last_combined_gga = self.last_nmea
        elif self.last_combined_gga and self.last_nmea - self.last_combined_gga < 3:
            return
        self.last_gga = self.last_nmea

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
        self.hdop_pub.publish(Float32(data=hdop))
        self.satellites_used = satellites
        self.hdop = hdop

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
        try:
            fix.latitude = float(msg.latitude) if msg.lat and quality > 0 else math.nan
            fix.longitude = float(msg.longitude) if msg.lon and quality > 0 else math.nan
        except (ValueError, TypeError):
            fix.latitude = fix.longitude = math.nan
        self.fix_valid = quality > 0 and math.isfinite(fix.latitude) and math.isfinite(fix.longitude)
        if not self.fix_valid:
            fix.status.status = NavSatStatus.STATUS_NO_FIX
        try:
            fix.altitude = float(msg.altitude) if msg.altitude else math.nan
        except (TypeError, ValueError):
            fix.altitude = math.nan
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.fix_pub.publish(fix)
        if self.fix_valid:
            self.last_fix = time.monotonic()
        else:
            self.last_fix = 0.0

    def _publish_status(self):
        now = time.monotonic()
        if self.fd is not None:
            try:
                current = os.stat(self.port)
                opened = os.fstat(self.fd)
                rebound = (current.st_rdev, current.st_ino) != (opened.st_rdev, opened.st_ino)
            except OSError:
                rebound = True
            if rebound or now - (self.last_byte or self.opened_at) > 8:
                self.last_error = 'USB path changed' if rebound else 'No NMEA bytes for 8 seconds'
                self._close_port()
        if self.last_gga and now - self.last_gga > 3:
            self._invalidate_fix()
        if self.fd is None:
            state = 'PORT_OFFLINE'
            action = 'CHECK_GNSS_USB_DRIVER_AND_NMEA_PORT'
        elif not self.last_byte or now - self.last_byte > 3.0:
            state = 'NO_UART_BYTES'
            action = 'CHECK_GNSS_POWER_AND_NMEA_OUTPUT'
        elif not self.last_nmea or now - self.last_nmea > 3.0:
            state = 'UART_BYTES_NO_VALID_NMEA'
            action = 'CHECK_GNSS_NMEA_PORT_AND_PROTOCOL'
        elif not self.fix_valid or not self.last_fix or now - self.last_fix > 3.0:
            state = 'NMEA_LIVE_NO_FIX'
            action = 'MOVE_ANTENNA_UNDER_OPEN_SKY'
        else:
            state = 'FIXED'
            action = 'NONE'
        self.status_pub.publish(String(data=(
            f'{self.source_name} {state} port={self.port} baud={self.baud} '
            f'bytes_total={self.bytes_total} valid_nmea={self.valid_lines} '
            f'action={action}'
        )))
        age = lambda stamp: round(now - stamp, 2) if stamp else None
        diagnostics = {
            'schema': 1, 'source': self.source_name, 'state': state,
            'port': self.port, 'resolved_port': os.path.realpath(self.port),
            'transport_open': self.fd is not None, 'baud': self.baud,
            'byte_age_s': age(self.last_byte), 'nmea_age_s': age(self.last_nmea),
            'gga_age_s': age(self.last_gga), 'fix_valid': state == 'FIXED',
            'satellites_used': self.satellites_used if self.last_gga and now - self.last_gga < 3 else None,
            'hdop': self.hdop if math.isfinite(self.hdop) else None,
            'bytes_total': self.bytes_total, 'valid_nmea': self.valid_lines,
            'invalid_nmea': self.invalid_lines, 'reconnects': max(0, self.open_count - 1),
            'last_transport_error': self.last_error, 'action': action,
            'last_sentence': self.last_sentence if self.last_nmea and now - self.last_nmea < 3 else '',
            'talkers': sorted(k for k, t in self.talker_times.items() if now - t < 6),
            'constellations': {name: {
                'in_view': count if name in self.constellation_times and now - self.constellation_times[name] < 6 else None,
                'age_s': age(self.constellation_times.get(name, 0)),
            } for name, count in self.constellation_counts.items()},
            'note': 'GSV counts are receiver-reported in-view counts, not antenna proof or fix counts. Talker labels alone do not prove satellite reception.',
        }
        self.diagnostics_pub.publish(String(data=json.dumps(diagnostics, allow_nan=False)))
        self._publish_constellations()

    def destroy_node(self):
        # systemd SIGTERM can shut down the ROS context before this cleanup.
        self._close_port(publish_invalid=False)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GnssNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
