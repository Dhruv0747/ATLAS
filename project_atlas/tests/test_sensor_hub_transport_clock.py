"""Execute the actual bridge tick without ROS/USB; wall time may jump at boot."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

SOURCE = Path(__file__).parents[1] / 'scripts/ultrasonic_arduino_bridge.py'


def tick_from(source, clock):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'UltrasonicArduinoBridge')
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'tick')
    scope = {'time': clock, 'SERIAL_STALE_REOPEN_SECONDS': 8., 'String': lambda **kw: NS(**kw)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), 'exec'), scope)
    return scope['tick']


class ClockTests(unittest.TestCase):
    def node(self, mono, wall):
        self.clock = NS(monotonic=lambda: mono, time=lambda: wall)
        self.ser = NS(in_waiting=0, close=Mock())
        return NS(ser=self.ser, validity_last_frame=mono, validity_last_invalid=mono,
                  flush_dashboard_cache=Mock(), read_local_camera_commands=Mock(),
                  rx_lines=NS(pop=lambda: None, data=b''), rx_high_water=0,
                  rx_processed=0, validity_pending=None, rx_diag_time=mono,
                  last_serial_rx=1000., last_serial_rx_mono=0., last_ok=wall,
                  last_wait_status=wall, status_pub=NS(publish=Mock()),
                  invalidate_ultrasonic=Mock())

    def test_backward_wall_step_does_not_delay_stale_reopen(self):
        node = self.node(9., 900.)
        tick_from(SOURCE.read_text(encoding='utf-8'), self.clock)(node)
        self.ser.close.assert_called_once()
        self.assertIsNone(node.ser)

    def test_forward_wall_step_does_not_reset_live_transport(self):
        node = self.node(1., 2000.)
        tick_from(SOURCE.read_text(encoding='utf-8'), self.clock)(node)
        self.ser.close.assert_not_called()
        self.assertIs(node.ser, self.ser)

    def test_normal_monotonic_deadline_unchanged(self):
        for mono, expected in ((7.999, False), (8., True), (8.1, True)):
            with self.subTest(mono=mono):
                node = self.node(mono, 1000.+mono)
                tick_from(SOURCE.read_text(encoding='utf-8'), self.clock)(node)
                self.assertEqual(self.ser.close.called, expected)

    def test_connect_and_receive_store_monotonic_not_wall(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        stores = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Attribute) and t.attr == 'last_serial_rx_mono' for t in n.targets)]
        self.assertGreaterEqual(len(stores), 4)
        for store in stores:
            if isinstance(store.value, ast.Constant): continue
            self.assertEqual(ast.unparse(store.value), 'time.monotonic()')


if __name__ == '__main__': unittest.main()
