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
        self.mux_gate = False
        self.teleop_stays_disabled = False        # scenario: gate-on does not take effect in the teleop
        self.web_restarted = False                # a restarted dashboard has no web_drive item (A3 attempt 1)
        self.web_drive_after_restart = None       # scenario: a present, non-STOP value
        self.bridge_lag_s = 1.5                   # observer sees the restarted mux later than the dashboard (A1 attempt 1)
        self.observer_never_back = False
        self.old_mux_lingers_s = 0.0              # the OLD mux keeps publishing fresh policy this long after restart (gate-on 1)
        self.restart_at, self.old_gate = -1e9, False
        self.observer_freeze_after_restart = False  # scenario: the observer stops producing verdicts (unresponsive)
        self.trigger_after = 0.0                    # scenario flags act only on restarts after this time

    # ---- what is installed
    def installed(self, rel, step=None):
        """rel is at a reviewed candidate (of `step`, or of any step that writes it: A3 and 'view' share page files)."""
        steps = [step] if step else [s for s in MAN['steps'] if rel in MAN['steps'][s]['files']]
        spec = MAN['steps'][steps[0]]['files'][rel]
        dst = (self.env.unit_dir / Path(rel).name) if spec['kind'] == 'unit' else (self.env.project / rel)
        return dst.exists() and h(dst) in {MAN['steps'][s]['files'][rel]['candidate_sha256'] for s in steps}

    def mux_patched(self):
        return self.installed('scripts/atlas_cmd_vel_mux.py')

    def gate(self, unit):
        return (self.env.runtime_unit_dir / f'{unit}.d' / D.GATE_DROPIN).exists()

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
                self.restart_at, self.old_gate = time.time(), self.mux_gate
                self.mux_down_until = time.time() + self.old_mux_lingers_s + (1e9 if self.mux_never_back else 1.0)
                self.mux_gate = self.gate(D.UNITS['mux'])
                tu = self.units[D.UNITS['teleop']]
                if tu['active']:                       # PartOf=atlas-cmd-vel-mux: the teleop restarts with the mux
                    tu['pid'] += 100; tu['inv'] = tu['inv'].rsplit('-', 1)[0] + '-m' + str(len(self.calls))
                    tu['log'] = ('FlySky teleop ENABLED' if self.gate(D.UNITS['teleop']) and not self.teleop_stays_disabled
                                 else 'FlySky teleop DISABLED: FlySky driving gate is off')
                u['log'] = 'ATLAS cmd_vel priority: REMOTE > FLYSKY > COMMISSION' if self.mux_patched() else 'ATLAS cmd_vel priority: REMOTE > COMMISSION'
            if args[1] == D.UNITS['teleop']:
                u['log'] = 'FlySky teleop DISABLED: FlySky driving gate is off'
            if args[1] == D.UNITS['web']:
                self.web_down_until = time.time() + 1.0
                self.web_restarted = True
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
            lingering = now < self.restart_at + self.old_mux_lingers_s
            if self.mux_patched():
                pol.update(manual_controller='XBOX', flysky_drive_enabled=self.old_gate if lingering else self.mux_gate)
            age = 0.1 if lingering else 5.0 if now < self.mux_down_until else 0.1
            return {'ros': {
                'control_policy': {'age': age, 'value': json.dumps(pol)},
                'cmd_vel': {'age': age, 'value': {'lin': 0.0, 'ang': 0.0}},
                'motor_speed': {'age': 0.2, 'value': 0.0},
                **({} if self.web_restarted and self.web_drive_after_restart is None else
                   {'web_drive': {'age': 0.1, 'value': self.web_drive_after_restart if self.web_restarted else 'STOP'}}),
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
        if path == '/api/controller_inputs':
            if not self.installed('scripts/atlas_controller_input_web.py') or not self.web_restarted:
                raise OSError('404')
            return {'read_only': True, 'xbox': {'state': 'LIVE', 'layout_ok': not getattr(self, 'bad_joy_layout', False),
                                                'axes': [0.0] * 8, 'buttons': [0] * 11}}
        raise OSError('unknown ' + path)

    def get_text(self, path):
        if path == '/v2/flysky-drive' and self.installed('web/v2/flysky-drive.html', 'view'):
            return 200, 'ATLAS · FlySky Driving SELECT FLYSKY <script src="/v2/controller-viz.js">'
        if path == '/v2/flysky-drive' and self.installed('web/v2/flysky-drive.html'):
            return 200, 'ATLAS · FlySky Driving'
        return 404, ''

    def sample(self, wanted, seconds=3.0):
        teleop = self.units[D.UNITS['teleop']]['active']
        out = {w: {'advertised': False, 'count': 0, 'last': None} for w in wanted}
        if self.mux_patched():                      # the patched mux subscribes: advertised, but nobody publishes
            out['/cmd_vel_flysky'].update(advertised=True)
        if teleop:
            enabled = 'ENABLED' in self.units[D.UNITS['teleop']]['log'] and 'DISABLED' not in self.units[D.UNITS['teleop']]['log']
            out['/atlas/flysky/drive_status'].update(advertised=True, count=6,
                                                     last=json.dumps({'state': 'NOT_SELECTED' if enabled else 'DISABLED'}))
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
                if rover.observer_freeze_after_restart and rover.restart_at > rover.trigger_after:
                    time.sleep(30)                   # unresponsive: no verdicts at all
                now = time.time()
                lingering = now < rover.restart_at + rover.old_mux_lingers_s
                mux_down = (not lingering and now < rover.mux_down_until + rover.bridge_lag_s) or (rover.observer_never_back and rover.mux_down_until > 0)
                restarted = any(c[0] in ('restart', 'start') for c in rover.calls)
                sig = {k: {'ok': not (mux_down and k in D.MUX_SIGNALS), 'age_s': 0.1}
                       for k in ('observer_connected', 'estop_latched', 'manual_only', 'commission_off', 'source_stopped',
                                 'cmd_zero', 'motor_output_zero', 'telemetry_live', 'base_loop_alive', 'base_still', 'base_identity')}
                if rover.fail_base_after_restart and restarted and rover.restart_at > rover.trigger_after:
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
        e = E(project=self.tmp / 'project_atlas', unit_dir=self.tmp / 'units', env_dir=self.tmp / 'envdir', runtime_unit_dir=self.tmp / 'run-units',
              evidence_root=self.tmp / 'evidence', steady_s=3, preflight_s=2, observer_warmup_s=0.5,
              mux_back_timeout_s=6.0, hold_poll_s=0.2)
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
        # spike inside the bound, then recovery. Bound 6 s: the new-mux proof (dashboard + 1.5 s fresh observer after
        # it, behind the simulated 1.5 s bridge lag) takes about 4 s here; the real bound is 15 s.
        self.cpu = [62.0] * 6 + [90.0, 99.0] + [62.0] * 40
        self.assertEqual(self.run_step('mux', bound=6.0), 0)
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
        self.assertIn('new mux proven on the dashboard', log); self.assertIn('exemption cleared', log)

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
        self.cpu = [62.0] * 6 + [99.0] * 9 + [62.0] * 60      # over the limit past the 6 s bound, after the mux is proven
        self.assertEqual(self.run_step('mux', bound=6.0), 1)
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
        self.assertIn('web_drive absent in 3/3', (self.result('deploy-web')[1] / 'log.txt').read_text())
        self.assertEqual(self.run_step('web'), 3)             # already installed: refused

    def test_web_drive_present_and_not_stop_after_restart_rolls_back(self):
        self.deploy_mux()
        self.assertEqual(self.run_step('teleop'), 0)
        self.rover.web_drive_after_restart = '0.10,0.00'
        self.assertEqual(self.run_step('web'), 1)
        r, _ = self.result('deploy-web')
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK'); self.assertIn('web_drive_stop', r['reason'])

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


class Commissioning(Base):
    def deploy_all(self):
        self.cpu = []
        for step in D.REQUIRED_STEPS:          # what the rover has: A1-A3
            self.assertEqual(self.run_step(step), 0, step)

    def act(self, *argv):
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            return D.main(list(argv) + ['--owner-confirms-estop-latched', '--owner-confirms-rover-lifted-and-clear'], env=self.env)

    def cfg(self):
        return json.loads((self.env.project / 'config/atlas_flysky_drive.json').read_text())

    def test_review_gate_on_gate_off(self):
        self.deploy_all()
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 3)              # unreviewed: refused, no change
        self.assertFalse(any(g.exists() for g in D.gate_paths(self.env)))
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            self.assertEqual(D.main(['review-config'], env=self.env), 2)             # needs the explicit flag
            self.assertEqual(D.main(['review-config', '--owner-reviewed-config'], env=self.env), 0)
        c = self.cfg()
        self.assertTrue(c['reviewed_by_owner']); self.assertEqual(c['max_linear_mps'], 0.05); self.assertEqual(c['max_angular_radps'], 0.2)
        mux0 = self.restarts(D.UNITS['mux'])
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 0)
        self.assertTrue(all(g.exists() for g in D.gate_paths(self.env)))
        self.assertEqual(self.restarts(D.UNITS['mux']), mux0 + 1)
        self.assertTrue(json.loads(self.env.get('/api/status')['ros']['control_policy']['value'])['flysky_drive_enabled'])
        self.env.estop = False
        self.assertEqual(self.act('gate-off'), 3)                                    # released: refused
        self.env.estop = True
        self.assertEqual(self.act('gate-off'), 0)
        self.assertFalse(any(g.exists() for g in D.gate_paths(self.env)))
        self.assertFalse(json.loads(self.env.get('/api/status')['ros']['control_policy']['value'])['flysky_drive_enabled'])

    def test_gate_on_refuses_above_caps(self):
        self.deploy_all()
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            D.main(['review-config', '--owner-reviewed-config'], env=self.env)
        p = self.env.project / 'config/atlas_flysky_drive.json'
        c = self.cfg(); c['max_linear_mps'] = 0.15; p.write_text(json.dumps(c))
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 3)
        self.assertIn('commissioning caps', self.result('gate-on')[0]['reason'])

    def test_gate_on_teleop_not_enabled_rolls_back(self):
        self.deploy_all()
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            D.main(['review-config', '--owner-reviewed-config'], env=self.env)
        self.rover.teleop_stays_disabled = True
        mux0 = self.restarts(D.UNITS['mux'])
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 1)
        self.assertEqual(self.result('gate-on')[0]['result'], 'FAIL_ROLLED_BACK')
        self.assertFalse(any(g.exists() for g in D.gate_paths(self.env)))
        self.assertEqual(self.restarts(D.UNITS['mux']), mux0 + 2)


class Preflight(Base):
    def test_preflight_is_read_only_and_go(self):
        self.assertEqual(D.main(['preflight'], env=self.env), 0)
        self.assertFalse(any(c[0] in ('restart', 'start', 'stop', 'daemon-reload') for c in self.rover.calls))

    def test_manifest_is_reproducible(self):
        import subprocess
        self.assertEqual(subprocess.run([sys.executable, str(PKG / 'refresh_manifest.py'), '--check']).returncode, 0)


if __name__ == '__main__':
    unittest.main()

class ViewStep(Commissioning):
    """The optional dual-controller dashboard step, chained on A3, never required for driving."""

    def test_view_deploys_on_a3_and_rolls_back_exactly(self):
        self.deploy_all()
        a3 = {rel: h(self.env.project / rel) for rel in MAN['steps']['view']['files'] if (self.env.project / rel).exists()}
        self.assertEqual(self.run_step('view'), 0)
        for rel, cand in CAND['view'].items():
            self.assertEqual(h(self.env.project / rel), cand, rel)
        for st in D.STEPS:
            self.assertTrue(D.step_done(self.env, st), st)          # web is superseded, not broken
        self.assertEqual(self.run_step('view'), 3)                   # already installed: refused
        ev = next(d for d in sorted(self.env.evidence_root.glob('stage29-deploy-view-*')) if (d / 'backup/meta.json').exists())
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            self.assertEqual(D.main(['rollback', '--step', 'view', '--evidence', str(ev), '--owner-confirms-estop-latched',
                                     '--owner-confirms-rover-lifted-and-clear'], env=self.env), 0)
        for rel, sha in a3.items():
            self.assertEqual(h(self.env.project / rel), sha, rel)
        self.assertFalse((self.env.project / 'scripts/atlas_controller_input_web.py').exists())
        self.assertTrue(all(D.step_done(self.env, st) for st in D.REQUIRED_STEPS)); self.assertFalse(D.step_done(self.env, 'view'))

    def test_view_needs_a3_and_bad_layout_rolls_back(self):
        self.cpu = []
        for st in ('mux', 'teleop'):
            self.assertEqual(self.run_step(st), 0)
        self.assertEqual(self.run_step('view'), 3)                   # A3 missing: refused, nothing changed
        self.assertEqual(self.run_step('web'), 0)
        self.rover.bad_joy_layout = True
        self.assertEqual(self.run_step('view'), 1)                   # verification fails -> rolled back to A3
        self.assertTrue(D.step_done(self.env, 'web')); self.assertFalse(D.step_done(self.env, 'view'))

    def test_gate_on_works_with_or_without_view(self):
        self.deploy_all()
        self.assertEqual(self.run_step('view'), 0)
        self.assertEqual(self.act('review-config', '--owner-reviewed-config'), 0)
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 0)
        self.assertEqual(self.act('gate-off', '--cpu-bound-s', '3'), 0)


class GateOnOldMuxLingers(Commissioning):
    """gate-on attempt 1, 2026-10-29 15:51: the old mux kept publishing about 1 s after the restart command."""

    def test_old_mux_data_cannot_clear_the_exemption(self):
        self.deploy_all()
        self.assertEqual(self.act('review-config', '--owner-reviewed-config'), 0)
        self.rover.old_mux_lingers_s = 1.0
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 0)
        ev = sorted(self.env.evidence_root.glob('stage29-gate-on-*'))[-1]
        log = (ev / 'log.txt').read_text()
        self.assertIn('new mux proven on the dashboard (flysky_drive_enabled True)', log)
        proven = float(log.split('flysky_drive_enabled True) after ')[1].split(' s')[0])
        self.assertGreaterEqual(proven, 1.0)                  # not the lingering old mux
        self.assertEqual(self.act('gate-off', '--cpu-bound-s', '3'), 0)


class GateOnHold(Commissioning):
    """CPU-only overrun HOLDs (no rollback restart); every real safety problem still rolls back (2026-10-29 16:29)."""

    def reviewed(self):
        self.deploy_all()
        self.assertEqual(self.act('review-config', '--owner-reviewed-config'), 0)
        self.mux_restarts0 = self.restarts(D.UNITS['mux'])
        self.rover.trigger_after = time.time()

    def last(self):
        ev = sorted(self.env.evidence_root.glob('stage29-gate-on-*'))[-1]
        return json.loads(next(ev.glob('*result.json')).read_text()), (ev / 'log.txt').read_text()

    def test_cpu_only_after_new_mux_proven_holds_without_restart(self):
        self.reviewed()
        self.cpu = [62.0] * 9 + [99.0] * 12 + [62.0] * 80          # over the 3 s bound well after the mux is proven
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 1)
        r, log = self.last()
        self.assertEqual(r['result'], 'FAIL_HELD', log)
        self.assertIn('CPU > 75.0 after the 3.0 s bound', r['reason'])         # after the wait: classified CPU-only
        self.assertEqual(self.restarts(D.UNITS['mux']) - self.mux_restarts0, 1)   # gate-on restart only, no rollback
        self.assertTrue(all(g.exists() for g in D.gate_paths(self.env)))        # held as is for the owner
        self.assertIn('held state', log); self.assertIn('owner decides', log)

    def test_cpu_only_during_mux_back_wait_holds(self):
        self.reviewed()
        self.rover.bridge_lag_s = 3.0                     # the wait runs past the bound; mux proven, observer OK
        self.cpu = [62.0] * 9 + [99.0] * 12 + [62.0] * 80
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '4.5'), 1)
        r, log = self.last()
        self.assertEqual(r['result'], 'FAIL_HELD', log)
        self.assertIn('mux-back: CPU > 75.0 after the 4.5 s bound', r['reason'])
        self.assertIn('new mux proven and every independent safety check healthy', r['reason'])
        self.assertEqual(self.restarts(D.UNITS['mux']) - self.mux_restarts0, 1)
        self.assertTrue(all(g.exists() for g in D.gate_paths(self.env)))

    def test_cpu_over_bound_before_mux_proven_rolls_back(self):
        self.reviewed()
        self.rover.old_mux_lingers_s = 6.0                          # the new mux is not proven for about 6 s
        self.cpu = [62.0] * 9 + [99.0] * 12 + [62.0] * 80
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 1)
        r, log = self.last()
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK', log)
        self.assertIn('new mux not yet proven', r['reason'])
        self.assertFalse(any(g.exists() for g in D.gate_paths(self.env)))

    def test_safety_failure_rolls_back_immediately(self):
        self.reviewed()
        self.rover.fail_base_after_restart = True                   # base-owned signal fails in the window
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 1)
        r, log = self.last()
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK', log)
        self.assertIn('safety failure', r['reason'])
        self.assertFalse(any(g.exists() for g in D.gate_paths(self.env)))

    def test_unresponsive_observer_is_not_cpu_only(self):
        self.reviewed()
        self.rover.observer_freeze_after_restart = True
        self.cpu = [62.0] * 9 + [99.0] * 12 + [62.0] * 80
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 1)
        r, log = self.last()
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK', log)
        self.assertIn('safety monitoring not operating reliably', r['reason'])

    def test_preflight_accepts_exactly_the_reviewed_config(self):
        self.reviewed()
        self.assertEqual(D.main(['preflight'], env=self.env), 0)
        ev = sorted(self.env.evidence_root.glob('stage29-preflight-*'))[-1]
        self.assertIn('owner-reviewed commissioning config', (ev / 'log.txt').read_text())
        cfg = self.cfg(); cfg['max_linear_mps'] = 0.04                # any other edit is not the reviewed config
        (self.env.project / 'config/atlas_flysky_drive.json').write_text(json.dumps(cfg))
        self.assertEqual(D.main(['preflight'], env=self.env), 1)
