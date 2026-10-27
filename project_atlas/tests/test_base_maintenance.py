"""Offline tests: Stage 28 base-maintenance lease, gate, recovery patch and deployer gates (no ROS, no systemd)."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage28_base_maintenance'
sys.path.insert(0, str(ROOT / 'scripts'))
import atlas_base_maintenance as bm  # noqa: E402

MANIFEST = json.loads((PKG / 'MANIFEST.json').read_text())


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def make(tmp, clock=None, ticks=None, boot='boot-A'):
    return bm.Maintenance(root=Path(tmp) / 'm', clock=clock or Clock(), boot=boot,
                          start_ticks=ticks or (lambda pid: 4242))


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.m = make(self.tmp.name, self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_directory_and_no_lease_are_none(self):
        self.assertEqual(self.m.evaluate().state, bm.NONE)
        self.m._check_root(create=True)
        self.assertEqual(self.m.evaluate().state, bm.NONE)

    def test_valid_lease_is_active(self):
        s = self.m.arm('t', 60, owner_pid=123)
        v = self.m.evaluate()
        self.assertEqual((v.state, v.lease['session']), (bm.ACTIVE, s))

    def _armed_then(self, mutate):
        self.m.arm('t', 60, owner_pid=123)
        d = json.loads(self.m.lease_path.read_text())
        mutate(d)
        self.m._write(self.m.lease_path, d)
        return self.m.evaluate()

    def test_invalid_matrix_fails_closed(self):
        cases = {
            'wrong boot': lambda d: d.update(boot='boot-B'),
            'bad session': lambda d: d.update(session='x' * 32),
            'too long': lambda d: d.update(deadline=d['created'] + bm.MAX_LEASE_S + 1),
            'tokens over budget': lambda d: d.update(tokens=3, used=3),
            'used above tokens': lambda d: d.update(used=1),
            'bad phase': lambda d: d.update(phase='WHATEVER'),
            'nan deadline': lambda d: d.update(deadline=float('nan')),
            'wrong service': lambda d: d.update(service='atlas-camera.service'),
            'bool pid': lambda d: d.update(owner_pid=True),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                self.m.clear(force=True)
                v = self._armed_then(fn)
                self.assertEqual(v.state, bm.INVALID, (name, v))
                self.assertTrue(v.hold)

    def test_owner_gone_expired_future_are_invalid(self):
        self.m.arm('t', 60, owner_pid=123)
        gone = make(self.tmp.name, self.clock, ticks=lambda pid: None)
        self.assertIn('owner', gone.evaluate().reason)
        reused = make(self.tmp.name, self.clock, ticks=lambda pid: 9999)       # PID reused by another process
        self.assertEqual(reused.evaluate().state, bm.INVALID)
        self.clock.t += 61
        self.assertIn('deadline', self.m.evaluate().reason)
        self.clock.t -= 1000
        self.assertIn('future', self.m.evaluate().reason)

    def test_unsafe_files_are_invalid(self):
        self.m.arm('t', 60, owner_pid=123)
        os.chmod(self.m.lease_path, 0o644)
        self.assertEqual(self.m.evaluate().state, bm.INVALID)
        os.chmod(self.m.lease_path, 0o600)
        self.m.lease_path.write_text('{not json')
        self.assertEqual(self.m.evaluate().state, bm.INVALID)
        self.m.lease_path.unlink()
        target = Path(self.tmp.name) / 'elsewhere.json'
        target.write_text('{}')
        os.symlink(target, self.m.lease_path)
        self.assertEqual(self.m.evaluate().state, bm.INVALID)
        self.m.lease_path.unlink()
        self.m.lease_path.write_bytes(b' ' * (bm.MAX_FILE_BYTES + 1))
        os.chmod(self.m.lease_path, 0o600)
        self.assertEqual(self.m.evaluate().state, bm.INVALID)

    def test_unsafe_root_is_invalid(self):
        real = Path(self.tmp.name) / 'real'
        real.mkdir(mode=0o700)
        os.symlink(real, Path(self.tmp.name) / 'm')
        self.assertEqual(self.m.evaluate().state, bm.INVALID)
        os.unlink(Path(self.tmp.name) / 'm')
        os.mkdir(Path(self.tmp.name) / 'm', 0o755)
        os.chmod(Path(self.tmp.name) / 'm', 0o755)
        self.assertEqual(self.m.evaluate().state, bm.INVALID)

    def test_gate_tokens_are_single_use_and_bounded(self):
        self.assertTrue(self.m.start_gate()[0], 'no lease: normal start')
        s = self.m.arm('t', 60, owner_pid=123)
        self.assertFalse(self.m.start_gate()[0], 'HOLD withholds every start')
        self.m.authorize_start(s)
        with self.assertRaises(bm.Refused):
            self.m.authorize_start(s)                       # no stacking of unused tokens
        self.assertTrue(self.m.start_gate()[0])
        self.assertFalse(self.m.start_gate()[0], 'token consumed: systemd auto-restart withheld')
        self.m.authorize_start(s)
        self.assertTrue(self.m.start_gate()[0])
        with self.assertRaises(bm.Refused):
            self.m.authorize_start(s)                       # budget: deploy + rollback only
        self.clock.t += 61
        self.assertFalse(self.m.start_gate()[0], 'expired lease withholds starts')

    def test_gate_error_withholds(self):
        self.m.arm('t', 60, owner_pid=123)
        with mock.patch.object(self.m, 'evaluate', side_effect=RuntimeError('boom')):
            ok, why = self.m.start_gate()
        self.assertFalse(ok)
        self.assertIn('gate error', why)

    def test_revoke_unused_token(self):
        s = self.m.arm('t', 60, owner_pid=123)
        self.m.authorize_start(s)
        self.assertTrue(self.m.revoke_unused(s))
        self.assertFalse(self.m.start_gate()[0])

    def test_arm_refuses_existing_state_and_busy_dispatch(self):
        self.m.arm('t', 60, owner_pid=123)
        with self.assertRaises(bm.Refused):
            self.m.arm('t', 60, owner_pid=123)
        self.m.clear(force=True)
        with self.m.recovery_dispatch() as v:               # recovery inside a base attempt
            self.assertEqual(v.state, bm.NONE)
            with self.assertRaises(bm.Refused):
                self.m.arm('t', 60, owner_pid=123, wait_s=0)
        self.assertEqual(self.m.evaluate().state, bm.NONE)

    def test_arm_waits_for_dispatch_release(self):
        hold = threading.Event()
        go = threading.Event()

        def recovery():
            with self.m.recovery_dispatch():
                hold.set()
                go.wait(2)
                time.sleep(0.3)
        t = threading.Thread(target=recovery)
        t.start()
        hold.wait(2)
        go.set()
        s = self.m.arm('t', 60, owner_pid=123, wait_s=3)
        t.join()
        self.assertEqual(self.m.evaluate().lease['session'], s)

    def test_dispatch_sees_lease_created_before_it_entered(self):
        self.m.arm('t', 60, owner_pid=123)
        with self.m.recovery_dispatch() as v:
            self.assertTrue(v.hold)

    def test_release_and_clear(self):
        s = self.m.arm('t', 60, owner_pid=123)
        with self.assertRaises(bm.Refused):
            self.m.clear(s)                                 # not released
        self.m.authorize_start(s)
        with self.assertRaises(bm.Refused):
            self.m.release(s)                               # pending token
        self.m.start_gate()
        self.m.release(s)
        self.assertEqual(self.m.evaluate().state, bm.NONE)  # RELEASED == NONE for gate + recovery
        self.assertTrue(self.m.start_gate()[0])
        self.m.clear(s)
        self.assertFalse(self.m.lease_path.exists())

    def test_files_are_private(self):
        self.m.arm('t', 60, owner_pid=123)
        self.assertEqual(os.stat(self.m.root).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(self.m.lease_path).st_mode & 0o777, 0o600)

    def test_real_process_identity(self):
        m = bm.Maintenance(root=Path(self.tmp.name) / 'r', clock=Clock(), boot='b')
        p = subprocess.Popen(['sleep', '30'])
        try:
            m.arm('t', 60, owner_pid=p.pid)
            self.assertEqual(m.evaluate().state, bm.ACTIVE)
        finally:
            p.kill()
            p.wait()
        self.assertEqual(m.evaluate().state, bm.INVALID)


# ------------------------------------------------------------------ patched recovery under stub rclpy
def baseline_dir():
    d = tempfile.mkdtemp()
    subprocess.run([str(PKG / 'sim/fetch_baselines.sh'), d], check=True, capture_output=True)
    return Path(d)


BASELINES = baseline_dir()


def candidate_recovery_path():
    d = Path(tempfile.mkdtemp())
    p = d / 'atlas_sensor_recovery.py'
    p.write_bytes((BASELINES / 'atlas_sensor_recovery.py').read_bytes())
    subprocess.run([sys.executable, '-I', str(PKG / 'insert_recovery_base_hold.py'), str(p)], check=True,
                   capture_output=True)
    return p


def stub_ros():
    class Node:
        def __init__(self, name):
            self.logs = []

        def create_publisher(self, *a):
            return types.SimpleNamespace(publish=lambda m: None)

        def create_subscription(self, *a, **k):
            pass

        def create_timer(self, *a):
            pass

        def get_logger(self):
            logs = self.logs
            return types.SimpleNamespace(info=logs.append, error=logs.append, warning=logs.append)

    class String:
        def __init__(self, data=''):
            self.data = data
    mods = {n: types.ModuleType(n) for n in ('rclpy', 'rclpy.node', 'rclpy.executors', 'rclpy.qos', 'geometry_msgs',
                                            'geometry_msgs.msg', 'nav_msgs', 'nav_msgs.msg', 'sensor_msgs',
                                            'sensor_msgs.msg', 'std_msgs', 'std_msgs.msg')}
    mods['rclpy.node'].Node = Node
    mods['rclpy.executors'].ExternalShutdownException = Exception
    mods['rclpy.qos'].__dict__.update(QoSProfile=lambda **k: None, DurabilityPolicy=types.SimpleNamespace(TRANSIENT_LOCAL=1),
                                      ReliabilityPolicy=types.SimpleNamespace(RELIABLE=1))
    mods['geometry_msgs.msg'].Twist = type('Twist', (), {})
    for n in ('OccupancyGrid', 'Odometry'):
        setattr(mods['nav_msgs.msg'], n, type(n, (), {}))
    for n in ('CompressedImage', 'Imu', 'LaserScan', 'NavSatFix'):
        setattr(mods['sensor_msgs.msg'], n, type(n, (), {}))
    mods['std_msgs.msg'].__dict__.update(Float32=type('Float32', (), {}), Int32=type('Int32', (), {}), String=String)
    return mods


def load_recovery(path, with_module=True):
    mods = stub_ros()
    if not with_module:
        mods['atlas_base_maintenance'] = None        # import raises ImportError
    with mock.patch.dict(sys.modules, mods):
        spec = importlib.util.spec_from_file_location('rec_under_test', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


class PatchedRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = candidate_recovery_path()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = load_recovery(self.path)
        self.node = self.mod.AtlasRecovery()
        self.m = make(self.tmp.name)
        self.node._atlas_bm_m = self.m
        self.node.publish_status = mock.Mock()
        self.base_item = next(i for i in self.mod.MONITORS if i.name == 'encoder_health')
        self.cam_item = next(i for i in self.mod.MONITORS if i.name == 'camera')

    def tearDown(self):
        self.tmp.cleanup()

    def test_candidate_matches_manifest_and_only_adds(self):
        data = self.path.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         MANIFEST['modified']['atlas_sensor_recovery.py']['candidate_sha256'])
        base = (BASELINES / 'atlas_sensor_recovery.py').read_text().splitlines()
        cand = self.path.read_text().splitlines()
        it = iter(cand)
        self.assertTrue(all(any(line == c for c in it) for line in base), 'a baseline line was removed/reordered')

    def test_insert_refuses_other_input_and_second_run(self):
        p = Path(self.tmp.name) / 'x.py'
        p.write_text(self.path.read_text())
        r = subprocess.run([sys.executable, '-I', str(PKG / 'insert_recovery_base_hold.py'), str(p)],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_hold_only_for_base_and_camera_logic_untouched(self):
        self.assertFalse(self.node.maintenance_hold(self.base_item))
        self.m.arm('t', 60, owner_pid=123)
        self.assertTrue(self.node.maintenance_hold(self.base_item))
        self.assertFalse(self.node.maintenance_hold(self.cam_item))   # no camera maintenance file -> unchanged

    def test_non_base_restart_never_enters_dispatch(self):
        self.node._atlas_bm_m = mock.Mock(side_effect=AssertionError, recovery_dispatch=mock.Mock(side_effect=AssertionError))
        self.assertTrue(self.node._atlas_base_dispatch_enter(self.cam_item))

    def test_dispatch_cancels_when_lease_appeared(self):
        self.m.arm('t', 60, owner_pid=123)
        self.assertFalse(self.node._atlas_base_dispatch_enter(self.base_item))
        self.assertIn('RECOVERY CANCELED', self.node.publish_status.call_args[0][0])

    def test_dispatch_holds_lock_until_exit(self):
        self.assertTrue(self.node._atlas_base_dispatch_enter(self.base_item))
        with self.assertRaises(bm.Refused):
            self.m.arm('t', 60, owner_pid=123, wait_s=0)
        self.node._atlas_base_dispatch_exit(self.base_item)
        self.m.arm('t', 60, owner_pid=123, wait_s=0)

    def test_dispatch_unusable_cancels(self):
        self.node._atlas_bm_m = mock.Mock(recovery_dispatch=mock.Mock(side_effect=bm.Refused('dir unsafe')))
        self.assertFalse(self.node._atlas_base_dispatch_enter(self.base_item))

    def test_recover_does_not_restart_under_lease(self):
        """Full recover() body: lease armed after scheduling -> no systemctl restart, attempt released."""
        node = self.node
        node.restart_allowed = mock.Mock(return_value=True)
        node.classify = mock.Mock(return_value=('STALE', 5.0, 'x'))
        node.restart_pending = mock.Mock(return_value=False)
        node.bms_retry_owned = mock.Mock(return_value=False)
        node.recovering.add('encoder_health')
        calls = []
        orig_hold = node.maintenance_hold

        def hold_then_arm(item):
            r = orig_hold(item)
            if not self.m.evaluate().hold:
                self.m.arm('raced in', 60, owner_pid=123)      # deployer arms right after the early check
            return r
        node.maintenance_hold = hold_then_arm
        with mock.patch.object(self.mod.subprocess, 'run', side_effect=lambda *a, **k: calls.append(a)):
            node.recover(self.base_item, 'stale', 1)
        self.assertEqual(calls, [], 'restart issued although the lease existed at the final check')
        self.assertNotIn('encoder_health', node.recovering)

    def test_tick_acks_and_reports_in_flight(self):
        s = self.m.arm('t', 60, owner_pid=123)
        self.node._atlas_base_maint_tick()
        a = self.m.read_ack()
        self.assertEqual((a['session'], a['in_flight']), (s, False))
        self.node.recovering.add('encoder_health')
        self.node._atlas_base_maint_tick()
        self.assertTrue(self.m.read_ack()['in_flight'])

    def test_tick_reports_invalid(self):
        self.m.arm('t', 60, owner_pid=123)
        self.node._atlas_bm_m = make(self.tmp.name, ticks=lambda pid: None)
        self.node._atlas_base_maint_tick()
        self.assertIn('HOLD INVALID', self.node.publish_status.call_args[0][0])
        self.assertEqual(self.node._atlas_base_hold_state, 'INVALID')

    def test_missing_module_with_lease_fails_closed(self):
        mod = load_recovery(self.path, with_module=False)
        self.assertIsNone(mod._atlas_bm)
        node = mod.AtlasRecovery()
        node.publish_status = mock.Mock()
        item = next(i for i in mod.MONITORS if i.name == 'encoder_health')
        with mock.patch.object(mod.os.path, 'lexists', return_value=True):
            self.assertTrue(node.maintenance_hold(item))
            self.assertFalse(node._atlas_base_dispatch_enter(item))
        with mock.patch.object(mod.os.path, 'lexists', return_value=False):
            self.assertFalse(node.maintenance_hold(item))
            self.assertTrue(node._atlas_base_dispatch_enter(item))


# ------------------------------------------------------------------ deployer gates
def load_deployer():
    spec = importlib.util.spec_from_file_location('deploy_rc_bridge_ut', PKG / 'deploy_rc_bridge.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


D = load_deployer()


def status(**over):
    ros = {
        'control_policy': {'age': 0.1, 'value': json.dumps({'stop_latched': True, 'manual_only': True,
                                                             'commission_armed': False, 'source': 'STOPPED'})},
        'cmd_vel': {'age': 0.1, 'value': {'lin': 0.0, 'ang': 0.0}},
        'motor_speed': {'age': 0.2, 'value': 0.0},
        'web_drive': {'age': 0.1, 'value': 'STOP'},
        'drive_pid': {'age': 0.1, 'value': json.dumps({'active': False})},
        'odom': {'age': 0.1, 'value': {'vx': 1e-19, 'wz': 0.0}},
        **{f'enc_m{i}': {'age': 0.0, 'value': v} for i, v in zip(range(1, 5), (-13, 27, -40, 16))},
        'encoder_health': {'age': 0.0, 'value': json.dumps({'state': 'READY', 'packet_fresh': True,
                                                             'packet_age_s': 0.02, 'serial_encoder_packets': 100})},
    }
    ros.update(over)
    return {'ros': ros}


class FakeEnv(D.Env):
    def __init__(self, statuses, estop=True, cpu=None, **kw):
        super().__init__(sleep=lambda s: None, **kw)
        self.statuses, self.estop, self.cpu = list(statuses), estop, list(cpu or [])

    def get(self, path):
        if path == '/api/estop/state':
            return {'latched': self.estop}
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]

    def cpu_samples(self, n):
        out, self.cpu = self.cpu[:n], self.cpu[n:]
        return out + [60.0] * (n - len(out))

    def ram_temp(self):
        return 60.0, {'cpu-thermal': 64.0}


class Ev:
    def __init__(self):
        self.saved = []

    def save(self, name, obj):
        self.saved.append((name, obj))

    def log(self, msg):
        pass


def pk(n, **over):
    s = status(**over)
    eh = json.loads(s['ros']['encoder_health']['value'])
    eh['serial_encoder_packets'] = n
    s['ros']['encoder_health']['value'] = json.dumps(eh)
    return s


class DeployerGateTests(unittest.TestCase):
    def test_safe_series_passes_and_is_retained(self):
        ev = Ev()
        D.require_safe(FakeEnv([pk(1), pk(2), pk(3)]), ev, 'x')
        self.assertEqual(len(ev.saved), 3)

    def test_each_predicate_blocks(self):
        bad = {
            'estop': None,
            'cmd': {'cmd_vel': {'age': 0.1, 'value': {'lin': 0.01, 'ang': 0.0}}},
            'cmd stale': {'cmd_vel': {'age': 1.5, 'value': {'lin': 0.0, 'ang': 0.0}}},
            'policy': {'control_policy': {'age': 0.1, 'value': json.dumps({'stop_latched': False, 'manual_only': True,
                                                                           'commission_armed': False, 'source': 'STOPPED'})}},
            'commission': {'control_policy': {'age': 0.1, 'value': json.dumps({'stop_latched': True, 'manual_only': True,
                                                                               'commission_armed': True, 'source': 'STOPPED'})}},
            'motor output': {'motor_speed': {'age': 0.1, 'value': 0.2}},
            'drive pid': {'drive_pid': {'age': 0.1, 'value': json.dumps({'active': True})}},
            'odom': {'odom': {'age': 0.1, 'value': {'vx': 0.05, 'wz': 0.0}}},
            'encoder stale': {'enc_m3': {'age': 3.0, 'value': -40}},
            'telemetry': {'encoder_health': {'age': 0.0, 'value': json.dumps({'state': 'CRITICAL', 'packet_fresh': True,
                                                                               'packet_age_s': 0.0, 'serial_encoder_packets': 5})}},
        }
        for name, over in bad.items():
            with self.subTest(name):
                env = FakeEnv([status(**(over or {}))], estop=over is not None)
                with self.assertRaises(D.Fail):
                    D.require_safe(env, Ev(), name)

    def test_motion_and_stalled_packets_block(self):
        moved = pk(3, enc_m1={'age': 0.0, 'value': -12})
        with self.assertRaises(D.Fail):
            D.require_safe(FakeEnv([pk(1), pk(2), moved]), Ev(), 'motion')
        with self.assertRaises(D.Fail):
            D.require_safe(FakeEnv([pk(5), pk(5), pk(5)]), Ev(), 'stalled')

    def test_strict_resource_gate_is_single_sample(self):
        with self.assertRaises(D.Fail):
            D.resources_strict(FakeEnv([status()], cpu=[60, 60, 75.01, 60]), Ev(), 'x', 4)
        D.resources_strict(FakeEnv([status()], cpu=[75.0] * 4), Ev(), 'x', 4)   # limit itself is allowed

    def test_settle_rule(self):
        env = FakeEnv([status()], cpu=[98.8, 90, 80, 70, 70, 70, 70, 70, 70], settle_run=3, steady_s=3, settle_max_s=10)
        D.resources_after_restart(env, Ev(), 'x', 'settle')
        env = FakeEnv([status()], cpu=[98.8] * 50, settle_run=3, steady_s=3, settle_max_s=10)
        with self.assertRaises(D.Fail):
            D.resources_after_restart(env, Ev(), 'x', 'settle')
        env = FakeEnv([status()], cpu=[70, 70, 70, 80] + [70] * 9, settle_run=3, steady_s=3, settle_max_s=10)
        with self.assertRaises(D.Fail):            # settled, but the steady window must also hold
            D.resources_after_restart(env, Ev(), 'x', 'settle')

    def test_strict_rule_fails_on_restart_transient(self):
        env = FakeEnv([status()], cpu=[98.8] + [66.0] * 40, steady_s=30)
        with self.assertRaises(D.Fail):
            D.resources_after_restart(env, Ev(), 'x', 'strict')

    def test_mutations_need_owner_approval_and_flags(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('OWNER_APPROVED', None)
            self.assertEqual(D.main(['deploy', '--cpu-rule', 'settle', '--owner-confirms-transmitter-off',
                                     '--owner-confirms-actuators-disconnected'], env=FakeEnv([status()])), 2)
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            self.assertEqual(D.main(['deploy'], env=FakeEnv([status()])), 2)
            self.assertEqual(D.main(['deploy', '--cpu-rule', 'settle'], env=FakeEnv([status()])), 2)

    def test_candidates_rebuild_from_baselines(self):
        with tempfile.TemporaryDirectory() as d:
            for p in BASELINES.iterdir():
                (Path(d) / p.name).write_bytes(p.read_bytes())
            env = FakeEnv([status()], scripts=Path(d))
            a = D.candidate_files(env, 'A')
            b = D.candidate_files(env, 'B')
            self.assertEqual(sorted(a), ['atlas_base_maintenance.py', 'atlas_sensor_recovery.py'])
            self.assertEqual(sorted(b), sorted(MANIFEST['stage_b_files']))
            D.compile_staged(env, {**a, **b})
            self.assertEqual(hashlib.sha256(b['yahboom_base.py']).hexdigest()[:8], 'bb6db3a1')
            self.assertEqual(hashlib.sha256(b['Rosmaster_Lib.py']).hexdigest()[:8], '15391e14')
            (Path(d) / 'atlas_flysky_core.py').write_bytes((Path(d) / 'atlas_flysky_core.py').read_bytes().replace(b'\n', b'\r\n'))
            with self.assertRaises(D.Fail):          # a changed shared file is refused, never replaced
                D.candidate_files(env, 'B')

    def test_unreadable_thermal_zones_are_not_applicable(self):
        with tempfile.TemporaryDirectory() as d:
            for i, (typ, val) in enumerate([('cpu-thermal', '64218\n'), ('cv0-thermal', None), ('bogus', '-273000'),
                                            ('hot', '999000')]):
                z = Path(d) / f'thermal_zone{i}'
                z.mkdir()
                (z / 'type').write_text(typ + '\n')
                if val is not None:
                    (z / 'temp').write_text(val)
                else:
                    os.mkdir(z / 'temp')                    # read fails like EAGAIN
            env = D.Env(thermal_root=d)
            _, temps = env.ram_temp()
        self.assertEqual(temps, {'cpu-thermal': 64.218})
        with mock.patch('os.read', side_effect=TypeError("can't concat NoneType to bytes")):
            self.assertIsNone(D.read_zone(Path('/nonexistent'))[0])

    def test_crlf_package_files_are_identified(self):
        for name, spec in MANIFEST['added'].items():
            if 'crlf_sha256_in_0ce6dd1_manifest' in spec:
                lf = (ROOT / 'scripts' / name).read_bytes()
                self.assertEqual(hashlib.sha256(lf.replace(b'\n', b'\r\n')).hexdigest(),
                                 spec['crlf_sha256_in_0ce6dd1_manifest'])


if __name__ == '__main__':
    unittest.main()
