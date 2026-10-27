"""Offline regression tests: actual method bodies, no ROS or hardware I/O."""
import ast
from contextlib import nullcontext
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
        source_text = source.read_text(encoding='utf-8')
        tree = ast.parse(source_text)
        self.source_tree = ast.parse(source_text)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AtlasRecovery')
        cls.bases = []
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name != '__init__']
        assignments = [n for n in tree.body if isinstance(n, ast.Assign) and
                       all(isinstance(t, ast.Name) and t.id not in ('MONITORS', 'GNSS_ENABLED', 'ULTRASONIC_ENABLED') for t in n.targets)]
        self.process = Mock()
        ns = {'json': json, 'math': math, 'String': String, 'NavSatFix': type('NavSatFix', (), {}),
              'time': SimpleNamespace(monotonic=lambda: self.now, sleep=Mock()),
              'subprocess': self.process, 'threading': Mock(), 'nullcontext': nullcontext,
              'Interlock': lambda: SimpleNamespace(recovery_dispatch=nullcontext)}
        exec(compile(ast.Module(body=assignments + [cls], type_ignores=[]), str(source), 'exec'), ns)
        self.ns = ns
        self.node = ns['AtlasRecovery']()
        self.node.last_seen = {'encoder_health': self.now}
        self.node.last_value = {'encoder_health': 'waiting'}
        self.node.attempts = {'encoder_health': []}
        self.node.last_notice = {'encoder_health': 0}
        self.node.recovering = {'encoder_health'}
        self.node.lock = threading.Lock()
        self.node.service_cache = {}
        self.node.service_active = Mock(return_value=True)
        self.node.restart_pending = Mock(return_value=False)
        self.node.publish_status = Mock()
        self.node.motion_active = False
        self.node.motion_last_seen = None
        self.node.motion_zero_since = None
        self.node.stop_latched = True
        self.node.stop_latch_seen = self.now
        self.item = SimpleNamespace(name='encoder_health', service='rover-base-telemetry.service',
                                    stale_after=2., stopped_only=True)

    def test_base_dispatch_interlock_denial_preserves_fault_reporting(self):
        from contextlib import contextmanager
        @contextmanager
        def denied():
            raise RuntimeError('B1 maintenance held')
            yield
        self.ns['Interlock'] = lambda: SimpleNamespace(recovery_dispatch=denied)
        self.node.restart_allowed = Mock(return_value=True)
        self.node.classify = Mock(return_value=('FAULT', 4, 'test'))
        self.node.maintenance_hold = Mock(return_value=False)
        self.node.bms_retry_owned = Mock(return_value=False)
        self.node.recover(self.item, 'test', 1)
        self.process.run.assert_not_called()
        self.assertIn('B1 maintenance held', self.node.publish_status.call_args[0][0])

    def test_unrelated_restart_does_not_enter_b1_gate(self):
        self.ns['Interlock'] = Mock(side_effect=AssertionError('unrelated service gated'))
        self.item.service = 'fake-unrelated.service'
        self.node.restart_allowed = Mock(return_value=True)
        self.node.classify = Mock(return_value=('FAULT', 4, 'test'))
        self.node.maintenance_hold = Mock(return_value=False)
        self.node.bms_retry_owned = Mock(return_value=False)
        self.node.bad_status = Mock(return_value=False)
        self.node.recover(self.item, 'test', 1)
        self.ns['Interlock'].assert_not_called()
        self.process.run.assert_called_once()

    def update(self, data):
        self.node.on_message('encoder_health', String(data))

    def bms_setup(self):
        item = SimpleNamespace(name='bms', service='rover-daly-bms.service', stale_after=15.)
        self.node.last_seen['bms'] = self.now
        self.node.last_value['bms'] = json.dumps({'ok': False,
            'retry_owner': 'daly_transport_v1', 'reconnect_in_s': 120})
        self.node.last_notice['bms'] = 0
        return item

    def test_bms_owned_retry_stays_fault_without_restart(self):
        item = self.bms_setup()
        self.assertTrue(self.node.bad_status('bms'))
        self.node.schedule_recovery(item, 'offline')
        self.ns['threading'].Thread.assert_not_called()
        self.process.run.assert_not_called()

    def test_bms_stale_or_invalid_ownership_not_exempt(self):
        item = self.bms_setup()
        self.assertTrue(self.node.bms_retry_owned(item, self.now))
        self.assertFalse(self.node.bms_retry_owned(item, self.now + 16))
        self.assertFalse(self.node.bms_retry_owned(item, self.now - 1))
        for value in (None, True, -1, 121, float('nan'), '10'):
            self.node.last_value['bms'] = json.dumps({'retry_owner': 'daly_transport_v1', 'reconnect_in_s': value})
            self.assertFalse(self.node.bms_retry_owned(item, self.now))
        for value in ('[]', 'broken', '{}'):
            self.node.last_value['bms'] = value
            self.assertFalse(self.node.bms_retry_owned(item, self.now))

    def test_retry_ownership_never_exempts_motor_service(self):
        item = self.bms_setup()
        item.service = 'rover-base-telemetry.service'
        self.assertFalse(self.node.bms_retry_owned(item, self.now))

    def test_worker_rechecks_bms_ownership(self):
        item = self.bms_setup()
        self.node.restart_allowed = Mock(return_value=True)
        self.node.classify = Mock(return_value=('FAULT', 0, 'offline'))
        self.node.recover(item, 'queued before heartbeat', 3)
        self.process.run.assert_not_called()

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

    def test_only_freshness_only_payloads_use_raw_transport(self):
        self.assertEqual(
            self.ns['RAW_FRESHNESS_MONITORS'],
            frozenset({
                'lidar', 'camera', 'imu', 'odometry', 'wheel_odometry',
                'encoder_fl', 'map',
            }),
        )
        init = next(
            node for node in next(
                node for node in self.source_tree.body
                if isinstance(node, ast.ClassDef) and node.name == 'AtlasRecovery'
            ).body
            if isinstance(node, ast.FunctionDef) and node.name == '__init__'
        )
        subscription_calls = [
            node for node in ast.walk(init)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'create_subscription'
        ]
        monitor_call = next(
            call for call in subscription_calls
            if call.args and isinstance(call.args[0], ast.Attribute)
            and call.args[0].attr == 'msg_type'
        )
        raw_keyword = next(
            keyword for keyword in monitor_call.keywords if keyword.arg == 'raw'
        )
        self.assertEqual(
            ast.unparse(raw_keyword.value),
            'item.name in RAW_FRESHNESS_MONITORS',
        )

    def test_raw_arrival_keeps_exact_freshness_semantics(self):
        self.node.last_seen['camera'] = self.now - 100.0
        self.node.last_value['camera'] = 'waiting'
        self.node.attempts['camera'] = []
        self.node.on_message('camera', b'opaque serialized payload')
        self.assertEqual(self.node.last_seen['camera'], self.now)
        self.assertEqual(self.node.last_value['camera'], 'data received')

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

    def test_latched_saved_map_does_not_become_falsely_stale(self):
        self.node.last_seen['map'] = self.now
        self.node.last_value['map'] = '187x218 resolution=0.05'
        item = SimpleNamespace(name='map', service='atlas-slam-fast.service',
                               stale_after=20., stopped_only=False)
        state, age, detail = self.node.classify(item, self.now + 600)
        self.assertEqual(state, 'HEALTHY')
        self.assertEqual(age, 600)
        self.assertEqual(detail, 'latched saved map available')

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


    # 26 Oct 2026: bounded hold for an intentional dashboard-owned camera restart.
    def hold_file(self, entries):
        import os, tempfile
        d = tempfile.mkdtemp(); path = os.path.join(d, 'm.json')
        with open(path, 'w') as f: json.dump(entries, f)
        os.environ['ATLAS_SERVICE_MAINTENANCE_FILE'] = path
        self.addCleanup(os.environ.pop, 'ATLAS_SERVICE_MAINTENANCE_FILE', None)

    def camera(self):
        self.node.last_notice['camera'] = 0; self.node.attempts['camera'] = []
        return SimpleNamespace(name='camera', service='atlas-camera.service', stale_after=8., stopped_only=False)

    def test_camera_hold_blocks_restart_without_spending_an_attempt(self):
        import time as wall
        self.hold_file({'atlas-camera.service': {'until_unix': wall.time() + 30}})
        item = self.camera()
        self.assertTrue(self.node.maintenance_hold(item))
        self.node.schedule_recovery(item, 'stale: no data for 8.9s')
        self.ns['threading'].Thread.assert_not_called(); self.process.run.assert_not_called()
        self.assertEqual(self.node.attempts['camera'], [])
        self.assertIn('RECOVERY HELD', self.node.publish_status.call_args[0][0])

    def test_hold_is_bounded_expiring_and_camera_only(self):
        import time as wall
        item = self.camera()
        for until in (wall.time() - 1, wall.time() + 46, 'x', None):
            self.hold_file({'atlas-camera.service': {'until_unix': until}})
            self.assertFalse(self.node.maintenance_hold(item), until)
        self.hold_file({'atlas-lidar.service': {'until_unix': wall.time() + 30},
                        'rover-base-telemetry.service': {'until_unix': wall.time() + 30}})
        for svc in ('atlas-lidar.service', 'rover-base-telemetry.service'):
            self.assertFalse(self.node.maintenance_hold(SimpleNamespace(name='x', service=svc)))
        import os
        os.environ['ATLAS_SERVICE_MAINTENANCE_FILE'] = '/nonexistent/m.json'
        self.assertFalse(self.node.maintenance_hold(item))
        with open(self.hold_path_corrupt(), 'w') as f: f.write('{broken')
        self.assertFalse(self.node.maintenance_hold(item))

    def hold_path_corrupt(self):
        import os, tempfile
        path = os.path.join(tempfile.mkdtemp(), 'bad.json'); os.environ['ATLAS_SERVICE_MAINTENANCE_FILE'] = path
        self.addCleanup(os.environ.pop, 'ATLAS_SERVICE_MAINTENANCE_FILE', None)
        return path

    def test_worker_cancels_if_hold_appears_before_restart(self):
        import time as wall
        item = self.camera(); self.node.recovering = {'camera'}
        self.node.classify = Mock(return_value=('STALE', 9.0, 'no data'))
        self.hold_file({'atlas-camera.service': {'until_unix': wall.time() + 30}})
        self.node.recover(item, 'stale', 3)
        self.process.run.assert_not_called()
        self.assertIn('intentional restart', self.node.publish_status.call_args[0][0])

    def test_no_hold_keeps_existing_camera_recovery(self):
        item = self.camera(); self.node.recovering = {'camera'}
        self.node.classify = Mock(side_effect=[('STALE', 9.0, 'no data'), ('HEALTHY', 0.1, '')])
        self.hold_file({})
        self.node.recover(item, 'stale', 3)
        self.process.run.assert_called_once_with(['systemctl', '--user', 'restart', 'atlas-camera.service'], timeout=15, check=True)

    def test_defers_when_systemd_is_already_restarting(self):
        # 2026-10-10: a recovery restart killed a fresh systemd auto-restart.
        self.settled()
        self.update('{"state":"CRITICAL"}')
        self.node.restart_pending = Mock(return_value=True)
        self.node.recover(self.item, 'stale', 3)
        self.process.run.assert_not_called()
        self.assertIn('DEFERRED', self.node.publish_status.call_args[0][0])
        self.assertFalse(self.node.recovering)

    def test_restart_pending_reads_systemd_state(self):
        cls = self.ns['AtlasRecovery']
        node = cls()
        for out, expect in (("ActiveState=activating\nSubState=auto-restart\n", True),
                            ("ActiveState=active\nSubState=running\n", False),
                            ("ActiveState=failed\nSubState=failed\n", False)):
            self.process.run.return_value = SimpleNamespace(stdout=out)
            self.assertEqual(node.restart_pending('atlas-lidar.service'), expect, out)
        self.process.run.side_effect = OSError('no systemctl')
        self.assertFalse(node.restart_pending('atlas-lidar.service'))


if __name__ == '__main__':
    unittest.main()
