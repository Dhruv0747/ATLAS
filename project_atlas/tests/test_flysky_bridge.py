import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import atlas_flysky_core as C   # noqa: E402
import atlas_rc_readonly_bridge as B   # noqa: E402


class PortChecks(unittest.TestCase):
    def test_refuses_bare_tty_and_ambiguous_ch340(self):
        for p in ('/dev/ttyUSB1', '/dev/ttyUSB2', '/dev/ttyACM0', 'ttyUSB0', '/dev/serial/by-path/pci-0:1',
                  '/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0', '/dev/serial/by-id/usb-QinHeng_CH340-if00', '/dev/serial/by-id/../../ttyUSB1'):
            with self.assertRaises(B.PortRefused, msg=p):
                B.check_port(p, lambda d: False)

    def test_refuses_missing_and_busy_ports(self):
        with self.assertRaises(B.PortRefused):
            B.check_port('/dev/serial/by-id/usb-FTDI_FT232R_UNIQUE123-if00-port0', lambda d: False)    # does not exist here
        self.assertTrue(B.BY_ID.match('/dev/serial/by-id/usb-FTDI_FT232R_A50285BI-if00-port0'))


class Forwarding(unittest.TestCase):
    def frames(self, n, **kw):
        return b''.join(C.encode_sbus([992 + k] * 16, **kw) for k in range(n))

    def test_rate_limited_to_20hz_but_flag_change_is_immediate(self):
        out = []; f = B.FrameForwarder('sbus')
        for k in range(300):                           # 100 Hz of valid frames for 3 s
            f.feed(C.encode_sbus([992] * 16), k * 0.01, 0.0, out.append)
        self.assertLessEqual(len(out), 3 * 20 + 2); self.assertGreater(len(out), 40); self.assertGreater(f.dropped_rate, 0)
        n = len(out); f.feed(C.encode_sbus([992] * 16, failsafe=True), 3.001, 0.0, out.append)
        self.assertEqual(len(out), n + 1)             # flag change forwarded at once

    def test_only_valid_frames_are_published_and_roundtrip(self):
        out = []; f = B.FrameForwarder('sbus')
        f.feed(b'\x01\x02\x03' + C.encode_sbus([172, 992, 1811] + [992] * 13) + b'\x0f' + b'\x55' * 10, 1.0, 0.0, out.append)
        self.assertEqual(len(out), 1); m = out[0]; self.assertEqual(set(m), {'proto', 'hex', 'seq'})
        fr = C.decode_sbus(bytes.fromhex(m['hex'])); self.assertEqual(fr.raw[:3], (172, 992, 1811))

    def test_ibus_forwarding(self):
        out = []; f = B.FrameForwarder('ibus'); f.feed(C.encode_ibus([1000, 1500, 2000]), 1.0, 0.0, out.append)
        self.assertEqual(C.decode_ibus(bytes.fromhex(out[0]['hex'])).raw[:3], (1000, 1500, 2000))


class ReadOnlyBySource(unittest.TestCase):
    SRC = re.sub(r'"""[\s\S]*?"""', '', (SCRIPTS / 'atlas_rc_readonly_bridge.py').read_text(), count=1)

    def test_never_writes_to_the_port_and_has_one_publisher(self):
        for bad in ('.write(', 'ser.write', 'flush(', 'create_client', 'create_service', 'ActionClient', 'geometry_msgs', 'Twist', 'cmd_vel',
                    'estop', 'e_stop', 'yahboom', 'Rosmaster', 'ttyUSB1', 'create_subscription', 'os.system', 'subprocess'):
            self.assertNotIn(bad, self.SRC, bad)
        self.assertEqual(self.SRC.count('create_publisher'), 1)
        self.assertEqual(self.SRC.count("TOPIC = '/atlas/rc/frames'"), 1)


if __name__ == '__main__':
    unittest.main()
