#!/usr/bin/env python3
import re
import time
import os
import glob
import math
import json
import socket

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Float32, String, Int32
from sensor_msgs.msg import NavSatFix, NavSatStatus

try:
    import serial
except Exception as exc:
    serial = None
    SERIAL_IMPORT_ERROR = exc
else:
    SERIAL_IMPORT_ERROR = None

PORT = os.environ.get(
    'ATLAS_SENSOR_HUB_PORT',
    '/dev/serial/by-id/usb-Arduino_UNO_R4_WiFi_3718211158323232840133334B573038-if00',
).strip()
PORT_FALLBACK_PATTERNS = (
    '/dev/atlas-sensor-hub',
    '/dev/serial/by-id/usb-Arduino_UNO_R4_WiFi_*-if00',
    '/dev/serial/by-id/usb-Arduino_UNO_WiFi_R4_CMSIS-DAP_*-if01',
    '/dev/ttyACM*',
)
BAUD = 115200
SERIAL_STALE_REOPEN_SECONDS = max(
    5.0, float(os.environ.get('ATLAS_SENSOR_HUB_STALE_REOPEN_SECONDS', '8.0'))
)
HUB_TRANSPORT = os.environ.get('ATLAS_SENSOR_HUB_TRANSPORT', 'arduino_uno_r4').strip()
NICLA_PRIMARY = os.environ.get('ATLAS_NICLA_PRIMARY', '0').strip().lower() in (
    '1', 'true', 'yes', 'on',
)
GNSS_ENABLED = os.environ.get('ATLAS_GNSS_ENABLED', '1').strip().lower() not in (
    '0', 'false', 'no', 'off',
)
CAMERA_ROUTE = os.environ.get('ATLAS_CAMERA_ROUTE', 'jetson').strip().lower()
CAMERA_SOCKET_PATH = os.environ.get(
    'ATLAS_SENSOR_HUB_CAMERA_SOCKET',
    '/run/user/1000/atlas-sensor-hub-camera.sock',
).strip()
DASHBOARD_SNAPSHOT_PATH = os.environ.get(
    'ATLAS_SENSOR_HUB_STATUS_PATH',
    '/run/user/1000/atlas-sensor-hub-status.json',
).strip()
LINE_RE = re.compile(
    r'F=(?P<front>-?\d+),L=(?P<left>-?\d+),R=(?P<right>-?\d+)'
    r'(?:,B=(?P<rear>-?\d+))?'
    r'(?:,LA=(?P<la>-?\d+),RA=(?P<ra>-?\d+),C1=(?P<c1>-?\d+),'
    r'C2=(?P<c2>-?\d+),PCA=(?P<pca>\d+))?,OK=(?P<ok>\d+)'
)


class UltrasonicArduinoBridge(Node):
    def __init__(self):
        super().__init__('ultrasonic_arduino_bridge')
        self.front_pub = self.create_publisher(Float32, '/ultrasonic/front_mm', 10)
        self.left_pub = self.create_publisher(Float32, '/ultrasonic/left_mm', 10)
        self.right_pub = self.create_publisher(Float32, '/ultrasonic/right_mm', 10)
        self.rear_pub = self.create_publisher(Float32, '/ultrasonic/rear_mm', 10)
        self.status_pub = self.create_publisher(String, '/ultrasonic/status', 10)
        self.pca_status_pub = self.create_publisher(String, '/arduino/pca9685/status', 10)
        self.left_servo_pub = self.create_publisher(Int32, '/ultrasonic/left_servo_us', 10)
        self.right_servo_pub = self.create_publisher(Int32, '/ultrasonic/right_servo_us', 10)
        self.camera_bottom_pub = self.create_publisher(Int32, '/camera/bottom_servo_us', 10)
        self.camera_second_pub = self.create_publisher(Int32, '/camera/second_servo_us', 10)
        self.camera_status_pub = self.create_publisher(String, '/camera/arducam/status', 10)
        self.i2c_status_pub = self.create_publisher(String, '/arduino/i2c/status', 10)
        self.outside_temp_pub = self.create_publisher(Float32, '/environment/outside_temperature_c', 10)
        self.outside_humidity_pub = self.create_publisher(Float32, '/environment/outside_humidity_pct', 10)
        self.pressure_pub = self.create_publisher(Float32, '/environment/pressure_hpa', 10)
        self.gas_pub = self.create_publisher(Float32, '/environment/gas_resistance_ohm', 10)
        self.iaq_pub = self.create_publisher(Float32, '/environment/iaq', 10)
        self.eco2_pub = self.create_publisher(Float32, '/environment/eco2_ppm', 10)
        self.environment_status_pub = self.create_publisher(String, '/environment/outside_status', 10)
        self.environment_json_pub = self.create_publisher(String, '/environment/bme680/json', 10)
        self.nicla_temp_pub = self.create_publisher(Float32, '/environment/nicla/temperature_c', 10)
        self.nicla_humidity_pub = self.create_publisher(Float32, '/environment/nicla/humidity_pct', 10)
        self.nicla_indoor_iaq_pub = self.create_publisher(Float32, '/environment/nicla/indoor_iaq', 10)
        self.nicla_relative_iaq_pub = self.create_publisher(Float32, '/environment/nicla/relative_iaq_pct', 10)
        self.nicla_eco2_pub = self.create_publisher(Float32, '/environment/nicla/eco2_ppm', 10)
        self.nicla_tvoc_pub = self.create_publisher(Float32, '/environment/nicla/tvoc_mg_m3', 10)
        self.nicla_ethanol_pub = self.create_publisher(Float32, '/environment/nicla/ethanol_ppm', 10)
        self.nicla_outdoor_aqi_pub = self.create_publisher(Float32, '/environment/nicla/outdoor_aqi', 10)
        self.nicla_fast_aqi_pub = self.create_publisher(Float32, '/environment/nicla/outdoor_fast_aqi', 10)
        self.nicla_no2_pub = self.create_publisher(Float32, '/environment/nicla/no2_ppb', 10)
        self.nicla_o3_pub = self.create_publisher(Float32, '/environment/nicla/o3_ppb', 10)
        self.nicla_status_pub = self.create_publisher(String, '/environment/nicla/status', 10)
        self.nicla_json_pub = self.create_publisher(String, '/environment/nicla/json', 10)
        self.radar_raw_pub = self.create_publisher(String, '/radar/hub/raw_hex', 10)
        self.radar_status_pub = self.create_publisher(String, '/radar/hub/status', 10)
        self.thermal_json_pub = self.create_publisher(String, '/thermal/amg8833/json', 10)
        self.thermal_status_pub = self.create_publisher(String, '/thermal/amg8833/status', 10)
        self.thermal_min_pub = self.create_publisher(Float32, '/thermal/amg8833/min_c', 10)
        self.thermal_max_pub = self.create_publisher(Float32, '/thermal/amg8833/max_c', 10)
        self.thermal_avg_pub = self.create_publisher(Float32, '/thermal/amg8833/avg_c', 10)
        self.thermal_center_pub = self.create_publisher(Float32, '/thermal/amg8833/center_c', 10)
        self.gnss_enabled = GNSS_ENABLED
        if self.gnss_enabled:
            self.gps_fix_pub = self.create_publisher(NavSatFix, '/gps/fix', 10)
            self.gps_satellites_pub = self.create_publisher(Float32, '/gps/satellites', 10)
            self.gps_hdop_pub = self.create_publisher(Float32, '/gps/hdop', 10)
            self.gps_nmea_pub = self.create_publisher(String, '/gps/nmea', 10)
            self.gps_constellations_pub = self.create_publisher(String, '/gps/constellations', 10)
            self.gps_status_pub = self.create_publisher(String, '/gps/arduino_status', 10)
        self.create_subscription(Int32, '/arduino/pca9685/servo_us', self.servo_cmd_cb, 10)
        self.create_subscription(Int32, '/ultrasonic/left_servo_cmd_us', lambda m: self.send_servo(0, m.data), 10)
        self.camera_via_arduino = CAMERA_ROUTE in ('arduino', 'uno_r4')
        if self.camera_via_arduino:
            # The commissioned UNO R4 hub uses channels 0/1. Retain channels
            # 1/2 only for the legacy UNO image.
            commissioned_hub = HUB_TRANSPORT == 'uno_r4_i2c_hub'
            self.camera_pan_channel = 0 if commissioned_hub else 1
            self.camera_tilt_channel = 1 if commissioned_hub else 2
            self.create_subscription(
                Int32, '/camera/bottom_servo_cmd_us',
                lambda m: self.send_servo(self.camera_pan_channel, m.data), 10)
            self.create_subscription(
                Int32, '/camera/second_servo_cmd_us',
                lambda m: self.send_servo(self.camera_tilt_channel, m.data), 10)
        self.create_subscription(Int32, '/ultrasonic/right_servo_cmd_us', lambda m: self.send_servo(3, m.data), 10)
        self.ser = None
        self.camera_socket = None
        if self.camera_via_arduino:
            try:
                if os.path.exists(CAMERA_SOCKET_PATH):
                    os.unlink(CAMERA_SOCKET_PATH)
                self.camera_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                self.camera_socket.bind(CAMERA_SOCKET_PATH)
                os.chmod(CAMERA_SOCKET_PATH, 0o600)
                self.camera_socket.setblocking(False)
            except Exception as exc:
                self.camera_socket = None
                self.get_logger().error(f'camera command socket unavailable: {exc}')
        self.last_ok = 0.0
        self.last_serial_rx = 0.0
        self.last_wait_status = 0.0
        self.last_connect_log = 0.0
        self.radar_last_rx = 0.0
        self.radar_bytes_total = 0
        self.gps_hdop = math.nan
        self.gps_constellations = set()
        self.gps_constellation_counts = {
            'GPS': 0, 'GLONASS': 0, 'BEIDOU': 0,
            'GALILEO': 0, 'QZSS': 0, 'NAVIC': 0,
        }
        self.gas_baseline = None
        self.bme_started = time.time()
        # ROS discovery can briefly miss a publisher when the web dashboard
        # and this USB bridge restart together. Keep a tiny local snapshot as
        # a second, read-only dashboard transport. ROS topics remain the
        # authoritative control/robot interface.
        self.dashboard_cache = {}
        self.last_dashboard_cache_flush = 0.0
        self.last_dashboard_cache_error = 0.0
        self.create_timer(0.05, self.tick)
        if self.camera_via_arduino:
            camera_route = 'Arduino UNO R4 PCA9685'
        else:
            camera_route = 'Jetson i2c-7 / atlas_arducam_ptz'
        self.hub_transport = HUB_TRANSPORT or 'unknown_sensor_hub'
        self.active_port = ''
        self.get_logger().info(
            f'ATLAS sensor hub starting on {PORT}; transport: {self.hub_transport}; '
            f'camera route: {camera_route}')
        if not self.gnss_enabled:
            self.get_logger().info('Arduino GNSS forwarding disabled by ATLAS_GNSS_ENABLED=0')

    def connect(self):
        if serial is None:
            self.status_pub.publish(String(data=f'pyserial_missing {SERIAL_IMPORT_ERROR}'))
            return False
        try:
            resolved_port = self.resolve_port(PORT)
            if not resolved_port:
                self.status_pub.publish(String(data='connect_error sensor_hub_port_not_found'))
                return False
            # The UNO R4 native USB CDC endpoint requires DTR asserted in
            # order to emit Serial telemetry.
            self.ser = serial.Serial()
            self.ser.port = resolved_port
            self.ser.baudrate = BAUD
            self.ser.timeout = 0.02
            self.ser.write_timeout = 0.25
            self.ser.dtr = True
            self.ser.open()
            self.active_port = resolved_port
            # Apply the final modem-control state after open as well. Linux
            # cdc_acm may not propagate a pre-open DTR assignment to the UNO
            # R4 native USB endpoint on every enumeration.
            self.ser.setDTR(True)
            time.sleep(1.8)
            now = time.time()
            # Give a newly enumerated board a bounded startup grace period.
            # A native USB reset can leave an otherwise valid cdc_acm handle
            # returning empty reads forever, so tick() reopens it if no bytes
            # arrive before this deadline.
            self.last_ok = now
            self.last_serial_rx = now
            self.status_pub.publish(String(data=f'connected port={resolved_port}'))
            if HUB_TRANSPORT == 'uno_r4_i2c_hub':
                # Firmware setup already performs the authoritative scan and
                # bounded initialization. Do not launch a second recovery scan
                # during a USB reconnect; it can interrupt an in-flight sensor
                # transaction. Camera outputs remain released.
                self.write_line('PING')
                self.write_line('PCA?')
                # Radar UART is deliberately lazy in firmware so a faulty
                # peripheral cannot block I2C startup. Enable it only after
                # the native USB telemetry link is proven alive.
                self.write_line('RADARINIT')
            else:
                self.write_line('PCA?')
                self.write_line('SCAN')
                # The consolidated hub releases camera servo outputs during
                # boot/reconnect to prevent an unexpected movement or current
                # surge. Home only the legacy UNO firmware automatically.
                if HUB_TRANSPORT != 'uno_r4_i2c_hub':
                    self.write_line('HOME')
            return True
        except Exception as exc:
            try:
                if self.ser is not None:
                    self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.status_pub.publish(String(data=f'connect_error {exc}'))
            now = time.time()
            if now - self.last_connect_log >= 5.0:
                self.last_connect_log = now
                self.get_logger().warning(f'Sensor hub connect failed: {exc}')
            return False

    @staticmethod
    def resolve_port(configured_port):
        """Resolve the commissioned UNO across native-USB and boot/debug IDs."""
        if configured_port and os.path.exists(configured_port):
            return configured_port
        for pattern in PORT_FALLBACK_PATTERNS:
            for candidate in sorted(glob.glob(pattern)):
                if os.path.exists(candidate):
                    return candidate
        return ''

    @staticmethod
    def publish_mm(pub, value):
        pub.publish(Float32(data=float(value if value >= 0 else -1)))

    def write_line(self, line):
        if self.ser is None:
            return False
        try:
            self.ser.write((line.strip() + '\n').encode())
            return True
        except Exception as exc:
            self.status_pub.publish(String(data=f'write_error {exc}'))
            return False

    def dashboard_cache_set(self, key, value, timestamp=None):
        self.dashboard_cache[key] = {
            'value': value,
            'ts': float(timestamp if timestamp is not None else time.time()),
        }

    def flush_dashboard_cache(self, force=False):
        """Atomically expose sensor telemetry when DDS discovery is delayed."""
        if not DASHBOARD_SNAPSHOT_PATH:
            return
        now = time.monotonic()
        if not force and now - self.last_dashboard_cache_flush < 0.25:
            return
        self.last_dashboard_cache_flush = now
        temporary = f'{DASHBOARD_SNAPSHOT_PATH}.{os.getpid()}.tmp'
        try:
            parent = os.path.dirname(DASHBOARD_SNAPSHOT_PATH)
            if parent:
                os.makedirs(parent, exist_ok=True)
            payload = {
                'schema': 1,
                'source': 'atlas-uno-r4-sensor-hub',
                'updated_at': time.time(),
                'data': self.dashboard_cache,
            }
            with open(temporary, 'w', encoding='utf-8') as stream:
                json.dump(payload, stream, separators=(',', ':'), allow_nan=False)
            os.chmod(temporary, 0o600)
            os.replace(temporary, DASHBOARD_SNAPSHOT_PATH)
        except Exception as exc:
            try:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            except OSError:
                pass
            wall_now = time.time()
            if wall_now - self.last_dashboard_cache_error >= 30.0:
                self.last_dashboard_cache_error = wall_now
                self.get_logger().warning(f'dashboard snapshot unavailable: {exc}')

    def send_servo(self, channel, pulse_us):
        pulse_us = int(pulse_us)
        if pulse_us <= 0:
            self.write_line(f'FREE,{int(channel)}')
            return
        pulse_us = max(500, min(2500, pulse_us))
        self.write_line(f'SERVO,{int(channel)},{pulse_us}')

    def read_local_camera_commands(self):
        """Accept dashboard fallback commands without opening Mega serial twice."""
        if self.camera_socket is None:
            return
        for _ in range(8):
            try:
                raw = self.camera_socket.recv(96)
            except BlockingIOError:
                break
            except OSError:
                break
            match = re.fullmatch(rb'SERVO,(\d+),(\d+)', raw.strip())
            if not match:
                continue
            channel, pulse = (int(match.group(1)), int(match.group(2)))
            if channel not in (self.camera_pan_channel, self.camera_tilt_channel):
                continue
            self.send_servo(channel, pulse)

    def servo_cmd_cb(self, msg):
        value = int(msg.data)
        channel = (value // 10000) & 0xFF
        pulse = value % 10000
        self.send_servo(channel, pulse)

    @staticmethod
    def nmea_degrees(value, hemisphere):
        if not value:
            raise ValueError('empty coordinate')
        raw = float(value)
        degrees = int(raw / 100)
        decimal = degrees + (raw - degrees * 100) / 60.0
        if hemisphere in ('S', 'W'):
            decimal = -decimal
        return decimal

    @staticmethod
    def valid_nmea_checksum(sentence):
        if not sentence.startswith('$') or '*' not in sentence:
            return sentence.startswith('$')
        body, supplied = sentence[1:].rsplit('*', 1)
        checksum = 0
        for char in body:
            checksum ^= ord(char)
        try:
            return checksum == int(supplied[:2], 16)
        except ValueError:
            return False

    def publish_gps_fix(self, latitude, longitude, altitude, valid):
        msg = NavSatFix()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'gps_link'
        msg.status.status = NavSatStatus.STATUS_FIX if valid else NavSatStatus.STATUS_NO_FIX
        service = 0
        for talker in self.gps_constellations:
            if talker in ('GP', 'GN'):
                service |= NavSatStatus.SERVICE_GPS
            elif talker == 'GL':
                service |= NavSatStatus.SERVICE_GLONASS
            elif talker == 'GA':
                service |= NavSatStatus.SERVICE_GALILEO
            elif talker in ('BD', 'GB'):
                service |= NavSatStatus.SERVICE_COMPASS
        msg.status.service = service or NavSatStatus.SERVICE_GPS
        msg.latitude = latitude
        msg.longitude = longitude
        msg.altitude = altitude
        if math.isfinite(self.gps_hdop):
            variance = (self.gps_hdop * 3.0) ** 2
            msg.position_covariance[0] = variance
            msg.position_covariance[4] = variance
            msg.position_covariance[8] = variance * 4.0
            msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_APPROXIMATED
        else:
            msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.gps_fix_pub.publish(msg)

    def publish_gps_constellations(self):
        """Publish GSV counts plus observed NMEA talkers for UI fallback."""
        order = ('GPS', 'GLONASS', 'BEIDOU', 'GALILEO', 'QZSS', 'NAVIC')
        fields = [f'{name}:{self.gps_constellation_counts[name]}' for name in order]
        fields.append('TALKERS:' + ','.join(sorted(self.gps_constellations)))
        self.gps_constellations_pub.publish(String(data='|'.join(fields)))

    def handle_nmea(self, sentence):
        sentence = sentence.strip()
        if not self.valid_nmea_checksum(sentence):
            return
        self.gps_nmea_pub.publish(String(data=sentence))
        fields = sentence.split('*', 1)[0].split(',')
        if not fields or len(fields[0]) < 6:
            return
        talker = fields[0][1:3]
        message_type = fields[0][3:]
        if talker:
            self.gps_constellations.add(talker)
            self.publish_gps_constellations()
        try:
            if message_type == 'GGA' and len(fields) >= 10:
                quality = int(fields[6] or 0)
                satellites = int(fields[7] or 0)
                self.gps_hdop = float(fields[8]) if fields[8] else math.nan
                self.gps_satellites_pub.publish(Float32(data=float(satellites)))
                if math.isfinite(self.gps_hdop):
                    self.gps_hdop_pub.publish(Float32(data=self.gps_hdop))
                if fields[2] and fields[4]:
                    self.publish_gps_fix(
                        self.nmea_degrees(fields[2], fields[3]),
                        self.nmea_degrees(fields[4], fields[5]),
                        float(fields[9]) if fields[9] else math.nan,
                        quality > 0,
                    )
            elif message_type == 'GNS' and len(fields) >= 10:
                satellites = int(fields[7] or 0)
                self.gps_hdop = float(fields[8]) if fields[8] else math.nan
                self.gps_satellites_pub.publish(Float32(data=float(satellites)))
                if math.isfinite(self.gps_hdop):
                    self.gps_hdop_pub.publish(Float32(data=self.gps_hdop))
                if fields[2] and fields[4]:
                    self.publish_gps_fix(
                        self.nmea_degrees(fields[2], fields[3]),
                        self.nmea_degrees(fields[4], fields[5]),
                        float(fields[9]) if fields[9] else math.nan,
                        bool(fields[6] and fields[6].strip('N')),
                    )
            elif message_type == 'RMC' and len(fields) >= 7 and fields[3] and fields[5]:
                self.publish_gps_fix(
                    self.nmea_degrees(fields[3], fields[4]),
                    self.nmea_degrees(fields[5], fields[6]),
                    math.nan,
                    fields[2] == 'A',
                )
            elif message_type == 'GSV' and len(fields) >= 4:
                satellites = int(fields[3] or 0)
                constellation = {
                    'GP': 'GPS', 'GL': 'GLONASS', 'BD': 'BEIDOU',
                    'GB': 'BEIDOU', 'GA': 'GALILEO', 'GQ': 'QZSS',
                    'QZ': 'QZSS', 'GI': 'NAVIC', 'IR': 'NAVIC',
                }.get(talker)
                if constellation:
                    self.gps_constellation_counts[constellation] = satellites
                    self.publish_gps_constellations()
        except (ValueError, IndexError) as exc:
            self.status_pub.publish(String(data=f'gps_parse_error {message_type}: {exc}'))

    @staticmethod
    def parse_fields(raw):
        values = {}
        for item in raw.split(',')[1:]:
            if '=' in item:
                key, value = item.split('=', 1)
                values[key] = value
        return values

    @staticmethod
    def air_quality_label(iaq):
        if iaq <= 50:
            return 'EXCELLENT'
        if iaq <= 100:
            return 'GOOD'
        if iaq <= 150:
            return 'MODERATE'
        if iaq <= 200:
            return 'POOR'
        if iaq <= 300:
            return 'UNHEALTHY'
        return 'HAZARDOUS'

    def handle_bme(self, raw):
        values = self.parse_fields(raw)
        if values.get('OK') != '1':
            status = f'BME680_OFFLINE via={self.hub_transport}'
            self.environment_status_pub.publish(String(data=status))
            self.dashboard_cache_set('outside_status', status)
            return
        try:
            temperature = float(values['T'])
            humidity = float(values['H'])
            pressure = float(values['P'])
            gas = float(values['G'])
        except (KeyError, ValueError) as exc:
            status = f'BME680_PARSE_ERROR {exc}'
            self.environment_status_pub.publish(String(data=status))
            self.dashboard_cache_set('outside_status', status)
            return
        stable = time.time() - self.bme_started >= 180.0 and gas > 0.0
        iaq = eco2 = math.nan
        label = 'WARMING'
        if stable:
            if self.gas_baseline is None:
                self.gas_baseline = gas
            elif gas > self.gas_baseline:
                self.gas_baseline = 0.995 * self.gas_baseline + 0.005 * gas
            else:
                self.gas_baseline = 0.9995 * self.gas_baseline + 0.0005 * gas
            gas_score = min(75.0, max(0.0, 75.0 * gas / max(1.0, self.gas_baseline)))
            humidity_score = max(0.0, 25.0 - abs(humidity - 40.0) * 0.625)
            iaq = max(0.0, min(500.0, 500.0 - 5.0 * (gas_score + humidity_score)))
            eco2 = max(400.0, min(5000.0, 400.0 + max(0.0, iaq - 25.0) * 8.0))
            label = self.air_quality_label(iaq)
        self.outside_temp_pub.publish(Float32(data=temperature))
        self.outside_humidity_pub.publish(Float32(data=humidity))
        self.pressure_pub.publish(Float32(data=pressure))
        self.gas_pub.publish(Float32(data=gas))
        if math.isfinite(iaq):
            self.iaq_pub.publish(Float32(data=iaq))
            self.eco2_pub.publish(Float32(data=eco2))
        address = values.get('A', '--')
        status = (f'BME680_{label} addr=0x{address} via={self.hub_transport} '
                  f'T={temperature:.1f}C RH={humidity:.0f}% P={pressure:.1f}hPa')
        self.environment_status_pub.publish(String(data=status))
        payload = {
            'ok': True, 'address': f'0x{address}', 'bus': self.hub_transport,
            'temperature_c': round(temperature, 2), 'humidity_pct': round(humidity, 1),
            'pressure_hpa': round(pressure, 1), 'gas_resistance_ohm': round(gas),
            'heat_stable': stable, 'iaq_estimate': None if not math.isfinite(iaq) else round(iaq, 1),
            'eco2_estimate_ppm': None if not math.isfinite(eco2) else round(eco2),
            'quality': label, 'note': 'IAQ/eCO2 are VOC-derived estimates; eCO2 is not direct CO2',
        }
        payload_json = json.dumps(payload, separators=(',', ':'))
        self.environment_json_pub.publish(String(data=payload_json))
        timestamp = time.time()
        for key, value in (
            ('outside_temperature', temperature),
            ('outside_humidity', humidity),
            ('outside_pressure', pressure),
            ('outside_gas', gas),
            ('outside_status', status),
            ('bme680_json', payload_json),
        ):
            self.dashboard_cache_set(key, value, timestamp)

    def handle_amg(self, raw):
        values = self.parse_fields(raw)
        if values.get('OK') != '1':
            status = f'offline via={self.hub_transport}'
            self.thermal_status_pub.publish(String(data=status))
            self.dashboard_cache_set('thermal_status', status)
            return
        try:
            pixels = [float(value) for value in values['PX'].split(';')]
            minimum = float(values['MIN'])
            maximum = float(values['MAX'])
            average = float(values['AVG'])
            center = float(values['CENTER'])
            if len(pixels) != 64:
                raise ValueError(f'expected 64 pixels, got {len(pixels)}')
        except (KeyError, ValueError) as exc:
            status = f'parse_error {exc}'
            self.thermal_status_pub.publish(String(data=status))
            self.dashboard_cache_set('thermal_status', status)
            return
        self.thermal_min_pub.publish(Float32(data=minimum))
        self.thermal_max_pub.publish(Float32(data=maximum))
        self.thermal_avg_pub.publish(Float32(data=average))
        self.thermal_center_pub.publish(Float32(data=center))
        payload = {
            'ok': True, 'address': f"0x{values.get('A', '--')}", 'bus': self.hub_transport,
            'min_c': minimum, 'max_c': maximum, 'avg_c': average, 'center_c': center,
            'pixels_c': pixels,
        }
        payload_json = json.dumps(payload, separators=(',', ':'))
        status = (f'online via={self.hub_transport} '
                  f'min={minimum:.1f} max={maximum:.1f}')
        self.thermal_json_pub.publish(String(data=payload_json))
        self.thermal_status_pub.publish(String(data=status))
        timestamp = time.time()
        self.dashboard_cache_set('thermal_json', payload_json, timestamp)
        self.dashboard_cache_set('thermal_status', status, timestamp)

    def handle_nicla_env(self, raw):
        values = self.parse_fields(raw)
        if values.get('OK') != '1':
            self.nicla_status_pub.publish(String(
                data=f'NICLA_SENSE_ENV_OFFLINE via={self.hub_transport}'))
            return
        field_names = ('T', 'H', 'IAQ', 'RIAQ', 'ECO2', 'TVOC', 'ETOH',
                       'AQI', 'FAQI', 'NO2', 'O3')
        try:
            data = {name: float(values[name]) for name in field_names}
        except (KeyError, ValueError) as exc:
            self.nicla_status_pub.publish(String(data=f'NICLA_SENSE_ENV_PARSE_ERROR {exc}'))
            return
        publishers = {
            'T': self.nicla_temp_pub,
            'H': self.nicla_humidity_pub,
            'IAQ': self.nicla_indoor_iaq_pub,
            'RIAQ': self.nicla_relative_iaq_pub,
            'ECO2': self.nicla_eco2_pub,
            'TVOC': self.nicla_tvoc_pub,
            'ETOH': self.nicla_ethanol_pub,
            'AQI': self.nicla_outdoor_aqi_pub,
            'FAQI': self.nicla_fast_aqi_pub,
            'NO2': self.nicla_no2_pub,
            'O3': self.nicla_o3_pub,
        }
        for name, publisher in publishers.items():
            if math.isfinite(data[name]):
                publisher.publish(Float32(data=data[name]))
        if NICLA_PRIMARY:
            self.outside_temp_pub.publish(Float32(data=data['T']))
            self.outside_humidity_pub.publish(Float32(data=data['H']))
            self.iaq_pub.publish(Float32(data=data['IAQ']))
            self.eco2_pub.publish(Float32(data=data['ECO2']))
        payload = {
            'ok': True,
            'address': f"0x{values.get('A', '21')}",
            'transport': self.hub_transport,
            'temperature_c': data['T'],
            'humidity_pct': data['H'],
            'indoor_iaq': data['IAQ'],
            'relative_iaq_pct': data['RIAQ'],
            'eco2_ppm': data['ECO2'],
            'tvoc_mg_m3': data['TVOC'],
            'ethanol_ppm': data['ETOH'],
            'outdoor_aqi': data['AQI'],
            'outdoor_fast_aqi': data['FAQI'],
            'no2_ppb': data['NO2'],
            'o3_ppb': data['O3'],
            'primary_environment_source': NICLA_PRIMARY,
        }
        self.nicla_json_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))
        self.nicla_status_pub.publish(String(
            data=(f'ONLINE via={self.hub_transport} T={data["T"]:.1f}C '
                  f'RH={data["H"]:.0f}% IAQ={data["IAQ"]:.1f} '
                  f'NO2={data["NO2"]:.1f}ppb O3={data["O3"]:.1f}ppb')))

    def tick(self):
        self.flush_dashboard_cache()
        self.read_local_camera_commands()
        if self.ser is None:
            self.connect()
            return
        try:
            raw = self.ser.readline().decode(errors='replace').strip()
        except Exception as exc:
            self.status_pub.publish(String(data=f'read_error {exc}'))
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            return
        if not raw:
            now = time.time()
            if now - self.last_serial_rx >= SERIAL_STALE_REOPEN_SECONDS:
                self.status_pub.publish(String(
                    data=(f'serial_stale_reopening age_s='
                          f'{now - self.last_serial_rx:.1f}')))
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                self.last_serial_rx = now
                self.last_wait_status = now
                return
            if now - self.last_ok > 2.5 and now - self.last_wait_status >= 1.0:
                self.last_wait_status = now
                self.status_pub.publish(String(data='waiting_for_data'))
            return
        self.last_serial_rx = time.time()
        if (raw.startswith('ATLAS_ULTRASONIC') or
                raw.startswith('ATLAS_UNO_SENSOR_HUB') or
                raw.startswith('ATLAS_UNO_R4_WIFI_I2C_HUB') or
                raw.startswith('ATLAS_PORTENTA_SENSOR_HUB')):
            if raw.startswith('ATLAS_PORTENTA_SENSOR_HUB'):
                self.hub_transport = 'portenta_h7'
            elif raw.startswith('ATLAS_UNO_R4_WIFI_I2C_HUB'):
                self.hub_transport = 'uno_r4_i2c_hub'
            self.status_pub.publish(String(data=raw))
            return
        if raw.startswith('I2C,') or raw.startswith('I2CSTAT,'):
            self.i2c_status_pub.publish(String(data=raw))
            self.dashboard_cache_set('i2c_status', raw)
            return
        if raw.startswith('BME,'):
            self.handle_bme(raw)
            return
        if raw.startswith('AMG,'):
            self.handle_amg(raw)
            return
        if raw.startswith('NICLAENV,'):
            self.handle_nicla_env(raw)
            return
        if raw.startswith('GPS,$'):
            if self.gnss_enabled:
                self.handle_nmea(raw[4:])
            return
        if raw.startswith('GPSSTAT,'):
            if self.gnss_enabled:
                self.gps_status_pub.publish(String(data=raw))
            return
        if raw.startswith('RADARHEX,'):
            payload = raw.split(',', 1)[1].strip()
            if payload and len(payload) % 2 == 0:
                self.radar_last_rx = time.time()
                self.radar_raw_pub.publish(String(data=payload))
                status = (f'{self.hub_transport.upper()}_RADAR_STREAM '
                          f'bytes={len(payload) // 2}')
                self.radar_status_pub.publish(String(data=status))
                self.dashboard_cache_set('radar_link', status)
            else:
                status = f'{self.hub_transport.upper()}_RADAR_FRAME_INVALID'
                self.radar_status_pub.publish(String(data=status))
                self.dashboard_cache_set('radar_link', status)
            return
        if raw.startswith('HEARTBEAT,'):
            self.status_pub.publish(String(data=raw))
            match = re.search(r'RADAR_BAUD=(\d+),RADAR_BYTES=(\d+)', raw)
            if match:
                baud, total = (int(value) for value in match.groups())
                self.radar_bytes_total = total
                age = (time.time() - self.radar_last_rx
                       if self.radar_last_rx else -1.0)
                state = 'STREAMING' if 0 <= age < 3.0 else 'WAITING_FOR_UART'
                status = (f'{self.hub_transport.upper()}_RADAR_{state} '
                          f'baud={baud} bytes_total={total} rx_age_s={age:.1f}')
                self.radar_status_pub.publish(String(data=status))
                self.dashboard_cache_set('radar_link', status)
            return
        if raw.startswith('USTAT,'):
            # Firmware health state for all four physical positions. Preserve
            # DISABLED versus ONLINE/OFFLINE instead of misclassifying this
            # valid diagnostic line as an ultrasonic range parse error.
            self.status_pub.publish(String(data=raw))
            self.dashboard_cache_set('us_status', raw)
            return
        if raw.startswith('ACK,') or raw.startswith('ERR,'):
            self.pca_status_pub.publish(String(data=raw))
            self.dashboard_cache_set('pca_status', raw)
            return
        m = LINE_RE.fullmatch(raw)
        if not m:
            self.status_pub.publish(String(data=f'parse_error {raw[:80]}'))
            return
        values = m.groupdict()
        front = int(values['front'])
        left = int(values['left'])
        right = int(values['right'])
        rear = int(values['rear']) if values['rear'] is not None else -1
        la, ra, c1, c2, pca = (
            values['la'], values['ra'], values['c1'], values['c2'], values['pca']
        )
        self.publish_mm(self.front_pub, front)
        if self.hub_transport in ('portenta_h7', 'uno_r4_i2c_hub'):
            # New sensor-hub harnesses use logical physical-side labels directly.
            self.publish_mm(self.left_pub, left)
            self.publish_mm(self.right_pub, right)
        else:
            # The existing UNO harness is physically mirrored on ATLAS.
            self.publish_mm(self.left_pub, right)
            self.publish_mm(self.right_pub, left)
        self.publish_mm(self.rear_pub, rear)
        if la is not None:
            self.left_servo_pub.publish(Int32(data=int(la)))
            self.right_servo_pub.publish(Int32(data=int(ra)))
            # Only the selected camera backend may publish feedback. Publishing
            # the UNO's cached C1/C2 values while its PCA is absent races the
            # native Jetson PTZ driver and makes web/voice commands jump.
            if self.camera_via_arduino and pca == '1':
                self.camera_bottom_pub.publish(Int32(data=int(c1)))
                self.camera_second_pub.publish(Int32(data=int(c2)))
                camera_status = (f'online via={self.hub_transport} '
                                 f'cam1_us={c1} cam2_us={c2}')
                self.camera_status_pub.publish(String(data=camera_status))
                self.dashboard_cache_set('camera_servo_status', camera_status)
            pca_status = f'pca={pca} left_us={la} right_us={ra} cam1_us={c1} cam2_us={c2}'
            self.pca_status_pub.publish(String(data=pca_status))
            self.dashboard_cache_set('pca_status', pca_status)
        self.last_ok = time.time()
        status = f'ok front={front} left={left} right={right} rear={rear}'
        self.status_pub.publish(String(data=status))
        timestamp = time.time()
        for key, value in (
            ('us_status', status),
            ('us_front', float(front if front >= 0 else -1)),
            ('us_left', float(left if left >= 0 else -1)),
            ('us_right', float(right if right >= 0 else -1)),
            ('us_rear', float(rear if rear >= 0 else -1)),
        ):
            self.dashboard_cache_set(key, value, timestamp)

    def destroy_node(self):
        self.flush_dashboard_cache(force=True)
        if self.camera_socket is not None:
            try:
                self.camera_socket.close()
                if os.path.exists(CAMERA_SOCKET_PATH):
                    os.unlink(CAMERA_SOCKET_PATH)
            except Exception:
                pass
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        super().destroy_node()


def main():
    rclpy.init()
    node = UltrasonicArduinoBridge()
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
