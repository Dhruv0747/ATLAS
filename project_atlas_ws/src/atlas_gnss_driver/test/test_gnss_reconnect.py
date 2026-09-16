"""Stationary, mocked serial tests. Never open a physical receiver."""
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import MagicMock, patch

# Test the production parser/lifecycle without DDS, ROS timers or real devices.
# This keeps fabricated fixes entirely out of the robot's ROS graph.
class FakeNode:
    def __init__(self, *args):
        self.parameters = {}

    def declare_parameter(self, name, value):
        self.parameters[name] = value

    def get_parameter(self, name):
        return SimpleNamespace(value=self.parameters[name])

    def create_publisher(self, *args):
        return MagicMock()

    def create_timer(self, *args):
        pass

    def get_logger(self):
        return MagicMock()

    def get_clock(self):
        return MagicMock()

    def destroy_node(self):
        pass


class Fix:
    COVARIANCE_TYPE_UNKNOWN = 0

    def __init__(self):
        self.header = SimpleNamespace()
        self.status = SimpleNamespace()


fake_ros = ModuleType('rclpy')
fake_node = ModuleType('rclpy.node')
fake_node.Node = FakeNode
fake_executors = ModuleType('rclpy.executors')
fake_executors.ExternalShutdownException = type('ExternalShutdownException', (Exception,), {})
fake_sensor = ModuleType('sensor_msgs.msg')
fake_sensor.NavSatFix = Fix
fake_sensor.NavSatStatus = SimpleNamespace(STATUS_NO_FIX=-1, STATUS_FIX=0, SERVICE_GPS=1,
                                          SERVICE_GLONASS=2, SERVICE_COMPASS=4, SERVICE_GALILEO=8)
fake_std = ModuleType('std_msgs.msg')
fake_std.Float32 = fake_std.String = SimpleNamespace
sys.modules.update({'rclpy': fake_ros, 'rclpy.node': fake_node,
                    'rclpy.executors': fake_executors,
                    'sensor_msgs': ModuleType('sensor_msgs'), 'sensor_msgs.msg': fake_sensor,
                    'std_msgs': ModuleType('std_msgs'), 'std_msgs.msg': fake_std})
if os.name == 'nt':
    fake_termios = ModuleType('termios')
    for baud in (4800, 9600, 19200, 38400, 57600, 115200):
        setattr(fake_termios, 'B' + str(baud), baud)
    sys.modules['termios'] = fake_termios
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atlas_gnss_driver.gnss_node import GnssNode


def sentence(payload):
    checksum = 0
    for character in payload:
        checksum ^= ord(character)
    return f'${payload}*{checksum:02X}'


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.clock_patch = patch('atlas_gnss_driver.gnss_node.time.monotonic', return_value=100.0)
        self.clock = self.clock_patch.start()
        with patch.object(GnssNode, '_open_port'):
            self.node = GnssNode()
        for name in ('fix_pub', 'sat_pub', 'hdop_pub', 'const_pub', 'nmea_pub', 'status_pub', 'diagnostics_pub'):
            setattr(self.node, name, MagicMock())

    def tearDown(self):
        self.node.fd = None
        self.node.destroy_node()
        self.clock_patch.stop()

    def gga(self, quality=1, talker='GN', count=8):
        self.node._handle_line(sentence(f'{talker}GGA,123519,0000.000,N,00000.000,E,{quality},{count:02d},0.9,12.0,M,0.0,M,,'))

    def diagnostics(self):
        same = SimpleNamespace(st_rdev=1, st_ino=2)
        self.node.fd = 123
        self.node.last_byte = self.node.last_nmea
        self.node.opened_at = self.clock.return_value
        with patch('os.stat', return_value=same), patch('os.fstat', return_value=same):
            self.node._publish_status()
        return json.loads(self.node.diagnostics_pub.publish.call_args.args[0].data)

    def test_zero_coordinate_valid_fix(self):
        self.gga()
        self.assertTrue(self.node.fix_valid)
        self.assertEqual(self.node.fix_pub.publish.call_args.args[0].latitude, 0.0)

    def test_invalid_gga_removes_previous_fix_immediately(self):
        self.gga()
        self.gga(quality=0, count=0)
        self.assertFalse(self.node.fix_valid)
        self.assertEqual(self.node.last_fix, 0.0)
        self.assertEqual(self.diagnostics()['state'], 'NMEA_LIVE_NO_FIX')

    def test_combined_gga_not_overwritten_by_individual_system(self):
        self.gga(count=10)
        self.gga(talker='GP', quality=0, count=0)
        self.assertEqual(self.node.satellites_used, 10)
        self.assertTrue(self.node.fix_valid)

    def test_zero_gsv_is_not_satellite_detection(self):
        self.node._handle_line(sentence('GLGSV,1,1,00'))
        d = self.diagnostics()
        self.assertEqual(d['constellations']['GLONASS']['in_view'], 0)
        self.assertIn('GL', d['talkers'])
        self.assertFalse(d['fix_valid'])

    def test_stale_gsv_becomes_unknown_even_with_new_nmea(self):
        self.node._handle_line(sentence('GPGSV,1,1,04'))
        self.clock.return_value = 108.0
        self.gga(quality=0, count=0)
        self.assertIsNone(self.diagnostics()['constellations']['GPS']['in_view'])

    def test_stale_fix_cleared(self):
        self.gga()
        self.clock.return_value = 104.0
        self.node.last_byte = self.node.last_nmea = 104.0
        self.assertFalse(self.diagnostics()['fix_valid'])
        self.assertEqual(self.node.fix_pub.publish.call_args.args[0].status.status, -1)

    def test_bad_checksum_rejected(self):
        self.node._handle_line('$GPGSV,1,1,00*00')
        self.assertEqual(self.node.valid_lines, 0)
        self.assertEqual(self.node.invalid_lines, 1)

    def test_eof_closes_clears_then_reopens_by_id(self):
        self.gga()
        self.node.fd = 123
        self.node.buffer = b'old incomplete sentence'
        with patch('os.read', return_value=b''), patch('os.close'):
            self.node._poll()
        self.assertIsNone(self.node.fd)
        self.assertFalse(self.node.fix_valid)
        self.assertEqual(self.node.buffer, b'')
        with patch('atlas_gnss_driver.gnss_node.open_raw_serial', return_value=456) as opened:
            self.node._poll()
            opened.assert_called_once_with(self.node.port, self.node.baud)

    def test_usb_rebind_detected_without_eof(self):
        self.node.fd = 123
        self.node.opened_at = 100
        with patch('os.stat', return_value=SimpleNamespace(st_rdev=2, st_ino=3)), patch('os.fstat', return_value=SimpleNamespace(st_rdev=1, st_ino=2)), patch('os.close'):
            self.node._publish_status()
        self.assertIsNone(self.node.fd)
        self.assertEqual(self.node.last_error, 'USB path changed')

    def test_temporary_eagain_does_not_reset_receiver(self):
        self.node.fd = 123
        with patch('os.read', side_effect=BlockingIOError), patch('os.close') as closed:
            self.node._poll()
            closed.assert_not_called()
        self.assertEqual(self.node.fd, 123)

    def test_shutdown_does_not_publish_after_ros_context_ends(self):
        self.node.destroy_node()
        self.node.fix_pub.publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
