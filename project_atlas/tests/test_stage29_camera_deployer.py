"""Stage 29 `camera` deploy step (FlySky VrA/VrB camera knobs) on the fake rover: a NEW service only, started once;
no existing service restarts; any unexpected servo command or policy change rolls back."""
import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import test_stage29_reset_deployer as R   # noqa: E402
from test_stage29_deployer import D, MAN, h   # noqa: E402

CAM = D.UNITS['camera']
CAM_FILES = MAN['steps']['camera']['files']


class CameraRover(R.ResetRover):
    def __init__(self, env):
        super().__init__(env)
        self.units[CAM] = {'pid': 5000, 'active': False, 'inv': f'inv-{CAM}-0', 'log': ''}
        self.camera_cmds = 0            # scenario: servo commands seen with the knobs untouched
        self.camera_crash = False

    def systemctl(self, *args, timeout=30, check=True):
        out = super().systemctl(*args, timeout=timeout, check=check)
        if args[0] == 'start' and args[1] == CAM:
            self.units[CAM]['log'] = 'Traceback (most recent call last)' if self.camera_crash else \
                'FlySky camera ready: VrA (CH9) pan, VrB (CH10) tilt'
        return out

    def get_text(self, path):
        if path == '/v2/controller-map.js':
            f = self.env.project / 'web/v2/controller-map.js'
            return (200, f.read_text()) if f.exists() else (404, '')
        return super().get_text(path)

    def sample(self, wanted, seconds=3.0):
        cam = [w for w in wanted if w.startswith('/camera/')]
        out = super().sample([w for w in wanted if w not in cam], seconds) if len(cam) < len(wanted) else {}
        for w in cam:
            out[w] = {'advertised': True, 'count': self.camera_cmds, 'last': None}
        return out


class CameraBase(R.ResetBase):
    def setUp(self):
        super().setUp()
        self.rover = CameraRover(self.env)
        for name in ('systemctl', 'journal', 'get', 'get_text'):
            setattr(self.env, name, getattr(self.rover, name))
        self.env.sample_topics = self.rover.sample
        self.env.make_observer = self.rover.observer

    def reset_rover(self):
        self.gate_on_rover()
        self.assertEqual(self.deploy_reset(), 0)
        self.counts0 = {u: self.restarts(u) for u in (D.UNITS['mux'], D.UNITS['web'], D.UNITS['teleop'], D.UNITS['features'])}

    def deploy_camera(self, bound=5.0):
        return self.run_step('camera', bound=bound)

    def assert_nothing_else_restarted(self):
        for u, n in self.counts0.items():
            self.assertEqual(self.restarts(u), n, u)


class CameraStep(CameraBase):
    def test_preflight_then_deploy_starts_only_the_new_service(self):
        self.reset_rover()
        self.assertEqual(R.D.main(['preflight', '--step', 'camera'], env=self.env), 0)
        self.assertEqual(self.deploy_camera(), 0)
        r, log, ev = self.last('deploy-camera')
        self.assertEqual(r['result'], 'PASS', log)
        for rel, spec in CAM_FILES.items():
            dst = (self.env.unit_dir / Path(rel).name) if spec['kind'] == 'unit' else (self.env.project / rel)
            self.assertEqual(h(dst), spec['candidate_sha256'], rel)
        self.assertEqual(self.restarts(CAM), 1)
        self.assert_nothing_else_restarted()
        self.assertNotIn('lease', log)                                      # the mux is not touched
        for st in D.STEPS + ('reset',):
            self.assertTrue(D.step_done(self.env, st, ignore=(D.CONFIG_REL,)), st)   # earlier steps superseded, not broken
        self.assertTrue(D.step_done(self.env, 'camera'))
        self.assertEqual(self.deploy_camera(), 3)                           # already installed: refused
        self.assertTrue(D.policy(self.env)['stop_latched'])

    def test_needs_the_reset_step_and_a_latched_estop(self):
        self.gate_on_rover()
        self.assertEqual(self.deploy_camera(), 3)
        self.assertIn('step reset is not installed', self.last('deploy-camera')[0]['reason'])
        self.assertEqual(self.deploy_reset(), 0)
        self.env.estop = False
        self.assertEqual(self.deploy_camera(), 3)
        self.assertIn('not latched', self.last('deploy-camera')[0]['reason'])
        self.assertFalse((self.env.project / 'scripts/atlas_flysky_camera.py').exists())

    def test_crash_or_unexpected_servo_commands_roll_back(self):
        for attr in ('camera_crash', 'camera_cmds'):
            with self.subTest(attr):
                self.setUp()
                self.reset_rover()
                setattr(self.rover, attr, True if attr == 'camera_crash' else 4)
                self.assertEqual(self.deploy_camera(), 1)
                r, log, _ = self.last('deploy-camera')
                self.assertEqual(r['result'], 'FAIL_ROLLED_BACK', log)
                self.assertFalse((self.env.project / 'scripts/atlas_flysky_camera.py').exists())
                self.assertFalse((self.env.unit_dir / 'atlas-flysky-camera.service').exists())
                self.assertEqual(h(self.env.project / 'web/v2/controller-map.js'), CAM_FILES['web/v2/controller-map.js']['baseline_sha256'])
                self.assertFalse(self.rover.units[CAM]['active'])
                self.assertTrue(D.step_done(self.env, 'reset'))
                self.assert_nothing_else_restarted()

    def test_reset_reenable_still_works_with_camera_installed(self):
        self.reset_rover()
        self.assertEqual(self.deploy_camera(), 0)
        self.assertEqual(self.act('gate-off'), 0)
        self.assertEqual(self.act('gate-on', '--cpu-bound-s', '3'), 0)
        self.assertEqual(self.deploy_reset(), 0)
        self.assertIn('files already installed (re-enable only)', self.last()[1])
        self.assertTrue(D.step_done(self.env, 'camera'))


if __name__ == '__main__':
    unittest.main()
