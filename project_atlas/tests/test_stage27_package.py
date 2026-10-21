import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage27_flysky'


def h16(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]


class Package(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        (self.t / 'scripts').mkdir(); (self.t / 'web/v2').mkdir(parents=True)
        # stand-in for the live Stage 26 tree: the repo files minus the FlySky hooks / link
        s = (ROOT / 'scripts/atlas_status_web.py').read_text()
        for line in ("import atlas_flysky_web   # FlySky Remote Test Lab (additive; read-only, lazy subscriber, no publishers)\n",
                     "        if atlas_flysky_web.serve(self, ROS):\n            return\n", "        if atlas_flysky_web.serve(self, ROS, post=True):\n            return\n"):
            self.assertEqual(s.count(line), 1); s = s.replace(line, '')
        w = (ROOT / 'scripts/atlas_web_v2.py').read_text().replace(", 'flysky-testlab': 'flysky-testlab.html'", '')
        idx = (ROOT / 'web/v2/index.html').read_text()
        idx = '\n'.join(l for l in idx.splitlines() if 'flysky' not in l.lower() and 'lblShort' not in l and 'lblFull' not in l) + '\n'
        (self.t / 'scripts/atlas_status_web.py').write_text(s); (self.t / 'scripts/atlas_web_v2.py').write_text(w); (self.t / 'web/v2/index.html').write_text(idx)
        for f in ('atlas_testlab_web.py', 'atlas_wifi_web.py'):
            shutil.copy(ROOT / 'scripts' / f, self.t / 'scripts' / f)
        self.pre = {k: h16(self.t / v) for k, v in (('PRE_STATUS_WEB', 'scripts/atlas_status_web.py'), ('PRE_WEB_V2', 'scripts/atlas_web_v2.py'), ('PRE_INDEX', 'web/v2/index.html'))}
        self.env = {**os.environ, **self.pre, 'TARGET': str(self.t), 'SRC': str(ROOT), 'STAMP': 'x', 'NO_RESTART': 'yes', 'SKIP_SAFETY_CHECK': 'yes'}

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def run_sh(self, name, **extra):
        return subprocess.run(['bash', str(PKG / name)], env={**self.env, **extra}, capture_output=True, text=True)

    def test_refuses_without_owner_approval(self):
        r = self.run_sh('apply.sh'); self.assertEqual(r.returncode, 2); self.assertIn('OWNER_APPROVED', r.stderr)
        self.assertFalse((self.t / 'scripts/atlas_flysky_web.py').exists())

    def test_refuses_when_live_hash_differs(self):
        (self.t / 'scripts/atlas_status_web.py').write_text((self.t / 'scripts/atlas_status_web.py').read_text() + '\n# drift\n')
        r = self.run_sh('apply.sh', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 2); self.assertIn('expected', r.stderr)

    def test_refuses_without_estop_latched(self):
        env = dict(self.env); env.pop('SKIP_SAFETY_CHECK'); env['OWNER_APPROVED'] = 'yes'
        r = subprocess.run(['bash', str(PKG / 'apply.sh')], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2); self.assertIn('E-STOP', r.stderr)

    def test_apply_is_additive_idempotent_guarded_and_rollback_is_byte_identical(self):
        before = {f: (self.t / f).read_bytes() for f in ('scripts/atlas_status_web.py', 'scripts/atlas_web_v2.py', 'web/v2/index.html')}
        r = self.run_sh('apply.sh', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        for f in ('scripts/atlas_flysky_core.py', 'scripts/atlas_flysky_web.py', 'web/v2/flysky-testlab.html', 'web/v2/flysky-testlab.js', 'web/v2/flysky.css'):
            self.assertTrue((self.t / f).exists(), f)
        s = (self.t / 'scripts/atlas_status_web.py').read_text(); old = before['scripts/atlas_status_web.py'].decode()
        self.assertEqual([l for l in old.splitlines() if l not in s.splitlines()], [])           # nothing removed
        self.assertEqual(len([l for l in s.splitlines() if 'flysky' in l.lower()]), 3)
        self.assertIn("'flysky-testlab'", (self.t / 'scripts/atlas_web_v2.py').read_text())
        self.assertEqual(self.run_sh('apply.sh', OWNER_APPROVED='yes').returncode, 2)             # second apply refused
        self.assertNotIn('atlas_flysky', (self.t / '.pre_stage27_flysky_x/scripts/atlas_status_web.py').read_text())
        r = self.run_sh('rollback.sh'); self.assertEqual(r.returncode, 0, r.stderr)
        for f, b in before.items():
            self.assertEqual((self.t / f).read_bytes(), b, f)
        self.assertFalse(any((self.t / f).exists() for f in ('scripts/atlas_flysky_core.py', 'scripts/atlas_flysky_web.py', 'web/v2/flysky-testlab.html')))

    def test_package_only_touches_flysky_and_never_the_motor_side(self):
        text = ''.join((PKG / n).read_text() for n in ('apply.sh', 'rollback.sh', 'insert_hooks.py'))
        for bad in ('yahboom', 'rover-base', 'rover-radar', 'ros2 ', 'systemctl --user stop', 'reboot', 'ATLAS_PID_LIFTED', '/dev/tty', 'cmd_vel'):
            self.assertNotIn(bad, text, bad)
        self.assertEqual(text.count('systemctl --user restart'), 2)     # apply + rollback, rover-status-web only
        self.assertEqual(text.count('restart rover-status-web'), 2)


if __name__ == '__main__':
    unittest.main()
