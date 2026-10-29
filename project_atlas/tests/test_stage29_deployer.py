"""Stage 29 Stage A deployer, end to end on a fake rover (temp file tree, fake systemd/API/observer, scripted CPU).

The real Stage 28 CpuRecorder / ObserverRecorder / gates run unchanged; only system access is faked."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage29_flysky_drive'
sys.path.insert(0, str(PKG))
import deploy_stage29 as D        # noqa: E402

h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
MAN = json.loads((PKG / 'MANIFEST.json').read_text())
CAND = {step: {rel: f['candidate_sha256'] for rel, f in v['files'].items()} for step, v in MAN['steps'].items()}


class FakeRover:
    """systemd units, dashboard API and observer signals, driven by what is installed on the fake disk."""

    def __init__(self, env):
        self.env, self.lock = env, threading.Lock()
        self.units = {u: {'pid': 1000 + i, 'active': True, 'inv': f'inv-{u}-0', 'log': ''}
                      for i, u in enumerate(sorted(set(env.protected) | {D.UNITS['teleop']}))}
        self.units[D.UNITS['teleop']]['active'] = False
        self.calls, self.packets = [], 100
        self.mux_down_until = 0.0
        self.web_down_until = 0.0
        self.fail_base_after_restart = False      # scenario: base-owned observer signal fails in the window
        self.advertise_cmd = False                # scenario: disabled teleop advertises /cmd_vel_flysky
        self.break_web_view = False
        self.change_protected = None
        self.mux_never_back = False
        self.bridge_lag_s = 1.5                   # observer sees the restarted mux later than the dashboard (A1 attempt 1)
        self.observer_never_back = False

    # ---- what is installed
    def installed(self, rel):
        spec = MAN['steps'][next(s for s in MAN['steps'] if rel in MAN['steps'][s]['files'])]['files'][rel]
        dst = (self.env.unit_dir / Path(rel).name) if spec['kind'] == 'unit' else (self.env.project / rel)
        return dst.exists() and h(dst) == spec['candidate_sha256']

    def mux_patched(self):
        return self.installed('scripts/atlas_cmd_vel_mux.py')

    # ---- systemd
    def systemctl(self, *args, timeout=30, check=True):
        args = list(args)
        self.calls.append(tuple(args))
        verb = args[0]
        if verb == 'show':
            u = self.units.get(args[1], {'pid': 0, 'active': False, 'inv': '', 'log': ''})
            env_line = 'Environment=ATLAS_MANUAL_ONLY=1' + (' ATLAS_FLYSKY_DRIVE_ENABLED=1' if getattr(self, 'gate_in_unit', False) else '')
            out = (f'ActiveState={"active" if u["active"] else "inactive"}\nSubState={"running" if u["active"] else "dead"}\n'
                   f'MainPID={u["pid"] if u["active"] else 0}\nNRestarts=0\nInvocationID={u["inv"]}\nDropInPaths=\n'
                   f'ExecMainStartTimestampMonotonic=1\n{env_line}\nEnvironmentFiles=\n')
            return NS(stdout=out, returncode=0)
        if verb == 'list-jobs':
            return NS(stdout='', returncode=0)
        if verb in ('restart', 'start'):
            u = self.units[args[1]]
            u['pid'] += 100; u['active'] = True; u['inv'] = u['inv'].rsplit('-', 1)[0] + '-' + str(len(self.calls))
            if args[1] == D.UNITS['mux']:
                self.mux_down_until = time.time() + (1e9 if self.mux_never_back else 1.0)
                u['log'] = 'ATLAS cmd_vel priority: REMOTE > FLYSKY > COMMISSION' if self.mux_patched() else 'ATLAS cmd_vel priority: REMOTE > COMMISSION'
            if args[1] == D.UNITS['teleop']:
                u['log'] = 'FlySky teleop DISABLED: FlySky driving gate is off'
            if args[1] == D.UNITS['web']:
                self.web_down_until = time.time() + 1.0
            if self.change_protected:
                self.units[self.change_protected]['pid'] += 7
            return NS(stdout='', returncode=0)
        if verb == 'stop':
            self.units[args[1]]['active'] = False
            return NS(stdout='', returncode=0)
        return NS(stdout='', returncode=0)

    def journal(self, inv, since_epoch=0.0):
        return next((u['log'] for u in self.units.values() if u['inv'] == inv), '')

    # ---- dashboard API
    def get(self, path):
        now = time.time()
        if now < self.web_down_until:
            raise OSError('connection refused (web restarting)')
        if path == '/api/estop/state':
            return {'latched': self.env.estop}
        if path == '/api/status':
            with self.lock:
                self.packets += 1
                n = self.packets
            pol = {'stop_latched': True, 'manual_only': True, 'commission_armed': False, 'source': 'STOPPED',
                   'stop_reason': 'REMOTE STOP: B pressed'}
            if self.mux_patched():
                pol.update(manual_controller='XBOX', flysky_drive_enabled=False)
            age = 5.0 if now < self.mux_down_until else 0.1
            return {'ros': {
                'control_policy': {'age': age, 'value': json.dumps(pol)},
                'cmd_vel': {'age': age, 'value': {'lin': 0.0, 'ang': 0.0}},
                'motor_speed': {'age': 0.2, 'value': 0.0}, 'web_drive': {'age': 0.1, 'value': 'STOP'},
                'drive_pid': {'age': 0.1, 'value': json.dumps({'active': False})},
                'odom': {'age': 0.1, 'value': {'vx': 0.0, 'wz': 0.0}},
                **{f'enc_m{i}': {'age': 0.0, 'value': v} for i, v in zip(range(1, 5), (-404, 1471, -14027, 1421))},
                'encoder_health': {'age': 0.0, 'value': json.dumps({'state': 'READY', 'packet_fresh': True,
                                                                     'packet_age_s': 0.02, 'serial_encoder_packets': n})}}}
        if path == '/api/manual_controller':
            if not self.installed('scripts/atlas_manual_controller_web.py'):
                raise OSError('404')
            teleop = self.units[D.UNITS['teleop']]['active']
            return {'policy': {'selection_supported': self.mux_patched(), 'manual_controller': 'XBOX',
                               'flysky_drive_enabled': False, 'stop_latched': True},
                    'drive': {'running': teleop, 'status': {'state': 'ARMED' if self.break_web_view else 'DISABLED'}},
                    'can_select': {'XBOX': False, 'FLYSKY': False}}
        if path == '/api/flysky/state':
            return {'read_only': True, 'link': {'state': 'LIVE'}}
        raise OSError('unknown ' + path)

    def get_text(self, path):
        if path == '/v2/flysky-drive' and self.installed('web/v2/flysky-drive.html'):
            return 200, 'ATLAS · FlySky Driving'
        return 404, ''

    def sample(self, wanted, seconds=3.0):
        teleop = self.units[D.UNITS['teleop']]['active']
        out = {w: {'advertised': False, 'count': 0, 'last': None} for w in wanted}
        if self.mux_patched():                      # the patched mux subscribes: advertised, but nobody publishes
            out['/cmd_vel_flysky'].update(advertised=True)
        if teleop:
            out['/atlas/flysky/drive_status'].update(advertised=True, count=6, last=json.dumps({'state': 'DISABLED'}))
            if self.advertise_cmd:                  # scenario: the disabled teleop publishes commands
                out['/cmd_vel_flysky'].update(count=12, last=(0.0, 0, 0, 0, 0, 0.0))
        return out

    # ---- observer
    def observer(self, base_pid):
        rover = self

        class Obs:
            def start(self): return self
            def stop(self): pass
            def evaluate(self):
                now = time.time()
                mux_down = now < rover.mux_down_until + rover.bridge_lag_s or (rover.observer_never_back and rover.mux_down_until > 0)
                restarted = any(c[0] in ('restart', 'start') for c in rover.calls)
                sig = {k: {'ok': not (mux_down and k in D.MUX_SIGNALS), 'age_s': 0.1}
                       for k in ('observer_connected', 'estop_latched', 'manual_only', 'commission_off', 'source_stopped',
                                 'cmd_zero', 'motor_output_zero', 'telemetry_live', 'base_loop_alive', 'base_still', 'base_identity')}
                if rover.fail_base_after_restart and restarted:
                    sig['motor_output_zero']['ok'] = False
                return {'wall': now, 'ok': all(s['ok'] for s in sig.values()), 'signals': sig}
        return Obs()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='s29dep-'))
        proj = self.tmp / 'project_atlas'
        for rel, base in (('scripts/atlas_cmd_vel_mux.py', 'atlas_cmd_vel_mux.py.live-0d959286'),
                          ('scripts/atlas_status_web.py', 'atlas_status_web.py.live-4ab16214'),
                          ('scripts/atlas_web_v2.py', 'atlas_web_v2.py.live-4893d1f6'),
                          ('web/v2/flysky.css', 'flysky.css.live-34d3e404')):
            (proj / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PKG / 'baseline' / base, proj / rel)
        (self.tmp / 'envdir').mkdir()
        (self.tmp / 'envdir' / 'hardware.env').write_text('ATLAS_YAHBOOM_PORT=/dev/ttyUSB0\n')
        (self.tmp / 'evidence').mkdir()
        self.cpu = []
        self.env = self.make_env()
        self.rover = FakeRover(self.env)
        for name in ('systemctl', 'journal', 'get', 'get_text'):
            setattr(self.env, name, getattr(self.rover, name))
        self.env.sample_topics = self.rover.sample
        self.env.make_observer = self.rover.observer

    def make_env(self):
        test = self

        class E(D.Env):
            def cpu_samples(self, n):
                out, test.cpu = test.cpu[:n], test.cpu[n:]
                return out + [62.0] * (n - len(out))

            def ram_temp(self):
                return 60.0, {'cpu-thermal': 64.0}
        e = E(project=self.tmp / 'project_atlas', unit_dir=self.tmp / 'units', env_dir=self.tmp / 'envdir',
              evidence_root=self.tmp / 'evidence', steady_s=3, preflight_s=2, observer_warmup_s=0.5,
              mux_back_timeout_s=4.0, hold_poll_s=0.2)
        e.sleep = time.sleep
        e.estop = True
        return e

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_step(self, step, bound=3.0, extra=()):
        argv = ['deploy', '--step', step, '--cpu-bound-s', str(bound), '--owner-confirms-estop-latched',
                '--owner-confirms-rover-lifted-and-clear', *extra]
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}), mock.patch.object(D, 'HOLD_MAX_S', 8.0):
            return D.main(argv, env=self.env)

    def result(self, kind):
        d = sorted(self.env.evidence_root.glob(f'stage29-{kind}-*'))[-1]
        return json.loads(sorted(d.glob('*-result.json'))[-1].read_text()), d

    def restarts(self, unit):
        return sum(1 for c in self.rover.calls if c[0] in ('restart', 'start') and c[1] == unit)

    def sha(self, rel):
        return h(self.env.project / rel)


class Refusals(Base):
    def test_cli_requires_approval_bound_and_confirmations(self):
        self.assertEqual(D.main(['deploy', '--step', 'mux', '--cpu-bound-s', '10', '--owner-confirms-estop-latched',
                                 '--owner-confirms-rover-lifted-and-clear'], env=self.env), 2)     # no OWNER_APPROVED
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            for argv in (['deploy', '--step', 'mux', '--owner-confirms-estop-latched', '--owner-confirms-rover-lifted-and-clear'],
                         ['deploy', '--step', 'mux', '--cpu-bound-s', '31', '--owner-confirms-estop-latched', '--owner-confirms-rover-lifted-and-clear'],
                         ['deploy', '--step', 'mux', '--cpu-bound-s', '10'],
                         ['rollback', '--step', 'mux', '--owner-confirms-estop-latched', '--owner-confirms-rover-lifted-and-clear']):
                self.assertEqual(D.main(argv, env=self.env), 2, argv)
        self.assertEqual(self.rover.calls, [])

    def test_out_of_order_gate_on_estop_released_and_drift_change_nothing(self):
        before = {rel: self.sha(rel) for rel in ('scripts/atlas_cmd_vel_mux.py', 'scripts/atlas_status_web.py')}
        self.assertEqual(self.run_step('teleop'), 3)
        self.assertIn('needs step mux first', self.result('deploy-teleop')[0]['reason'])
        (self.tmp / 'envdir' / 'hardware.env').write_text('ATLAS_FLYSKY_DRIVE_ENABLED=1\n')
        self.assertEqual(self.run_step('mux'), 3)
        self.assertIn('gate is ON', self.result('deploy-mux')[0]['reason'])
        (self.tmp / 'envdir' / 'hardware.env').write_text('\n')
        self.rover.gate_in_unit = True
        self.assertEqual(self.run_step('mux'), 3); self.rover.gate_in_unit = False
        self.env.estop = False
        self.assertEqual(self.run_step('mux'), 3)
        self.assertIn('not latched', self.result('deploy-mux')[0]['reason'])
        self.env.estop = True
        p = self.env.project / 'scripts/atlas_cmd_vel_mux.py'; p.write_text(p.read_text() + '\n# drift\n')
        self.assertEqual(self.run_step('mux'), 3)
        self.assertIn('drifted', self.result('deploy-mux')[0]['reason'])
        self.assertFalse(any(c[0] in ('restart', 'start') for c in self.rover.calls))
        self.assertEqual(self.sha('scripts/atlas_status_web.py'), before['scripts/atlas_status_web.py'])

    def test_hot_pre_window_refuses_before_any_change(self):
        self.cpu = [62.0, 62.0] + [80.0] * 6            # preflight OK, then the pre-window sees > 75
        base = self.sha('scripts/atlas_cmd_vel_mux.py')
        self.assertEqual(self.run_step('mux'), 3)
        r, _ = self.result('deploy-mux')
        self.assertEqual(r['result'], 'REFUSED_NO_CHANGE')
        self.assertEqual(self.sha('scripts/atlas_cmd_vel_mux.py'), base)
        self.assertEqual(self.restarts(D.UNITS['mux']), 0)


class MuxStep(Base):
    def test_pass_installs_candidate_restarts_once_and_keeps_xbox(self):
        self.cpu = [62.0] * 6 + [90.0, 99.0] + [62.0] * 40     # spike inside the 3 s bound, then recovery
        self.assertEqual(self.run_step('mux'), 0)
        r, d = self.result('deploy-mux')
        self.assertEqual(r['result'], 'PASS')
        self.assertEqual(self.sha('scripts/atlas_cmd_vel_mux.py'), CAND['mux']['scripts/atlas_cmd_vel_mux.py'])
        self.assertEqual(self.restarts(D.UNITS['mux']), 1)
        self.assertTrue((d / 'backup' / 'meta.json').exists())
        self.assertTrue(any(p.name.startswith('stream-observer') for p in d.iterdir()))
        log = (d / 'log.txt').read_text()
        self.assertIn('exemption cleared', log); self.assertIn("'manual_controller': 'XBOX'", log)

    def test_base_signal_failure_in_window_rolls_back(self):
        self.rover.fail_base_after_restart = True
        self.assertEqual(self.run_step('mux'), 1)
        r, _ = self.result('deploy-mux')
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK')
        self.assertEqual(self.sha('scripts/atlas_cmd_vel_mux.py'), MAN['steps']['mux']['files']['scripts/atlas_cmd_vel_mux.py']['baseline_sha256'])
        self.assertEqual(self.restarts(D.UNITS['mux']), 2)

    def test_bridge_lag_after_dashboard_is_waited_out_not_aborted(self):
        # A1 attempt 1 failed exactly here: dashboard fresh at +1 s, observer fresh only at +2.5 s.
        self.assertEqual(self.run_step('mux'), 0)
        log = (self.result('deploy-mux')[1] / 'log.txt').read_text()
        self.assertIn('mux back on the dashboard', log); self.assertIn('exemption cleared', log)

    def test_observer_never_sees_mux_rolls_back(self):
        self.rover.observer_never_back = True
        self.assertEqual(self.run_step('mux', bound=10.0), 1)
        r, d = self.result('deploy-mux')
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK'); self.assertIn('observer mux signals not ok', r['reason'])

    def test_mux_not_back_rolls_back(self):
        self.rover.mux_never_back = True
        self.assertEqual(self.run_step('mux', bound=10.0), 1)
        r, _ = self.result('deploy-mux')
        self.assertIn(r['result'], ('FAIL_ROLLED_BACK', 'FAIL_ROLLBACK_UNCONFIRMED'))
        self.assertEqual(self.sha('scripts/atlas_cmd_vel_mux.py'), MAN['steps']['mux']['files']['scripts/atlas_cmd_vel_mux.py']['baseline_sha256'])

    def test_cpu_overrun_with_safety_ok_holds_without_restart_then_owner_rollback(self):
        self.cpu = [62.0] * 6 + [99.0] * 6 + [62.0] * 60      # over the limit past the 3 s bound
        self.assertEqual(self.run_step('mux'), 1)
        r, d = self.result('deploy-mux')
        self.assertEqual(r['result'], 'FAIL_HELD')
        self.assertEqual(self.restarts(D.UNITS['mux']), 1)       # no automatic second spike
        self.assertEqual(self.sha('scripts/atlas_cmd_vel_mux.py'), CAND['mux']['scripts/atlas_cmd_vel_mux.py'])
        self.assertIn('rollback --step mux', (d / 'log.txt').read_text())
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            rc = D.main(['rollback', '--step', 'mux', '--evidence', str(d), '--owner-confirms-estop-latched',
                         '--owner-confirms-rover-lifted-and-clear'], env=self.env)
        self.assertEqual(rc, 0)
        self.assertEqual(self.sha('scripts/atlas_cmd_vel_mux.py'), MAN['steps']['mux']['files']['scripts/atlas_cmd_vel_mux.py']['baseline_sha256'])
        self.assertEqual(self.restarts(D.UNITS['mux']), 2)

    def test_lasting_load_fails_recovery_mean_and_holds(self):
        self.cpu = [60.0] * 6 + [90.0] + [70.0] * 60          # every steady sample <= 75 but +10 points above baseline
        self.assertEqual(self.run_step('mux'), 1)
        r, _ = self.result('deploy-mux')
        self.assertEqual(r['result'], 'FAIL_HELD'); self.assertIn('lasting new load', r['reason'])

    def test_protected_service_change_rolls_back(self):
        self.rover.change_protected = 'atlas-ekf.service'
        self.assertEqual(self.run_step('mux'), 1)
        self.assertEqual(self.result('deploy-mux')[0]['result'], 'FAIL_ROLLED_BACK')


class LaterSteps(Base):
    def deploy_mux(self):
        self.cpu = []
        self.assertEqual(self.run_step('mux'), 0)

    def test_teleop_then_web_pass(self):
        self.deploy_mux()
        self.assertEqual(self.run_step('teleop'), 0)
        self.assertTrue((self.env.unit_dir / 'atlas-flysky-teleop.service').exists())
        self.assertIn(('daemon-reload',), self.rover.calls)
        self.assertEqual(self.restarts(D.UNITS['teleop']), 1)
        cfg = json.loads((self.env.project / 'config/atlas_flysky_drive.json').read_text())
        self.assertFalse(cfg['reviewed_by_owner'])
        self.assertEqual(self.run_step('web'), 0)
        for rel, want in CAND['web'].items():
            self.assertEqual(self.sha(rel), want, rel)
        self.assertEqual(self.restarts(D.UNITS['web']), 1)
        self.assertEqual(self.run_step('web'), 3)             # already installed: refused

    def test_teleop_advertising_a_command_topic_is_rolled_back(self):
        self.deploy_mux()
        self.rover.advertise_cmd = True
        self.assertEqual(self.run_step('teleop'), 1)
        self.assertEqual(self.result('deploy-teleop')[0]['result'], 'FAIL_ROLLED_BACK')
        self.assertFalse((self.env.unit_dir / 'atlas-flysky-teleop.service').exists())
        self.assertFalse((self.env.project / 'scripts/atlas_flysky_teleop.py').exists())
        self.assertFalse(self.rover.units[D.UNITS['teleop']]['active'])

    def test_web_verification_failure_restores_dashboard(self):
        self.deploy_mux()
        self.assertEqual(self.run_step('teleop'), 0)
        self.rover.break_web_view = True
        self.assertEqual(self.run_step('web'), 1)
        self.assertEqual(self.result('deploy-web')[0]['result'], 'FAIL_ROLLED_BACK')
        self.assertEqual(self.sha('scripts/atlas_status_web.py'), MAN['steps']['web']['files']['scripts/atlas_status_web.py']['baseline_sha256'])
        self.assertFalse((self.env.project / 'web/v2/flysky-drive.html').exists())
        self.assertEqual(self.restarts(D.UNITS['web']), 2)


class AdvertisedTopicsReal(unittest.TestCase):
    """The real advertised_topics() against the fake foxglove bridge (the A2 readiness check found it blocked forever)."""
    def test_returns_within_deadline_and_lists_topics(self):
        import socket, subprocess
        sys.path.insert(0, str(ROOT / 'tests'))
        port = (lambda s: (s.bind(('127.0.0.1', 0)), s.getsockname()[1], s.close())[1])(socket.socket())
        ctl = Path(tempfile.mkdtemp()) / 'ctl.json'; ctl.write_text('{}')
        srv = subprocess.Popen([sys.executable, str(ROOT / 'tools/deploy/stage28_base_maintenance/sim/fake_foxglove.py'),
                                str(port), str(ctl), 'foxglove.sdk.v1'])
        try:
            for _ in range(100):
                try:
                    socket.create_connection(('127.0.0.1', port), 0.2).close(); break
                except OSError:
                    time.sleep(0.05)
            env = D.Env(observer_port=port)
            t0 = time.time(); topics = env.advertised_topics(seconds=1.5); dt = time.time() - t0
            self.assertLess(dt, 3.0)
            self.assertIn('/atlas/control_policy', topics); self.assertNotIn('/cmd_vel_flysky', topics)
            t0 = time.time(); smp = env.sample_topics(['/atlas/control_policy', '/cmd_vel_flysky'], seconds=1.5)
            self.assertLess(time.time() - t0, 3.0)
            pol = smp['/atlas/control_policy']
            self.assertTrue(pol['advertised']); self.assertGreater(pol['count'], 5)        # 10 Hz in the fake bridge
            self.assertIn('stop_latched', json.loads(pol['last']))
            self.assertEqual(smp['/cmd_vel_flysky'], {'advertised': False, 'count': 0, 'last': None, 'schema': None})
        finally:
            srv.terminate(); srv.wait(5)

    def test_unreachable_bridge_fails(self):
        with self.assertRaises(D.Fail):
            D.Env(observer_port=1).advertised_topics(seconds=0.5)


class Preflight(Base):
    def test_preflight_is_read_only_and_go(self):
        self.assertEqual(D.main(['preflight'], env=self.env), 0)
        self.assertFalse(any(c[0] in ('restart', 'start', 'stop', 'daemon-reload') for c in self.rover.calls))

    def test_manifest_is_reproducible(self):
        import subprocess
        self.assertEqual(subprocess.run([sys.executable, str(PKG / 'refresh_manifest.py'), '--check']).returncode, 0)


if __name__ == '__main__':
    unittest.main()
