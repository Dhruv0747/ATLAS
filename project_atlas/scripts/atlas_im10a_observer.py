#!/usr/bin/env python3
"""Read-only IM10A acquisition. Isolated topics; not a navigation input yet."""
import math
import json
import struct
import time
import serial
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from sensor_msgs.msg import Imu
from geometry_msgs.msg import Vector3Stamped
from std_msgs.msg import String


class Observer(Node):
    def __init__(self):
        super().__init__('atlas_im10a_observer')
        self.declare_parameter('port', '/dev/serial/by-path/platform-3610000.usb-usb-0:2.2.4.1:1.0-port0')
        self.pub = self.create_publisher(Imu, '/im10a/imu/unvalidated', 10)
        self.mag = self.create_publisher(Vector3Stamped, '/im10a/magnetic_raw', 10)
        self.status = self.create_publisher(String, '/im10a/status', 10)
        self.dashboard = self.create_publisher(String, '/im10a/dashboard_json', 10)
        self.euler = None
        self.magnetic = None
        self.buffer = bytearray()
        self.accel = None
        self.last = 0.0
        self.link = None
        self.retry = 0.0
        self.errors = 0
        self.create_timer(.02, self.read)
        self.create_timer(1., self.health)

    def health(self):
        age = time.monotonic() - self.last
        state = 'LIVE_UNVALIDATED' if age < .5 else 'STALE'
        self.status.publish(String(data=f'{state}; age={age:.2f}s; checksum_errors={self.errors}; EKF disabled'))

    def read(self):
        now = time.monotonic()
        try:
            if self.link is None:
                if now < self.retry:
                    return
                self.retry = now + 3.
                s = serial.Serial(port=None, baudrate=9600, timeout=0, exclusive=True)
                s.dtr = False
                s.rts = False
                s.port = self.get_parameter('port').value
                s.open()
                self.link = s
                self.buffer.clear()
                self.accel = None
            self.buffer.extend(self.link.read(min(self.link.in_waiting, 4096)))
            while len(self.buffer) >= 11:
                if self.buffer[0] != 0x55:
                    del self.buffer[0]
                    continue
                p = self.buffer[:11]
                if sum(p[:10]) % 256 != p[10]:
                    self.errors += 1
                    del self.buffer[0]
                    continue
                del self.buffer[:11]
                xyz = struct.unpack('<3h', p[2:8])
                if p[1] == 0x51:
                    self.accel = (now, tuple(x * 16. * 9.80665 / 32768 for x in xyz))
                elif p[1] == 0x52 and self.accel and now - self.accel[0] < .15:
                    m = Imu()
                    m.header.stamp = self.get_clock().now().to_msg()
                    m.header.frame_id = 'im10a_sensor_unvalidated'
                    m.orientation_covariance[0] = -1.  # No magnetic orientation used.
                    m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z = (
                        x * math.radians(2000.) / 32768 for x in xyz)
                    m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z = self.accel[1]
                    # Zero covariance means unknown; this topic MUST NOT feed EKF yet.
                    self.pub.publish(m)
                    self.last = now
                    data = {
                        'source': 'Hiwonder IM10A', 'role': 'primary candidate / monitoring',
                        'frame': m.header.frame_id, 'qualified_for_navigation': False,
                        'navigation_fusion': 'DISABLED: mounting and dynamic tests pending',
                        'gx': m.angular_velocity.x, 'gy': m.angular_velocity.y,
                        'gz': m.angular_velocity.z,
                        'ax': m.linear_acceleration.x, 'ay': m.linear_acceleration.y,
                        'az': m.linear_acceleration.z,
                    }
                    if self.euler and now - self.euler[0] < .3:
                        data.update(zip(('roll', 'pitch', 'yaw'), self.euler[1]))
                        data['heading'] = self.euler[1][2] % 360
                    if self.magnetic and now - self.magnetic[0] < .3:
                        data.update(zip(('mx_raw', 'my_raw', 'mz_raw'), self.magnetic[1]))
                    self.dashboard.publish(String(data=json.dumps(data)))
                elif p[1] == 0x53:
                    self.euler = (now, tuple(x * 180. / 32768 for x in xyz))
                elif p[1] == 0x54:
                    self.magnetic = (now, xyz)
                    m = Vector3Stamped()
                    m.header.stamp = self.get_clock().now().to_msg()
                    m.header.frame_id = 'im10a_sensor_unvalidated'
                    m.vector.x, m.vector.y, m.vector.z = map(float, xyz)
                    self.mag.publish(m)
        except (serial.SerialException, OSError) as exc:
            self.get_logger().warning(str(exc))
            if self.link:
                self.link.close()
            self.link = None
            self.accel = None


def main():
    rclpy.init()
    node = Observer()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node.link:
            node.link.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
