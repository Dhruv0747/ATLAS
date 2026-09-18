"""Offline regression tests: actual method bodies, no ROS or hardware I/O."""
import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock


class String:
    def __init__(self, data):
        self.data = data


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        source = Path(__file__).parents[1] / 'scripts/atlas_sensor_recovery.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AtlasRecovery')
        cls.bases = []
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name != '__init__']
        assignments = [n for n in tree.body if isinstance(n, ast.Assign) and
                       all(isinstance(t, ast.Name) and t.id not in ('MONITORS', 'GNSS_ENABLED', 'ULTRASONIC_ENABLED') for t in n.targets)]
        self.process = Mock()
        ns = {'json': json, 'math': math, 'String': String, 'NavSatFix': type('NavSatFix', (), {}),
              'time': SimpleNamespace(monotonic=lambda: self.now, sleep=Mock()),
              'subprocess': self.process, 'threading': Mock()}
        exec(compile(ast.Module(body=assignments + [cls], type_ignores=[]), str(source), 'exec'), ns)
        self.node = ns['AtlasRecovery']()
        self.node.last_seen = {'encoder_health': self.now}
        self.node.last_value = {'encoder_health': 'waiting'}
        self.node.attempts = {'encoder_health': []}
        self.node.last_notice = {'encoder_health': 0}
        self.node.recovering = {'encoder_health'}
        self.node.lock = threading.Lock()
        self.node.service_cache = {}
        self.node.service_active = Mock(return_value=True)
        self.node.publish_status = Mock()
        self.node.motion_active = False
        self.node.motion_last_seen = None
        self.node.motion_zero_since = None
        self.node.stop_latched = True
        self.node.stop_latch_seen = self.now
        self.item = SimpleNamespace(name='encoder_health', service='rover-base-telemetry.service',
                                    stale_after=2., stopped_only=True)

    def update(self, data):
        self.node.on_message('encoder_health', String(data))

    def zero(self):
        self.node.on_velocity(SimpleNamespace(linear=SimpleNamespace(x=0, y=0), angular=SimpleNamespace(z=0)))

    def settled(self):
        self.zero()
        for _ in range(6):
            self.now += .5
            self.zero()
        self.node.on_control_policy(String('{"stop_latched":true}'))

    def test_full_degraded_json_not_false_fault(self):
        data = json.dumps({'state': 'DEGRADED', 'faults': [], 'detail': 'x' * 600,
                           'selected': [1, 2, 3], 'excluded': [4], 'navigation_validated': False})
        self.update(data)
        self.assertEqual(self.node.last_value['encoder_health'], data)
        self.assertFalse(self.node.bad_status('encoder_health'))
        state, _, detail = self.node.classify(self.item, self.now)
        self.assertEqual(state, 'HEALTHY')  # recovery transport health, not autonomy readiness
        self.assertLessEqual(len(detail), 240)
        self.node.recover(self.item, 'old false fault', 1)
        self.process.run.assert_not_called()

    def test_malformed_unknown_and_critical_fail_closed(self):
        for data in ('{', 'null', '[]', 'true', '123', '{}',
                     '{"state":"CRITICAL"}', '{"state":"QUALIFYING"}', '{"state":"NEW_STATE"}'):
            with self.subTest(data=data):
                self.update(data)
                self.assertTrue(self.node.bad_status('encoder_health'))

    def test_oversize_bounded_and_faulted(self):
        self.update('x' * 20000)
        self.assertLess(len(self.node.last_value['encoder_health']), 100)
        self.assertTrue(self.node.bad_status('encoder_health'))

    def test_valid_but_stale_detected(self):
        self.update('{"state":"READY"}')
        self.assertEqual(self.node.classify(self.item, self.now + 3)[0], 'STALE')

    def test_stop_needs_fresh_sustained_command(self):
        self.assertFalse(self.node.stop_command_confirmed())
        self.zero()
        self.assertFalse(self.node.stop_command_confirmed())
        self.now += 2.1
        self.assertFalse(self.node.stop_command_confirmed())
        self.zero()
        self.assertFalse(self.node.stop_command_confirmed())
        self.settled()
        self.assertTrue(self.node.stop_command_confirmed())
        self.now += 1.1
        self.assertFalse(self.node.stop_command_confirmed())

    def test_motion_resets_settle_and_worker_does_not_restart(self):
        self.settled()
        self.node.on_velocity(SimpleNamespace(linear=SimpleNamespace(x=.1, y=0), angular=SimpleNamespace(z=0)))
        self.assertFalse(self.node.stop_command_confirmed())
        self.node.recover(self.item, 'fault', 1)
        self.process.run.assert_not_called()
        self.assertFalse(self.node.recovering)
        self.zero()
        self.assertFalse(self.node.stop_command_confirmed())

    def test_fresh_health_cancels_scheduled_restart(self):
        self.settled()
        self.update('{"state":"READY"}')
        self.node.recover(self.item, 'previous stale event', 1)
        self.process.run.assert_not_called()
        self.assertFalse(self.node.recovering)

    def test_invalid_command_not_stationary(self):
        self.settled()
        self.node.on_velocity(SimpleNamespace(linear=SimpleNamespace(x=math.nan, y=0), angular=SimpleNamespace(z=0)))
        self.assertFalse(self.node.stop_command_confirmed())

    def test_motor_restart_requires_fresh_latch(self):
        self.settled()
        self.assertTrue(self.node.restart_allowed(self.item))
        for payload in ('{"stop_latched":false}', 'null', '{', '{"stop_latched":"true"}'):
            self.node.on_control_policy(String(payload))
            self.assertFalse(self.node.restart_allowed(self.item))
        self.node.on_control_policy(String('{"stop_latched":true}'))
        self.now += 1.1
        self.zero()
        self.assertFalse(self.node.restart_allowed(self.item))

    def test_legitimate_fault_still_allows_bounded_recovery(self):
        self.settled()
        self.update('{"state":"CRITICAL"}')
        self.process.run.side_effect = lambda *a, **k: self.update('{"state":"READY"}')
        self.node.recover(self.item, 'genuine critical fault', 1)
        self.process.run.assert_called_once_with(
            ['systemctl', '--user', 'restart', 'rover-base-telemetry.service'], timeout=15, check=True)
        self.assertFalse(self.node.recovering)


if __name__ == '__main__':
    unittest.main()
