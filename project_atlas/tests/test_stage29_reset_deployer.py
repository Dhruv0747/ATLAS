"""Stage 29 `reset` deploy step (FlySky SwD E-STOP reset), end to end on the fake rover of test_stage29_deployer.

The real deployer, Stage 28 CPU recorder / observer recorder / gates and the mux lease run unchanged; only system
access is faked. The fake mux reports policy flysky_reset.enabled only when the reset-patched mux restarts with the
reset drop-in present; the fake teleop reports its reset status the same way."""
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import test_stage29_deployer as T   # noqa: E402
from test_stage29_deployer import D, MAN, h   # noqa: E402

RESET_FILES = MAN['steps']['reset']['files']
MUX = 'scripts/atlas_cmd_vel_mux.py'


class ResetRover(T.FakeRover):
    def __init__(self, env):
        super().__init__(env)
        self.mux_reset, self.old_reset = False, False
        self.controller = 'XBOX'
        self.reset_never = False           # scenario: the new mux never reports the reset enabled
        self.reset_requests = 0            # scenario: reset requests seen with Xbox selected
        self.teleop_reset = False

    def reset_dropin(self, unit):
        return (self.env.runtime_unit_dir / f'{unit}.d' / D.RESET_DROPIN).exists()

    def systemctl(self, *args, timeout=30, check=True):
        out = super().systemctl(*args, timeout=timeout, check=check)
        if args[0] == 'restart' and args[1] == D.UNITS['mux']:
            self.old_reset = self.mux_reset
            self.mux_reset = (not self.reset_never and self.reset_dropin(D.UNITS['mux'])
                              and self.installed(MUX, 'reset'))
            self.teleop_reset = self.reset_dropin(D.UNITS['teleop']) and self.installed('scripts/atlas_flysky_teleop.py', 'reset')
        return out

    def get(self, path):
        v = super().get(path)
        if path == '/api/status':
            pol = json.loads(v['ros']['control_policy']['value'])
            lingering = time.time() < self.restart_at + self.old_mux_lingers_s
            if 'manual_controller' in pol:
                pol['manual_controller'] = self.controller
                on = self.old_reset if lingering else self.mux_reset
                if self.installed(MUX, 'reset') or on:
                    pol['flysky_reset'] = {'enabled': on, 'last_result': None, 'last_reason': '', 'age_s': None,
                                           'stationary': True}
            v['ros']['control_policy']['value'] = json.dumps(pol)
        return v

    def get_text(self, path):
        if path in ('/v2/flysky-drive', '/v2/flysky-drive.js'):
            f = self.env.project / ('web/v2/flysky-drive.html' if path == '/v2/flysky-drive' else 'web/v2/flysky-drive.js')
            return (200, f.read_text()) if f.exists() else (404, '')
        return super().get_text(path)

    def sample(self, wanted, seconds=3.0):
        out = super().sample([w for w in wanted if w != '/atlas/flysky/reset_request'], seconds)
        if '/atlas/flysky/reset_request' in wanted:
            out['/atlas/flysky/reset_request'] = {'advertised': self.teleop_reset, 'count': self.reset_requests, 'last': None}
        st = out.get('/atlas/flysky/drive_status')
        if st and st['last']:
            d = json.loads(st['last'])
            d['reset'] = ({'enabled': True, 'state': 'UNAVAILABLE', 'blocked': ['FlySky is not the selected controller']}
                          if self.teleop_reset else {'enabled': False, 'state': 'OFF'}) \
                if self.installed('scripts/atlas_flysky_teleop.py', 'reset') else None
            st['last'] = json.dumps(d)
        return out


class ResetBase(T.Commissioning):
    def setUp(self):
        super().setUp()
        self.rover = ResetRover(self.env)
        for name in ('systemctl', 'journal', 'get', 'get_text'):
            setattr(self.env, name, getattr(self.rover, name))
        self.env.sample_topics = self.rover.sample
        self.env.make_observer = self.rover.observer

    def gate_on_rover(self):
        """What ATLAS has today: all five Stage A steps, reviewed config, gate ON, Xbox selected, latched."""
        self.deploy_all()
        self.assertEqual(self.act('review-config', '--owner-reviewed-config'), 0)
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 0)
        self.live0 = {rel: h(self.env.project / rel) for rel in RESET_FILES if (self.env.project / rel).exists()}
        self.mux0, self.web0 = self.restarts(D.UNITS['mux']), self.restarts(D.UNITS['web'])
        self.rover.trigger_after = time.time()

    def deploy_reset(self, bound=6.0):
        return self.run_step('reset', bound=bound)

    def last(self, kind='deploy-reset'):
        ev = sorted(self.env.evidence_root.glob(f'stage29-{kind}-*'))[-1]
        return json.loads(next(ev.glob('*result.json')).read_text()), (ev / 'log.txt').read_text(), ev

    def at(self, which):
        return {rel: h(self.env.project / rel) == spec[which] for rel, spec in RESET_FILES.items()
                if which == 'candidate_sha256' or 'baseline_sha256' in spec}

    def dropins(self):
        return [p.exists() for p in D.reset_paths(self.env)]

    def assert_rolled_back(self):
        for rel, spec in RESET_FILES.items():
            p = self.env.project / rel
            if spec['kind'] == 'new':
                self.assertFalse(p.exists(), rel)
            else:
                self.assertEqual(h(p), spec['baseline_sha256'], rel)
        self.assertEqual(self.dropins(), [False, False])
        for st in D.STEPS:
            self.assertTrue(D.installed(self.env, st), st)          # the deployed Stage 29 state is intact


class ResetStep(ResetBase):
    def test_reset_preflight_then_deploy_pass(self):
        self.gate_on_rover()
        with mock.patch.dict(os.environ, {}):
            self.assertEqual(D.main(['preflight', '--step', 'reset'], env=self.env), 0)
        self.assertEqual(self.restarts(D.UNITS['mux']), self.mux0)                 # preflight changed nothing
        self.cpu = [62.0] * 6 + [95.0, 99.0] + [62.0] * 60                         # spike inside the bound
        self.assertEqual(self.deploy_reset(), 0)
        r, log, ev = self.last()
        self.assertEqual(r['result'], 'PASS', log)
        self.assertTrue(all(self.at('candidate_sha256').values()), self.at('candidate_sha256'))
        self.assertEqual(self.dropins(), [True, True])
        self.assertEqual(self.restarts(D.UNITS['mux']), self.mux0 + 1)              # ONE restart
        self.assertEqual(self.restarts(D.UNITS['web']), self.web0)                  # dashboard NOT restarted
        self.assertIn('mux maintenance lease armed (stage29 reset', log); self.assertIn('mux maintenance lease released', log)
        self.assertIn('new mux proven on the dashboard (flysky_reset enabled)', log)
        self.assertTrue((ev / 'backup/meta.json').exists())
        for st in D.STEPS:
            self.assertTrue(D.installed(self.env, st), st)                          # earlier steps: superseded, not broken
        self.assertTrue(D.step_done(self.env, 'reset'))
        pol = D.policy(self.env)
        self.assertTrue(pol['stop_latched']); self.assertEqual(pol['manual_controller'], 'XBOX')
        self.assertTrue(pol['flysky_reset']['enabled'])
        self.assertEqual(self.deploy_reset(), 3)                                    # already enabled: refused
        # the reviewed mapping and limits are untouched
        cfg = self.cfg()
        self.assertTrue(cfg['reviewed_by_owner']); self.assertEqual((cfg['max_linear_mps'], cfg['max_angular_radps']), (0.05, 0.2))
        self.assertTrue(D.reviewed_config_ok(self.env))

    def test_refusals_change_nothing(self):
        self.gate_on_rover()
        cases = []
        self.rover.controller = 'FLYSKY'; cases.append(('SELECT XBOX', self.deploy_reset())); self.rover.controller = 'XBOX'
        self.env.estop = False; cases.append(('not latched', self.deploy_reset())); self.env.estop = True
        p = self.env.project / 'scripts/atlas_flysky_teleop.py'; good = p.read_bytes()
        p.write_bytes(good + b'\n# drift\n'); cases.append(('teleop', self.deploy_reset())); p.write_bytes(good)
        c = self.env.project / 'config/atlas_flysky_drive.json'; cgood = c.read_text()
        cfg = json.loads(cgood); cfg['max_linear_mps'] = 0.04; c.write_text(json.dumps(cfg))
        cases.append(('step teleop is not installed', self.deploy_reset())); c.write_text(cgood)
        self.cpu = [62.0, 62.0] + [80.0] * 8; cases.append(('', self.deploy_reset())); self.cpu = []
        for want, rc in cases:
            self.assertEqual(rc, 3, want)
        self.assertEqual(self.restarts(D.UNITS['mux']), self.mux0)
        self.assertEqual({rel: h(self.env.project / rel) for rel in self.live0}, self.live0)
        self.assertFalse((self.env.project / 'scripts/atlas_flysky_reset.py').exists())
        self.assertEqual(self.dropins(), [False, False])
        reasons = [json.loads(next(d.glob('*result.json')).read_text()).get('reason', '')
                   for d in sorted(self.env.evidence_root.glob('stage29-deploy-reset-*'))]
        for want, got in zip([w for w, _ in cases], reasons):
            self.assertIn(want, got)

    def test_gate_off_rover_refuses(self):
        self.gate_on_rover()
        self.assertEqual(self.act('gate-off'), 0)
        n = self.restarts(D.UNITS['mux'])
        self.assertEqual(self.deploy_reset(), 3)
        self.assertIn('gate is OFF', self.last()[0]['reason'])
        self.assertEqual(self.restarts(D.UNITS['mux']), n)

    def test_stage_a_rover_without_features_refuses(self):
        self.deploy_all(D.STEPS[:4])
        self.assertEqual(self.deploy_reset(), 3)
        self.assertIn('step features is not installed', self.last()[0]['reason'])

    def test_cli_needs_approval_bound_and_confirmations(self):
        argv = ['deploy', '--step', 'reset', '--cpu-bound-s', '15', '--owner-confirms-estop-latched',
                '--owner-confirms-rover-lifted-and-clear']
        self.assertEqual(D.main(argv, env=self.env), 2)                             # no OWNER_APPROVED
        with mock.patch.dict(os.environ, {'OWNER_APPROVED': 'yes'}):
            self.assertEqual(D.main(argv[:3] + argv[5:], env=self.env), 2)          # no bound
            self.assertEqual(D.main(argv[:4] + ['31'] + argv[5:], env=self.env), 2)
            self.assertEqual(D.main(argv[:5], env=self.env), 2)                     # no confirmations
        self.assertEqual(self.rover.calls, [])


class ResetFailures(ResetBase):
    def test_teleop_not_enabled_rolls_back_exactly(self):
        self.gate_on_rover()
        self.rover.teleop_stays_disabled = True
        self.assertEqual(self.deploy_reset(), 1)
        r, log, _ = self.last()
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK', log); self.assertIn('teleop did not restart ENABLED', r['reason'])
        self.assert_rolled_back()
        self.assertEqual(self.restarts(D.UNITS['mux']), self.mux0 + 2)              # deploy + rollback restart
        self.assertIn('stage29 rollback reset mux restart', log)

    def test_new_mux_never_reports_reset_rolls_back(self):
        self.gate_on_rover()
        self.rover.reset_never = True
        self.assertEqual(self.deploy_reset(bound=10.0), 1)
        r, log, _ = self.last()
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK', log); self.assertIn('flysky_reset enabled', r['reason'])
        self.assert_rolled_back()

    def test_old_mux_lingering_cannot_prove_the_new_one(self):
        self.gate_on_rover()
        self.rover.old_mux_lingers_s = 1.0
        self.assertEqual(self.deploy_reset(), 0)
        log = self.last()[1]
        proven = float(log.split('(flysky_reset enabled) after ')[1].split(' s')[0])
        self.assertGreaterEqual(proven, 1.0)

    def test_base_signal_failure_in_window_rolls_back(self):
        self.gate_on_rover()
        self.rover.fail_base_after_restart = True
        self.assertEqual(self.deploy_reset(), 1)
        r, log, _ = self.last()
        self.assertEqual(r['result'], 'FAIL_ROLLED_BACK', log)
        self.assert_rolled_back()

    def test_reset_requests_or_commands_with_xbox_selected_roll_back(self):
        for attr, val in (('reset_requests', 3), ('advertise_cmd', True)):
            with self.subTest(attr):
                self.setUp()
                self.gate_on_rover()
                setattr(self.rover, attr, val)
                self.assertEqual(self.deploy_reset(), 1)
                self.assertEqual(self.last()[0]['result'], 'FAIL_ROLLED_BACK')
                self.assert_rolled_back()

    def test_cpu_only_overrun_holds_then_owner_rollback(self):
        self.gate_on_rover()
        self.cpu = [62.0] * 9 + [99.0] * 12 + [62.0] * 80                          # over the 3 s bound after the proof
        self.assertEqual(self.deploy_reset(bound=3.0), 1)
        r, log, ev = self.last()
        self.assertEqual(r['result'], 'FAIL_HELD', log)
        self.assertEqual(self.restarts(D.UNITS['mux']), self.mux0 + 1)              # no automatic second spike
        self.assertEqual(self.dropins(), [True, True])                              # held as is for the owner
        self.assertIn('rollback --step reset', log)
        self.assertEqual(self.act('rollback', '--step', 'reset', '--evidence', str(ev)), 0)
        self.assert_rolled_back()
        self.assertEqual(self.restarts(D.UNITS['mux']), self.mux0 + 2)
        self.assertFalse(D.reset_enabled_in(D.policy(self.env)))

    def test_rollback_after_pass_restores_the_deployed_stage29(self):
        self.gate_on_rover()
        self.assertEqual(self.deploy_reset(), 0)
        ev = self.last()[2]
        self.assertEqual(self.act('rollback', '--step', 'reset', '--evidence', str(ev)), 0)
        self.assert_rolled_back()
        self.assertTrue(all(g.exists() for g in D.gate_paths(self.env)))           # the gate is untouched by rollback


class ResetLifecycle(ResetBase):
    def test_gate_off_removes_reset_and_reboot_reenable_copies_nothing(self):
        self.gate_on_rover()
        self.assertEqual(self.deploy_reset(), 0)
        self.assertEqual(self.act('gate-off'), 0)                                   # one restart, both drop-ins gone
        self.assertEqual(self.dropins(), [False, False])
        self.assertFalse(any(g.exists() for g in D.gate_paths(self.env)))
        self.assertFalse(D.reset_enabled_in(D.policy(self.env)))
        # "reboot": runtime drop-ins are gone; reset FILES stay installed. gate-on still works on them.
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 0)
        self.assertFalse(D.reset_enabled_in(D.policy(self.env)))                    # gate on alone: reset stays off
        files = {rel: h(self.env.project / rel) for rel in RESET_FILES}
        n = self.restarts(D.UNITS['mux'])
        self.assertEqual(self.deploy_reset(), 0)
        r, log, _ = self.last()
        self.assertIn('files already installed (re-enable only)', log)
        self.assertIn('installed: nothing (files already installed)', log)
        self.assertEqual({rel: h(self.env.project / rel) for rel in RESET_FILES}, files)
        self.assertEqual(self.restarts(D.UNITS['mux']), n + 1)
        self.assertTrue(D.reset_enabled_in(D.policy(self.env)))

    def test_stage_a_preflight_reports_the_reset_step(self):
        self.gate_on_rover()
        self.assertEqual(self.deploy_reset(), 0)
        D.main(['preflight'], env=self.env)                     # the Stage A preflight is NO-GO with the gate on, by design
        log = (sorted(self.env.evidence_root.glob('stage29-preflight-2*'))[-1] / 'log.txt').read_text()
        self.assertIn('step reset: files INSTALLED (FlySky SwD reset ENABLED)', log)
        for st in D.STEPS:
            self.assertIn(f'step {st}: INSTALLED', log)


class ResetManifest(unittest.TestCase):
    def test_existing_steps_still_describe_the_rover(self):
        """The reset work must not change what the five deployed steps describe (verified on the rover 2026-10-30)."""
        live = {'teleop': {'scripts/atlas_flysky_teleop.py': 'feecba2cb9e6'},
                'view': {'web/v2/flysky-drive.html': 'b5b4f12e301f', 'web/v2/flysky-drive.js': 'dd02e0e51787',
                         'web/v2/controller-map.js': '8f1f302b1d6c', 'web/v2/controller-viz.js': '545aebf93894'},
                'mux': {MUX: '5d096638bf3c'}}
        for st, files in live.items():
            for rel, pref in files.items():
                self.assertTrue(MAN['steps'][st]['files'][rel]['candidate_sha256'].startswith(pref), (st, rel))
        for rel, spec in RESET_FILES.items():
            if 'baseline_sha256' in spec:
                st = 'mux' if rel == MUX else 'teleop' if rel.endswith('teleop.py') else 'view'
                self.assertEqual(spec['baseline_sha256'], MAN['steps'][st]['files'][rel]['candidate_sha256'], rel)
        self.assertEqual(set(RESET_FILES), {'scripts/atlas_flysky_reset.py', MUX, 'scripts/atlas_flysky_teleop.py',
                                             'web/v2/flysky-drive.html', 'web/v2/flysky-drive.js',
                                             'web/v2/controller-map.js', 'web/v2/controller-viz.js'})

    def test_reset_never_touches_the_drive_core_config_remote_stop_or_firmware(self):
        for rel in RESET_FILES:
            self.assertNotIn(rel, ('scripts/atlas_flysky_drive_core.py', 'config/atlas_flysky_drive.json',
                                   'scripts/atlas_remote_stop.py'))
        src = (ROOT / 'tools/deploy/stage29_flysky_drive/deploy_stage29.py').read_text()
        body = src.split('# ------------------------------------------------------------------ FlySky SwD E-STOP reset')[1].split('def require_latched')[0]
        for bad in ('/api/estop/reset', 'remote_stop/reset', 'select_flysky', 'publish', "'/cmd_vel'", 'serial', 'firmware', "'start'",
                    'POST', 'method='):
            self.assertNotIn(bad, body, bad)
        self.assertEqual(body.count("env.systemctl('restart'"), 2)        # the deploy restart and the rollback restart only


if __name__ == '__main__':
    unittest.main()
