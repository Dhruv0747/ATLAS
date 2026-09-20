"""Pure protocol tests: no serial ports or robot commands."""
import ast
from pathlib import Path
import sys
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_usb_identity import protocol_matches
from atlas_usb_identity import open_verified


def nmea(body):
    checksum = 0
    for value in body:
        checksum ^= value
    return b'$' + body + b'*' + f'{checksum:02X}'.encode() + b'\r\n'


def imu(kind):
    p = bytes([0x55, kind]) + b'\x00' * 8
    return p + bytes([sum(p) % 256])


def board(kind):
    payload = b'\x00' * (16 if kind == 0x0D else 7)
    p = bytes([len(payload) + 3, kind]) + payload
    return b'\xff\xfb' + p + bytes([sum(p) % 256])


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.gps = nmea(b'GNGGA,,,,,,0,00,25.5,,,,,,') + nmea(b'GNRMC,,V,,,,,,,,,,M,V') + nmea(b'GPGSV,1,1,00')
        self.imu = (imu(0x51) + imu(0x52) + imu(0x53)) * 2
        self.board = (board(0x0D) + board(0x0A)) * 2

    def test_live_no_fix_is_valid_identity(self):
        self.assertTrue(protocol_matches(self.gps, 'gps'))

    def test_imu_identity(self):
        self.assertTrue(protocol_matches(self.imu, 'imu'))

    def test_motor_identity(self):
        self.assertTrue(protocol_matches(self.board, 'yahboom'))

    def test_wrong_roles_rejected(self):
        for actual, data in [('gps', self.gps), ('imu', self.imu), ('yahboom', self.board)]:
            for role in ('gps', 'imu', 'yahboom'):
                if role != actual:
                    self.assertFalse(protocol_matches(data, role))

    def test_noise_and_partial_rejected(self):
        for role in ('gps', 'imu', 'yahboom'):
            self.assertFalse(protocol_matches(b'\xff\xfb\xff\x55\x51$GNGGA*00\n' * 6, role))
            self.assertFalse(protocol_matches(b'', role))

    def test_imu_one_type_insufficient(self):
        self.assertFalse(protocol_matches(imu(0x53) * 20, 'imu'))

    def test_motor_without_encoders_rejected(self):
        self.assertFalse(protocol_matches(board(0x0A) * 20, 'yahboom'))

    def test_gsv_labels_alone_insufficient(self):
        self.assertFalse(protocol_matches(nmea(b'GPGSV,1,1,00') * 20, 'gps'))

    def test_checksums_required(self):
        self.assertFalse(protocol_matches(self.gps.replace(b'25.5', b'25.6'), 'gps'))
        self.assertFalse(protocol_matches((imu(0x51)[:-1] + b'\x00') * 10, 'imu'))
        self.assertFalse(protocol_matches((board(0x0D)[:-1] + b'\x00') * 10, 'yahboom'))

    def test_resync_after_garbage(self):
        self.assertTrue(protocol_matches(b'garbage\n' + self.gps, 'gps'))
        self.assertTrue(protocol_matches(b'\xffgarbage' + self.imu, 'imu'))
        self.assertTrue(protocol_matches(b'\xff\xfb\xffnoise' + self.board, 'yahboom'))

    def test_unknown_role(self):
        with self.assertRaises(ValueError):
            protocol_matches(b'', 'unknown')

    def test_no_transmit_calls_in_discovery(self):
        source = Path(__file__).parents[1] / 'scripts' / 'atlas_usb_identity.py'
        tree = ast.parse(source.read_text(encoding='utf8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, ('write', 'send', 'sendall', 'setDTR', 'setRTS'))


@unittest.skipIf(sys.platform == 'win32', 'Linux flock transport tests run on Jetson')
class DiscoveryTests(unittest.TestCase):
    def exercise(self, streams, busy=()):
        created = []
        class Link:
            def __init__(self, **kwargs):
                self.closed = False
                self.timeout = kwargs['timeout']
                created.append(self)
            def open(self):
                pass
            def read(self, size):
                return streams[self.port]
            def close(self):
                self.closed = True
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict('os.environ', {'XDG_RUNTIME_DIR': folder}), \
             patch.dict(sys.modules, {'serial': SimpleNamespace(Serial=Link, SerialException=OSError)}), \
             patch('atlas_usb_identity.candidates', return_value=list(streams)), \
             patch('atlas_usb_identity.in_use', side_effect=lambda p: p in busy):
            try:
                result = open_verified('imu', duration=.002)
            except OSError:
                result = None
        return result, created

    def test_skips_owned_and_holds_verified_handle(self):
        good = (imu(0x51) + imu(0x52)) * 3
        result, links = self.exercise({'/dev/a': good, '/dev/b': good}, busy=('/dev/a',))
        self.assertEqual(len(links), 1)
        self.assertIs(result, links[0])
        self.assertFalse(result.closed)
        self.assertEqual(result.port, '/dev/b')

    def test_ambiguous_devices_closed(self):
        good = (imu(0x51) + imu(0x52)) * 3
        result, links = self.exercise({'/dev/a': good, '/dev/b': good})
        self.assertIsNone(result)
        self.assertTrue(all(x.closed for x in links))

    def test_invalid_stream_closed(self):
        result, links = self.exercise({'/dev/a': b'noise'})
        self.assertIsNone(result)
        self.assertTrue(links[0].closed)

    def test_missing_device_fails_closed(self):
        result, links = self.exercise({})
        self.assertIsNone(result)
        self.assertEqual(links, [])


if __name__ == '__main__':
    unittest.main()
