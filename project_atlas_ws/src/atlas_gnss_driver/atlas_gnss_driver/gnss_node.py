#!/usr/bin/env python3
"""
GNSS driver for SIMCOM SIM8230G on Project ATLAS.

Reads raw NMEA sentences from /dev/ttyUSB2 (the modem's dedicated GNSS port,
NOT the AT/data ports at ttyUSB1/ttyUSB3 which are owned by ModemManager).

Uses a raw os.open()/termios read instead of pyserial, because pyserial's
Serial.open() asserts DTR/RTS by default (dtr=True) via a TIOCMSET ioctl,
and this port rejects that ioctl. CLOCAL+CREAD via termios avoids touching
modem control lines entirely, which is all this port supports.
"""
import os
import termios
import time

import pynmea2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus


DEFAULT_PORT = '/dev/ttyUSB2'


def open_raw_serial(path):
    """Open a serial port for read-only access without asserting DTR/RTS."""
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[2] |= termios.CLOCAL | termios.CREAD
    attrs[2] &= ~termios.HUPCL  # do not toggle DTR on close
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


class GnssNode(Node):
    def __init__(self):
        super().__init__('atlas_gnss_node')

        self.declare_parameter('port', DEFAULT_PORT)
        self.declare_parameter('frame_id', 'gnss_link')
        self.declare_parameter('poll_hz', 5.0)

        self.port = self.get_parameter('port').value
        self.frame_id = self.get_parameter('frame_id').value
        poll_hz = self.get_parameter('poll_hz').value

        self.pub = self.create_publisher(NavSatFix, '/gps/fix', 10)

        self.fd = None
        self._buf = b''
        self._open_port()

        self.timer = self.create_timer(1.0 / poll_hz, self._poll)
        self.get_logger().info(f'GNSS node started on {self.port}')

    def _open_port(self):
        try:
            if self.fd is not None:
                os.close(self.fd)
        except OSError:
            pass
        try:
            self.fd = open_raw_serial(self.port)
        except OSError as e:
            self.get_logger().error(f'Failed to open {self.port}: {e}')
            self.fd = None

    def _poll(self):
        if self.fd is None:
            self._open_port()
            return

        try:
            chunk = os.read(self.fd, 4096)
            self._buf += chunk
        except BlockingIOError:
            chunk = b''
        except OSError as e:
            self.get_logger().warn(f'Serial read error, reopening: {e}')
            self._open_port()
            return

        while b'\n' in self._buf:
            line, self._buf = self._buf.split(b'\n', 1)
            line = line.decode('ascii', errors='ignore').strip()
            if not line.startswith('$'):
                continue
            self._handle_line(line)

    def _handle_line(self, line):
        try:
            msg = pynmea2.parse(line)
        except pynmea2.ParseError:
            return

        # GGA carries fix quality, lat/lon, altitude, satellite count.
        if isinstance(msg, pynmea2.types.talker.GGA):
            fix = NavSatFix()
            fix.header.stamp = self.get_clock().now().to_msg()
            fix.header.frame_id = self.frame_id

            quality = int(msg.gps_qual) if msg.gps_qual not in (None, '') else 0
            if quality == 0:
                fix.status.status = NavSatStatus.STATUS_NO_FIX
            else:
                fix.status.status = NavSatStatus.STATUS_FIX
            fix.status.service = NavSatStatus.SERVICE_GPS

            if msg.latitude and msg.longitude:
                fix.latitude = msg.latitude
                fix.longitude = msg.longitude
            else:
                fix.latitude = float('nan')
                fix.longitude = float('nan')

            try:
                fix.altitude = float(msg.altitude) if msg.altitude else float('nan')
            except (TypeError, ValueError):
                fix.altitude = float('nan')

            # No covariance data available from this NMEA stream yet.
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN

            self.pub.publish(fix)

            if quality == 0:
                self.get_logger().debug(
                    'GGA received, no fix (quality=0) — check GNSS antenna placement'
                )

    def destroy_node(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
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
        rclpy.shutdown()


if __name__ == '__main__':
    main()
