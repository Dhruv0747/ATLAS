"""Offline only: pure helpers and extracted methods, no ROS/hardware imports."""
import ast
import copy
import json
import itertools
import math
import re
import uuid
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from atlas_ultrasonic_validity import parse_frame, invalid_snapshot, ValidityWindow
from atlas_serial_lines import SerialLines


def report(now=10.0, seq=1, front=1000, rear=1000, age=20, uptime=None, stream='test'):
    return parse_frame(f'UVALID1,T={int(now * 1000) if uptime is None else uptime},'
                       f'F=1:{front}:{seq}:{age},L=0:-1:0:-1,R=0:-1:0:-1,B=1:{rear}:{seq}:{age}',
                       stream, now)


class ValidityTests(unittest.TestCase):
    def setUp(self):
        self.window = ValidityWindow()

    def test_valid_report_and_disabled_sides(self):
        self.window.ingest(report(), 10)
        self.assertEqual(self.window.reading('front', 10), (1.0, 'VALID'))
        self.assertEqual(self.window.reading('left', 10), (None, 'DISABLED'))
        self.assertIsNone(self.window.veto(.1, .2, 10, .3, .3, .28))

    def test_missing_blocks_both_directions(self):
        for speed, side in ((.1, 'FRONT'), (-.1, 'REAR')):
            self.assertIn(side, self.window.veto(speed, 0, 10, .3, .3, .28))

    def test_no_echo_clears_previous_good_immediately(self):
        self.window.ingest(report(), 10)
        self.window.ingest(report(10.25, 2, front=-1), 10.25)
        self.assertEqual(self.window.reading('front', 10.25), (None, 'NO_ECHO'))
        self.assertIn('NO_ECHO', self.window.veto(.1, 0, 10.25, .3, .3, .28))
        self.assertIsNone(self.window.veto(-.1, 0, 10.25, .3, .3, .28))

    def test_range_limits(self):
        for value in (-2, 0, 19, 4201, 10000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                report(front=value)
        for value in (20, 4200):
            self.assertEqual(report(front=value)['sensors']['front']['range_mm'], value)

    def test_malformed_frames_rejected(self):
        for text in ('STUB,F=4000', 'UVALID1', 'UVALID1,T=-1,F=1:20:1:0,L=0:-1:0:-1,R=0:-1:0:-1,B=1:20:1:0',
                     'UVALID1,T=1,F=1:20:1:0,F=1:20:1:0,R=0:-1:0:-1,B=1:20:1:0'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_frame(text, 'test', 10)

    def test_report_and_source_age_both_expire(self):
        self.window.ingest(report(), 10)
        self.assertEqual(self.window.reading('rear', 11.1)[1], 'STALE_REPORT')
        self.window.ingest(report(11.2, 2, age=1500), 11.2)
        self.assertEqual(self.window.reading('front', 11.2)[1], 'STALE_SAMPLE')

    def test_repeated_sample_does_not_renew_lease(self):
        self.window.ingest(report(), 10)
        for now in (10.5, 11.0, 11.5):
            self.window.ingest(report(now, 1, age=0), now)
        self.assertEqual(self.window.reading('front', 11.5)[1], 'STALE_SAMPLE')

    def test_changed_value_same_sequence_is_invalid(self):
        self.window.ingest(report(), 10)
        self.window.ingest(report(10.25, 1, front=1500), 10.25)
        self.assertEqual(self.window.reading('front', 10.25)[1], 'SAMPLE_CHANGED_WITHOUT_SEQUENCE')

    def test_replay_and_out_of_order_rejected(self):
        for earlier in (report(), report(9.9), report(10.2, seq=0)):
            self.window = ValidityWindow()
            self.window.ingest(report(), 10)
            self.window.ingest(earlier, 10.2)
            self.assertIsNone(self.window.reading('front', 10.2)[0])

    def test_bad_envelope_and_missing_channels_clear_old_data(self):
        for field, value in (('source', 'stub'), ('host_monotonic_s', float('nan')),
                             ('host_monotonic_s', float('inf')), ('host_monotonic_s', 11),
                             ('host_monotonic_s', 8), ('sensors', {}), ('sensors', None),
                             ('schema_version', 2), ('stream_id', '')):
            with self.subTest(field=field, value=value):
                self.window = ValidityWindow()
                self.window.ingest(report(), 10)
                bad = report(10.25, 2)
                bad[field] = value
                self.window.ingest(bad, 10.25)
                self.assertIsNone(self.window.reading('front', 10.25)[0])

    def test_bad_numeric_samples(self):
        for field, value in (('range_mm', float('inf')), ('range_mm', True),
                             ('range_mm', -1), ('range_mm', 0), ('sample_age_s', -1),
                             ('sample_age_s', float('nan')), ('sample_sequence', True)):
            with self.subTest(field=field, value=value):
                bad = report()
                bad['sensors']['front'][field] = value
                self.window.ingest(bad, 10)
                self.assertIsNone(self.window.reading('front', 10)[0])

    def test_usb_delay_relative_to_mcu_clock_is_not_fresh(self):
        self.window.ingest(report(), 10)
        self.window.ingest(report(12, 2, uptime=10250), 12)
        self.assertEqual(self.window.reading('front', 12)[1], 'STALE_SAMPLE')

    def test_mcu_clock_reset_requires_new_stream(self):
        self.window.ingest(report(), 10)
        self.window.ingest(report(10.25, 2, uptime=200), 10.25)
        self.assertEqual(self.window.reading('front', 10.25)[1], 'MCU_CLOCK_RESET')
        self.window.ingest(report(10.5, 1, uptime=450, stream='new'), 10.5)
        self.assertEqual(self.window.reading('front', 10.5)[1], 'VALID')

    def test_read_error_and_legacy_firmware_fail_closed(self):
        for reason in ('SERIAL_READ_ERROR', 'SERIAL_BACKLOG', 'MISSING_UVALID1_FIRMWARE_OR_STALE'):
            self.window.ingest(report(), 10)
            self.window.ingest(invalid_snapshot(reason, 'test', 10.2), 10.2)
            self.assertEqual(self.window.reading('front', 10.2), (None, reason))

    def test_direction_and_inclusive_stop_boundary(self):
        self.window.ingest(report(front=300, rear=250), 10)
        self.assertIn('FRONT', self.window.veto(.1, 0, 10, .3, .3, .28))
        self.assertIn('REAR', self.window.veto(-.1, 0, 10, .3, .3, .28))
        self.assertIsNone(self.window.veto(0, 0, 10, .3, .3, .28))

    def test_side_veto_uses_validated_echo_only(self):
        d = report()
        d['sensors']['left'] = dict(d['sensors']['front'], range_mm=200)
        self.window.ingest(d, 10)
        self.assertIn('LEFT', self.window.veto(.1, .1, 10, .3, .3, .28))
        self.assertIsNone(self.window.veto(.1, -.1, 10, .3, .3, .28))

    def test_future_time_at_read_and_bad_timeout(self):
        self.window.ingest(report(), 10)
        self.assertIsNone(self.window.reading('front', 9)[0])
        for timeout in (0, -1, float('nan'), 3):
            with self.assertRaises(ValueError):
                ValidityWindow(timeout)

    def test_schema_is_strict_json(self):
        json.dumps(report(), allow_nan=False)

    def test_nonfinite_command_or_limit_fails_closed(self):
        self.window.ingest(report(), 10)
        for args in ((math.nan, 0, 10, .3, .3, .28), (.1, 0, 10, math.inf, .3, .28), (.1, 0, 10, 0, .3, .28)):
            self.assertIn('INVALID', self.window.veto(*args))


def extracted_class(filename, name, methods):
    """Compile only chosen method bodies, never execute a driver module."""
    tree = ast.parse((ROOT / 'scripts' / filename).read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    cls.bases, cls.decorator_list = [], []
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    scope = dict(time=NS(monotonic=lambda: 10.0, time=lambda: 1000.0), math=math, json=json,
                 parse_frame=parse_frame, invalid_snapshot=invalid_snapshot, uuid=uuid,
                 SERIAL_STALE_REOPEN_SECONDS=8,
                 Float32=object, String=NS, Twist=lambda: NS(linear=NS(x=0), angular=NS(z=0)),
                 Optional=__import__('typing').Optional)
    if filename == 'ultrasonic_arduino_bridge.py':
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'LINE_RE' for t in n.targets))
        scope['re'] = re
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), filename, 'exec'), scope)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), filename, 'exec'), scope)
    return scope[name]


class MuxIntegrationTests(unittest.TestCase):
    def setUp(self):
        cls = extracted_class('atlas_cmd_vel_mux.py', 'AtlasCmdVelMux',
                              {'on_ultrasonic', 'on_ultrasonic_validity', 'autonomous_guard', 'watchdog'})
        self.mux = cls()
        self.mux.ultrasonic = dict.fromkeys(('front', 'left', 'right', 'rear'), math.inf)
        self.mux.ultrasonic_rx = dict.fromkeys(self.mux.ultrasonic, 0)
        self.mux.ultrasonic_validity = ValidityWindow()
        self.mux.ultrasonic_enabled = True
        self.mux.auto_front_stop_m = self.mux.auto_rear_stop_m = .3
        self.mux.auto_side_stop_m = .28
        self.mux.auto_reaction_time_s = 1
        self.mux.auto_stop_margin_m = .15
        self.command = NS(linear=NS(x=.1), angular=NS(z=0))

    def test_bare_positive_float_never_grants_authority(self):
        self.mux.on_ultrasonic('front', NS(data=4000))
        self.assertIn('MISSING', self.mux.autonomous_guard(self.command, 10))
        m = self.mux
        m.remote_stop, m.active_name = NS(check=lambda _: False), None
        m.encoder_health_rx, m.encoder_health = 10, {'state': 'HEALTHY', 'autonomy_ready': True}
        m.localization_guard = lambda _: None
        m.output, m.safety_output = Mock(), Mock()
        m.get_logger = lambda: NS(error=Mock())
        m.last_blocked_reason = None
        for source in ('NAV2', 'RECOVERY'):
            m.active_name = None
            m.live_channel = lambda _: NS(name=source, command=self.command)
            m.watchdog()
            sent = m.output.publish.call_args.args[0]
            self.assertEqual((sent.linear.x, sent.angular.z), (0, 0))
            self.assertIn('MISSING', m.safety_output.publish.call_args.args[0].data)

    def test_invalid_raw_clears_previous_numeric_cache(self):
        for value in (-1, 0, math.inf, math.nan):
            self.mux.on_ultrasonic('front', NS(data=1000))
            self.mux.on_ultrasonic('front', NS(data=value))
            self.assertEqual(self.mux.ultrasonic_rx['front'], 0)

    def test_atomic_json_drives_guard_and_malformed_clears(self):
        self.mux.on_ultrasonic_validity(NS(data=json.dumps(report())))
        self.assertIsNone(self.mux.autonomous_guard(self.command, 10))
        for invalid in ('{', 'null', '[]', '{}'):
            self.mux.on_ultrasonic_validity(NS(data=invalid))
            self.assertIsNotNone(self.mux.autonomous_guard(self.command, 10))

    def test_speed_margin_retained(self):
        self.mux.on_ultrasonic_validity(NS(data=json.dumps(report(front=500))))
        self.command.linear.x = .4
        self.assertIn('stop 0.55 m', self.mux.autonomous_guard(self.command, 10))

    def test_latched_remote_stop_preempts_sensor_processing(self):
        self.mux.remote_stop = NS(check=lambda _: True)
        self.mux.hold_remote_stop = Mock()
        self.mux.watchdog()
        self.mux.hold_remote_stop.assert_called_once_with()
        # Once the existing deliberate release has happened, manual remote
        # routing is unchanged and does not require an autonomous echo contract.
        self.mux.remote_stop = NS(check=lambda _: False)
        self.mux.active_name = None
        self.mux.live_channel = lambda _: NS(name='REMOTE', command=self.command)
        self.mux.copy_twist = copy.deepcopy
        self.mux.radar_gate_enabled = False
        self.mux.publish = Mock()
        self.mux.watchdog()
        self.assertEqual(self.mux.publish.call_args.args[0].linear.x, .1)


class BridgeIntegrationTests(unittest.TestCase):
    def setUp(self):
        cls = extracted_class('ultrasonic_arduino_bridge.py', 'UltrasonicArduinoBridge',
                              {'tick', 'handle_line', 'publish_ultrasonic_validity', 'invalidate_ultrasonic'})
        self.bridge = cls()
        b = self.bridge
        b.validity_stream, b.validity_last_frame, b.validity_last_invalid = 'test', 10, 10
        b.validity_pending = None
        b.flush_dashboard_cache, b.read_local_camera_commands, b.dashboard_cache_set = Mock(), Mock(), Mock()
        b.validity_pub, b.status_pub, b.rx_diag_pub = Mock(), Mock(), Mock()
        b.ser = NS(in_waiting=0)
        b.rx_lines = NS(data=b'', pop=lambda: None)
        b.rx_high_water = b.rx_processed = 0
        b.rx_diag_time, b.last_serial_rx, b.last_ok = 10, 1000, 1000

    def published(self):
        return json.loads(self.bridge.validity_pub.publish.call_args.args[0].data)

    def frame(self):
        return 'UVALID1,T=10000,F=1:500:1:20,L=0:-1:0:-1,R=0:-1:0:-1,B=1:500:1:20'

    def test_firmware_line_to_ros_contract(self):
        self.bridge.handle_line(self.frame())
        self.bridge.tick()
        payload = self.published()
        window = ValidityWindow()
        window.ingest(payload, 10)
        self.assertEqual(window.reading('front', 10), (.5, 'VALID'))
        self.bridge.dashboard_cache_set.assert_called_with('us_validity', self.bridge.validity_pub.publish.call_args.args[0].data)

    def test_parser_backlog_not_fresh_safety(self):
        self.bridge.handle_line(self.frame())
        self.bridge.rx_lines.data = b'queued_complete_line\npartial'
        self.bridge.tick()
        self.assertEqual(self.published()['reason'], 'SERIAL_BACKLOG')
        self.assertIsNotNone(self.bridge.validity_pending)

    def test_trailing_partial_line_does_not_revoke_complete_report(self):
        self.bridge.handle_line(self.frame())
        self.bridge.rx_lines.data = b'RADARHEX,AAFF'
        self.bridge.tick()
        self.assertEqual(self.published()['reason'], 'SAMPLE_REPORT')
        self.assertIsNone(self.bridge.validity_pending)
        self.assertEqual(self.bridge.rx_lines.data, b'RADARHEX,AAFF')
        window = ValidityWindow()
        window.ingest(self.published(), 10)
        self.assertEqual(window.reading('front', 10), (.5, 'VALID'))
        self.assertEqual(window.reading('front', 11.1)[1], 'STALE_REPORT')

    def test_usb_bytes_arriving_during_parse_still_block(self):
        class Serial:
            @property
            def in_waiting(self):
                self.reads += 1
                return 0 if self.reads == 1 else 30
            reads = 0
        self.bridge.ser = Serial()
        self.bridge.handle_line(self.frame())
        self.bridge.tick()
        self.assertEqual(self.published()['reason'], 'SERIAL_BACKLOG')
        self.assertIsNotNone(self.bridge.validity_pending)

    def test_draining_backlog_never_restamps_held_report(self):
        self.bridge.validity_pending = (self.frame(), 8.0)
        self.bridge.rx_lines.data = b'RADARHEX,AAFF'
        self.bridge.tick()
        self.assertEqual(self.published()['host_monotonic_s'], 8.0)
        window = ValidityWindow()
        window.ingest(self.published(), 10)
        self.assertEqual(window.reading('front', 10)[1], 'INVALID_OR_STALE_ENVELOPE')

    def test_new_bytes_drain_within_same_tick(self):
        chunks = [(self.frame() + '\n').encode(), b'\n']
        class Serial:
            @property
            def in_waiting(self):
                return len(chunks[0]) if chunks else 0
            def read(self, size):
                chunk = chunks.pop(0)
                self.assert_size = size
                return chunk
        self.bridge.ser = Serial()
        self.bridge.rx_lines = SerialLines()
        self.bridge.tick()
        self.assertEqual(chunks, [])
        self.assertEqual(self.published()['reason'], 'SAMPLE_REPORT')
        self.assertEqual(self.bridge.rx_processed, 2)

    def test_continuous_bytes_cannot_exceed_per_tick_byte_budget(self):
        class Serial:
            in_waiting = 100000
            read_sizes = []
            def read(self, size):
                self.read_sizes.append(size)
                return b'x' * size
        self.bridge.ser = Serial()
        self.bridge.rx_lines = SerialLines()
        self.bridge.handle_line(self.frame())
        self.bridge.tick()
        self.assertEqual(sum(self.bridge.ser.read_sizes), 8192)
        self.assertEqual(self.published()['reason'], 'SERIAL_BACKLOG')

    def test_complete_lines_cannot_exceed_per_tick_line_budget(self):
        self.bridge.rx_lines = SerialLines()
        self.bridge.rx_lines.feed(b'\n' * 200)
        self.bridge.handle_line(self.frame())
        self.bridge.tick()
        self.assertEqual(self.bridge.rx_processed, 128)
        self.assertEqual(self.bridge.rx_lines.data.count(b'\n'), 72)
        self.assertEqual(self.published()['reason'], 'SERIAL_BACKLOG')

    def test_empty_read_does_not_spin_on_reported_waiting_bytes(self):
        self.bridge.ser = NS(in_waiting=50, read=Mock(return_value=b''))
        self.bridge.rx_lines = SerialLines()
        self.bridge.handle_line(self.frame())
        self.bridge.tick()
        self.bridge.ser.read.assert_called_once_with(50)
        self.assertEqual(self.published()['reason'], 'SERIAL_BACKLOG')

    def test_time_budget_leaves_backlog_blocked(self):
        clock = itertools.chain([10.0, 10.0, 10.004], itertools.repeat(10.010))
        self.bridge.tick.__func__.__globals__['time'] = NS(
            monotonic=lambda: next(clock), time=lambda: 1000.0)
        self.bridge.rx_lines = SerialLines()
        self.bridge.rx_lines.feed(b'\n' * 20)
        self.bridge.validity_pending = (self.frame(), 10.0)
        self.bridge.tick()
        self.assertEqual(self.bridge.rx_processed, 1)
        self.assertEqual(self.bridge.rx_lines.data.count(b'\n'), 19)
        self.assertEqual(self.published()['reason'], 'SERIAL_BACKLOG')

    def test_malformed_line_invalidates(self):
        self.bridge.handle_line('UVALID1,bad')
        self.bridge.tick()
        self.assertEqual(self.published()['reason'], 'MALFORMED_UVALID1')

    def test_firmware_without_contract_never_falls_back_to_old_range(self):
        self.bridge.validity_last_frame = self.bridge.validity_last_invalid = 0
        self.bridge.tick()
        self.assertEqual(self.published()['reason'], 'MISSING_UVALID1_FIRMWARE_OR_STALE')

    def test_banner_invalidates_old_stream(self):
        self.bridge.handle_line('ATLAS_UNO_R4_WIFI_I2C_HUB')
        self.assertNotEqual(self.bridge.validity_stream, 'test')
        self.assertEqual(self.published()['reason'], 'MCU_RESTART')

    def test_legacy_bad_ok_bit_clears_numeric_ranges(self):
        b = self.bridge
        b.hub_transport = 'uno_r4_i2c_hub'
        b.front_pub, b.left_pub, b.right_pub, b.rear_pub = 'F', 'L', 'R', 'B'
        b.publish_mm = Mock()
        b.handle_line('F=500,L=600,R=700,B=800,OK=0')
        self.assertEqual([c.args for c in b.publish_mm.call_args_list], [('F', -1), ('L', -1), ('R', -1), ('B', -1)])


if __name__ == '__main__':
    unittest.main()
