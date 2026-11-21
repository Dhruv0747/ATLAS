"""Offline regression checks for the UNO bridge polling cadence and safety."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'ultrasonic_arduino_bridge.py'
sys.path.insert(0, str(ROOT / 'scripts'))

from atlas_serial_lines import SerialLines


def bridge_tree():
    return ast.parse(SCRIPT.read_text(encoding='utf-8'))


def poll_seconds():
    assignment = next(
        node for node in bridge_tree().body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name)
                and target.id == 'SENSOR_HUB_POLL_SECONDS'
                for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


def extracted_tick(clock):
    tree = bridge_tree()
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef)
               and node.name == 'UltrasonicArduinoBridge')
    method = next(node for node in cls.body
                  if isinstance(node, ast.FunctionDef) and node.name == 'tick')
    scope = {
        'time': clock,
        'json': json,
        'String': lambda **kwargs: NS(**kwargs),
        'SERIAL_STALE_REOPEN_SECONDS': 8.0,
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]),
                 str(SCRIPT), 'exec'), scope)
    return scope['tick']


def bridge_fixture(serial_port, clock):
    now_mono = clock.monotonic()
    return NS(
        ser=serial_port,
        rx_lines=SerialLines(),
        rx_high_water=0,
        rx_processed=0,
        rx_diag_time=now_mono,
        validity_last_frame=now_mono,
        validity_last_invalid=now_mono,
        validity_pending=None,
        last_serial_rx=clock.time(),
        last_ok=clock.time(),
        last_wait_status=0.0,
        next_connect_attempt=0.0,
        flush_dashboard_cache=Mock(),
        read_local_camera_commands=Mock(),
        invalidate_ultrasonic=Mock(),
        publish_ultrasonic_validity=Mock(),
        handle_line=Mock(),
        connect=Mock(),
        status_pub=Mock(),
        rx_diag_pub=Mock(),
    )


class UnoBridgePollingTests(unittest.TestCase):
    def test_timer_uses_25_hz_policy(self):
        tree = bridge_tree()
        cls = next(node for node in tree.body
                   if isinstance(node, ast.ClassDef)
                   and node.name == 'UltrasonicArduinoBridge')
        init = next(node for node in cls.body
                    if isinstance(node, ast.FunctionDef) and node.name == '__init__')
        timers = [node for node in ast.walk(init)
                  if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute)
                  and node.func.attr == 'create_timer']
        self.assertEqual(poll_seconds(), 0.04)
        self.assertTrue(any(
            isinstance(call.args[0], ast.Name)
            and call.args[0].id == 'SENSOR_HUB_POLL_SECONDS'
            and isinstance(call.args[1], ast.Attribute)
            and call.args[1].attr == 'tick'
            for call in timers
        ))

    def test_one_tick_still_drains_immediate_serial_burst(self):
        class Port:
            def __init__(self):
                self.data = b''.join(
                    f'ACK,{index}\n'.encode() for index in range(64))

            @property
            def in_waiting(self):
                return len(self.data)

            def read(self, size):
                chunk, self.data = self.data[:size], self.data[size:]
                return chunk

        clock = NS(monotonic=lambda: 10.0, time=lambda: 1000.0)
        port = Port()
        bridge = bridge_fixture(port, clock)
        tick = extracted_tick(clock)

        tick(bridge)

        self.assertEqual(port.data, b'')
        self.assertEqual(bridge.handle_line.call_count, 64)
        self.assertEqual(bridge.rx_processed, 64)

    def test_offline_tick_keeps_camera_expiry_and_reconnect_checks(self):
        clock = NS(monotonic=lambda: 10.0, time=lambda: 1000.0)
        bridge = bridge_fixture(None, clock)
        bridge.validity_last_frame = 8.0
        bridge.validity_last_invalid = 8.0

        extracted_tick(clock)(bridge)

        bridge.invalidate_ultrasonic.assert_called_once_with(
            'MISSING_UVALID1_FIRMWARE_OR_STALE')
        bridge.read_local_camera_commands.assert_called_once_with()
        bridge.connect.assert_called_once_with()
        self.assertEqual(bridge.next_connect_attempt, 12.0)

    def test_complete_parser_backlog_remains_fail_closed(self):
        clock = NS(monotonic=lambda: 10.0, time=lambda: 1000.0)
        port = NS(in_waiting=0)
        bridge = bridge_fixture(port, clock)
        bridge.validity_pending = ('UVALID1,held', 9.9)
        bridge.rx_lines.feed(b'queued_complete_line\n' * 129 + b'partial')

        extracted_tick(clock)(bridge)

        bridge.invalidate_ultrasonic.assert_called_once_with('SERIAL_BACKLOG')
        self.assertEqual(bridge.validity_pending, ('UVALID1,held', 9.9))


if __name__ == '__main__':
    unittest.main()
