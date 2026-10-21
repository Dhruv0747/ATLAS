"""Stage31 deployment package rehearsal on a copy of the verified live baseline (commit 1cbc000 == live hashes)."""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage31/stage31.sh'
BASE = '1cbc0001a9b9f08286f587f7cd5da4af02c3a3f9'
FILES = ['web/v2/index.html', 'web/v2/vision3d.html', 'web/v2/vision3d.js', 'web/v2/vision3d.css',
         'scripts/atlas_vision3d_runtime.py', 'scripts/atlas_vision3d_web.py']
LIVE_INDEX = 'f53d68120ecdb82efa0d942ec5519712e283ee511dc02e3b2cbdc88cc12a53c0'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Stage31Package(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        try:
            for f in FILES:
                data = subprocess.run(['git', 'show', '%s:project_atlas/%s' % (BASE, f)], cwd=ROOT, capture_output=True, check=True).stdout
                (self.t / f).parent.mkdir(parents=True, exist_ok=True); (self.t / f).write_bytes(data)
        except Exception:
            self.skipTest('git history unavailable')
        # live index carries one extra title attribute compared with the repository; use the exact live bytes
        shutil.copy(ROOT / 'web/v2/classic.html', self.t / 'web/v2/index.html')
        self.assertEqual(sha(self.t / 'web/v2/index.html'), LIVE_INDEX)
        self.before = {f: (self.t / f).read_bytes() for f in FILES}
        self.env = {**os.environ, 'TARGET': str(self.t), 'SRC': str(ROOT), 'STAMP': 'x', 'NO_RESTART': 'yes', 'SKIP_SAFETY_CHECK': 'yes'}

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def run_pkg(self, *args, **env):
        return subprocess.run(['bash', str(PKG), *args], env={**self.env, **env}, capture_output=True, text=True)

    def test_refuses_without_approval_and_on_drift(self):
        r = self.run_pkg('apply-ui'); self.assertEqual(r.returncode, 2); self.assertIn('OWNER_APPROVED', r.stderr)
        (self.t / 'web/v2/vision3d.js').write_text('// drift\n')
        r = self.run_pkg('apply-ui', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 2); self.assertIn('baseline', r.stderr)
        self.assertFalse((self.t / 'web/v2/home.css').exists())

    def test_ui_apply_is_static_guarded_and_rollback_byte_identical(self):
        r = self.run_pkg('apply-ui', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('systemctl', r.stdout)
        for f in ('web/v2/index.html', 'web/v2/home.css', 'web/v2/home-cards.js', 'web/v2/classic.html', 'web/v2/vision3d.js'):
            self.assertEqual(sha(self.t / f), sha(ROOT / f), f)
        self.assertEqual(sha(self.t / 'web/v2/classic.html'), LIVE_INDEX)
        self.assertEqual(self.run_pkg('apply-ui', OWNER_APPROVED='yes').returncode, 2)       # second apply refused
        r = self.run_pkg('rollback-ui', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 0, r.stderr)
        for f, b in self.before.items():
            self.assertEqual((self.t / f).read_bytes(), b, f)
        for f in ('web/v2/home.css', 'web/v2/home-cards.js', 'web/v2/classic.html'):
            self.assertFalse((self.t / f).exists(), f)

    def test_astra_apply_and_rollback(self):
        r = self.run_pkg('apply-astra', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('NO_RESTART=yes', r.stdout)
        for f in ('scripts/atlas_vision3d_runtime.py', 'scripts/atlas_vision3d_web.py'):
            self.assertEqual(sha(self.t / f), sha(ROOT / f))
        self.assertEqual(self.run_pkg('apply-astra', OWNER_APPROVED='yes').returncode, 2)
        r = self.run_pkg('rollback-astra', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 0, r.stderr)
        for f, b in self.before.items():
            self.assertEqual((self.t / f).read_bytes(), b, f)

    def test_package_touches_only_rover_status_web(self):
        text = PKG.read_text()
        self.assertEqual(text.count('systemctl --user restart'), 1)
        self.assertIn('systemctl --user restart rover-status-web', text)
        for bad in ('stop rover-base', 'restart rover-base', 'atlas-nav2', 'reboot', 'ATLAS_PID_LIFTED', 'cmd_vel', '/dev/tty', 'estop/reset', 'action=e_stop'):
            self.assertNotIn(bad, text, bad)
        for word in ('cpu>75', '75'):
            pass
        self.assertNotIn('limits(', text)


if __name__ == '__main__':
    unittest.main()
