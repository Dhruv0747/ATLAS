#!/usr/bin/env python3
import re
import time
import os
import math
import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String, Int32
from sensor_msgs.msg import Imu, MagneticField, NavSatFix, NavSatStatus
from geometry_msgs.msg import Vector3

try:
    import serial
except Exception as exc:
    serial = None
    SERIAL_IMPORT_ERROR = exc
else:
    SERIAL_IMPORT_ERROR = None

PORT = '/dev/serial/by-id/usb-Arduino_UNO_WiFi_R4_CMSIS-DAP_E4B063836708-if01'
BAUD = 115200
GNSS_ENABLED = os.environ.get('ATLAS_GNSS_ENABLED', '1').strip().lower() not in (
    '0', 'false', 'no', 'off',
)
CAMERA_ROUTE = os.environ.get('ATLAS_CAMERA_ROUTE', 'jetson').strip().lower()
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
        self.thermal_json_pub = self.create_publisher(String, '/thermal/amg8833/json', 10)
        self.thermal_status_pub = self.create_publisher(String, '/thermal/amg8833/status', 10)
        self.thermal_min_pub = self.create_publisher(Float32, '/thermal/amg8833/min_c', 10)
        self.thermal_max_pub = self.create_publisher(Float32, '/thermal/amg8833/max_c', 10)
        self.thermal_avg_pub = self.create_publisher(Float32, '/thermal/amg8833/avg_c', 10)
        self.thermal_center_pub = self.create_publisher(Float32, '/thermal/amg8833/center_c', 10)
        self.imu_pub = self.create_publisher(Imu, '/imu/data', 20)
        self.mag_pub = self.create_publisher(MagneticField, '/imu/mag', 20)
        self.euler_pub = self.create_publisher(Vector3, '/imu/euler', 20)
        self.roll_pub = self.create_publisher(Float32, '/imu/roll', 20)
        self.pitch_pub = self.create_publisher(Float32, '/imu/pitch', 20)
        self.heading_pub = self.create_publisher(Float32, '/imu/heading', 20)
        self.imu_json_pub = self.create_publisher(String, '/imu/dashboard_json', 10)
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
        self.camera_via_arduino = CAMERA_ROUTE == 'arduino'
        if self.camera_via_arduino:
            self.create_subscription(Int32, '/camera/bottom_servo_cmd_us', lambda m: self.send_servo(1, m.data), 10)
            self.create_subscription(Int32, '/camera/second_servo_cmd_us', lambda m: self.send_servo(2, m.data), 10)
        self.create_subscription(Int32, '/ultrasonic/right_servo_cmd_us', lambda m: self.send_servo(3, m.data), 10)
        self.ser = None
        self.last_ok = 0.0
        self.gps_hdop = math.nan
        self.gps_constellations = set()
        self.gps_constellation_counts = {
            'GPS': 0, 'GLONASS': 0, 'BEIDOU': 0,
            'GALILEO': 0, 'QZSS': 0, 'NAVIC': 0,
        }
        self.gas_baseline = None
        self.bme_started = time.time()
        self.create_timer(0.05, self.tick)
        camera_route = 'Arduino UNO R4' if self.camera_via_arduino else 'Jetson i2c-7 / atlas_arducam_ptz'
        self.get_logger().info(f'ATLAS Arduino sensor hub starting on {PORT}; camera route: {camera_route}')
        if not self.gnss_enabled:
            self.get_logger().info('Arduino GNSS forwarding disabled by ATLAS_GNSS_ENABLED=0')

    def connect(self):
        if serial is None:
            self.status_pub.publish(String(data=f'pyserial_missing {SERIAL_IMPORT_ERROR}'))
            return False
        try:
            self.ser = serial.Serial(PORT, BAUD, timeout=0.02)
            time.sleep(1.8)
            self.status_pub.publish(String(data='connected'))
            self.write_line('PCA?')
            self.write_line('SCAN')
            self.write_line('HOME')
            return True
        except Exception as exc:
            self.ser = None
            self.status_pub.publish(String(data=f'connect_error {exc}'))
            return False

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

    def send_servo(self, channel, pulse_us):
        pulse_us = int(pulse_us)
        if pulse_us <= 0:
            self.write_line(f'FREE,{int(channel)}')
            return
        pulse_us = max(500, min(2500, pulse_us))
        self.write_line(f'SERVO,{int(channel)},{pulse_us}')

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
            self.environment_status_pub.publish(String(data='BME680_OFFLINE via=arduino'))
            return
        try:
            temperature = float(values['T'])
            humidity = float(values['H'])
            pressure = float(values['P'])
            gas = float(values['G'])
        except (KeyError, ValueError) as exc:
            self.environment_status_pub.publish(String(data=f'BME680_PARSE_ERROR {exc}'))
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
        self.environment_status_pub.publish(String(
            data=f'BME680_{label} addr=0x{address} via=arduino T={temperature:.1f}C RH={humidity:.0f}% P={pressure:.1f}hPa'))
        payload = {
            'ok': True, 'address': f'0x{address}', 'bus': 'arduino_uno_r4',
            'temperature_c': round(temperature, 2), 'humidity_pct': round(humidity, 1),
            'pressure_hpa': round(pressure, 1), 'gas_resistance_ohm': round(gas),
            'heat_stable': stable, 'iaq_estimate': None if not math.isfinite(iaq) else round(iaq, 1),
            'eco2_estimate_ppm': None if not math.isfinite(eco2) else round(eco2),
            'quality': label, 'note': 'IAQ/eCO2 are VOC-derived estimates; eCO2 is not direct CO2',
        }
        self.environment_json_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))

    def handle_amg(self, raw):
        values = self.parse_fields(raw)
        if values.get('OK') != '1':
            self.thermal_status_pub.publish(String(data='offline via=arduino'))
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
            self.thermal_status_pub.publish(String(data=f'parse_error {exc}'))
            return
        self.thermal_min_pub.publish(Float32(data=minimum))
        self.thermal_max_pub.publish(Float32(data=maximum))
        self.thermal_avg_pub.publish(Float32(data=average))
        self.thermal_center_pub.publish(Float32(data=center))
        payload = {
            'ok': True, 'address': f"0x{values.get('A', '--')}", 'bus': 'arduino_uno_r4',
            'min_c': minimum, 'max_c': maximum, 'avg_c': average, 'center_c': center,
            'pixels_c': pixels,
        }
        self.thermal_json_pub.publish(String(data=json.dumps(payload, separators=(',', ':'))))
        self.thermal_status_pub.publish(String(data=f'online via=arduino min={minimum:.1f} max={maximum:.1f}'))

    @staticmethod
    def quaternion_to_euler(x, y, z, w):
        sinr = 2.0 * (w * x + y * z)
        cosr = 1.0 - 2.0 * (x * x + y * y)
        roll = math.degrees(math.atan2(sinr, cosr))
        sinp = 2.0 * (w * y - z * x)
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, sinp))))
        siny = 2.0 * (w * z + x * y)
        cosy = 1.0 - 2.0 * (y * y + z * z)
        yaw = math.degrees(math.atan2(siny, cosy))
        return roll, pitch, yaw

    def handle_bno(self, raw):
        values = self.parse_fields(raw)
        if values.get('OK') != '1':
            self.i2c_status_pub.publish(String(data='BNO08X_OFFLINE via=arduino'))
            return
        try:
            names = ('QX', 'QY', 'QZ', 'QW', 'GX', 'GY', 'GZ', 'AX', 'AY', 'AZ', 'MX', 'MY', 'MZ')
            data = {name: float(values[name]) for name in names}
        except (KeyError, ValueError) as exc:
            self.i2c_status_pub.publish(String(data=f'BNO08X_PARSE_ERROR {exc}'))
            return
        roll, pitch, yaw = self.quaternion_to_euler(data['QX'], data['QY'], data['QZ'], data['QW'])
        now = self.get_clock().now().to_msg()
        imu = Imu()
        imu.header.stamp = now
        imu.header.frame_id = 'base_link'
        ros_yaw = math.radians(-yaw)
        imu.orientation.z = math.sin(ros_yaw / 2.0)
        imu.orientation.w = math.cos(ros_yaw / 2.0)
        imu.orientation_covariance = [0.002, 0.0, 0.0, 0.0, 0.002, 0.0, 0.0, 0.0, 0.002]
        imu.angular_velocity.z = -data['GZ']
        imu.angular_velocity_covariance = [0.001, 0.0, 0.0, 0.0, 0.001, 0.0, 0.0, 0.0, 0.001]
        imu.linear_acceleration.x = data['AX']
        imu.linear_acceleration.y = data['AY']
        imu.linear_acceleration.z = data['AZ']
        imu.linear_acceleration_covariance = [0.05, 0.0, 0.0, 0.0, 0.05, 0.0, 0.0, 0.0, 0.05]
        self.imu_pub.publish(imu)
        mag = MagneticField()
        mag.header.stamp = now
        mag.header.frame_id = 'base_link'
        mag.magnetic_field.x = data['MX'] * 1e-6
        mag.magnetic_field.y = data['MY'] * 1e-6
        mag.magnetic_field.z = data['MZ'] * 1e-6
        self.mag_pub.publish(mag)
        self.euler_pub.publish(Vector3(x=roll, y=pitch, z=yaw))
        self.roll_pub.publish(Float32(data=roll))
        self.pitch_pub.publish(Float32(data=pitch))
        self.heading_pub.publish(Float32(data=(yaw + 360.0) % 360.0))
        dashboard = {
            'roll': round(roll, 3), 'pitch': round(pitch, 3), 'yaw': round(yaw, 3),
            'heading': round((yaw + 360.0) % 360.0, 3), 'frame': 'base_link',
            'address': f"0x{values.get('A', '--')}", 'transport': 'arduino_uno_r4',
        }
        dashboard.update({name.lower(): round(value, 6) for name, value in data.items()})
        self.imu_json_pub.publish(String(data=json.dumps(dashboard, separators=(',', ':'))))

    def tick(self):
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
            if time.time() - self.last_ok > 2.5:
                self.status_pub.publish(String(data='waiting_for_data'))
            return
        if raw.startswith('ATLAS_ULTRASONIC') or raw.startswith('ATLAS_UNO_SENSOR_HUB'):
            self.status_pub.publish(String(data=raw))
            return
        if raw.startswith('I2C,') or raw.startswith('I2CSTAT,'):
            self.i2c_status_pub.publish(String(data=raw))
            return
        if raw.startswith('BME,'):
            self.handle_bme(raw)
            return
        if raw.startswith('AMG,'):
            self.handle_amg(raw)
            return
        if raw.startswith('BNO,'):
            self.handle_bno(raw)
            return
        if raw.startswith('GPS,$'):
            if self.gnss_enabled:
                self.handle_nmea(raw[4:])
            return
        if raw.startswith('GPSSTAT,'):
            if self.gnss_enabled:
                self.gps_status_pub.publish(String(data=raw))
            return
        if raw.startswith('ACK,') or raw.startswith('ERR,'):
            self.pca_status_pub.publish(String(data=raw))
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
        # The two side ultrasonic sensors are physically mirrored on ATLAS:
        # the Arduino's LEFT field is the rover's right side and vice versa.
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
                self.camera_status_pub.publish(String(data=f'online via=arduino cam1_us={c1} cam2_us={c2}'))
            self.pca_status_pub.publish(String(data=f'pca={pca} left_us={la} right_us={ra} cam1_us={c1} cam2_us={c2}'))
        self.last_ok = time.time()
        self.status_pub.publish(
            String(data=f'ok front={front} left={left} right={right} rear={rear}')
        )

    def destroy_node(self):
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
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
