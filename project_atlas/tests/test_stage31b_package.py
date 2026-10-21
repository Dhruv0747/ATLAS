"""Stage31b candidate package: apply/refuse/rollback on a copy of the deployed Stage 31 files (commit b00b231)."""
import hashlib, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'tools/deploy/stage31b/stage31b.sh'
FILES = ['scripts/atlas_vision3d_runtime.py', 'web/v2/vision3d.js']
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Package(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        try:
            for f in FILES:
                data = subprocess.run(['git', 'show', 'b00b231:project_atlas/' + f], cwd=ROOT, capture_output=True, check=True).stdout
                (self.t / f).parent.mkdir(parents=True, exist_ok=True); (self.t / f).write_bytes(data)
        except Exception:
            self.skipTest('git history unavailable')
        self.before = {f: (self.t / f).read_bytes() for f in FILES}
        self.env = {**os.environ, 'TARGET': str(self.t), 'SRC': str(ROOT), 'STAMP': 'x', 'SKIP_SAFETY_CHECK': 'yes'}

    def tearDown(self): shutil.rmtree(self.t, ignore_errors=True)

    def run_pkg(self, *a, **e): return subprocess.run(['bash', str(PKG), *a], env={**self.env, **e}, capture_output=True, text=True)

    def test_refuses_without_approval_or_on_drift(self):
        self.assertEqual(self.run_pkg('apply').returncode, 2)
        (self.t / FILES[1]).write_text('// drift')
        r = self.run_pkg('apply', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 2); self.assertIn('baseline', r.stderr)

    def test_apply_no_restart_and_byte_identical_rollback(self):
        r = self.run_pkg('apply', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('no service restarted', r.stdout)
        for f in FILES: self.assertEqual(sha(self.t / f), sha(ROOT / f))
        self.assertEqual(self.run_pkg('apply', OWNER_APPROVED='yes').returncode, 2)
        r = self.run_pkg('rollback', OWNER_APPROVED='yes'); self.assertEqual(r.returncode, 0, r.stderr)
        for f, b in self.before.items(): self.assertEqual((self.t / f).read_bytes(), b)

    def test_package_restarts_and_pauses_nothing(self):
        import re
        code = '\n'.join(l for l in PKG.read_text().splitlines() if not l.lstrip().startswith('#'))
        code = re.sub(r'"[^"]*"', '""', code)          # ignore message strings; check only executed commands
        for bad in ('systemctl', 'restart', 'kill', 'nice', 'reboot', 'pause'):
            self.assertNotIn(bad, code, bad)


if __name__ == '__main__':
    unittest.main()
