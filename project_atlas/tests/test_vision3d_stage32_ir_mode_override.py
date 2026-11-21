"""Stage32 D2: temporary 640x480 IR override is one line, IR-only, and restores byte-identically. Files only."""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/vision3d/stage32_ir_mode_override.py'
sys.path.insert(0, str(ROOT / 'scripts'))


def load_runtime(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Override(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.f = self.d / 'scripts/atlas_vision3d_runtime.py'; self.f.parent.mkdir()
        # The repository now carries the accepted 640x480 line; rebuild the pre-correction Stage32 baseline (454dd25f)
        src = (ROOT / 'scripts/atlas_vision3d_runtime.py').read_bytes()
        self.f.write_bytes(src.replace(b"ir_width='640',ir_height='480'", b"ir_width='320',ir_height='240'"))
        self.base = self.f.read_bytes()
        self.env = dict(os.environ, ATLAS_RUNTIME_FILE=str(self.f), ATLAS_IR_DIAG_STATE=str(self.d / 'state'))

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_tool(self, cmd, ok=True):
        env = dict(self.env, OWNER_APPROVED='yes') if ok else self.env
        return subprocess.run([sys.executable, str(TOOL), cmd], env=env, capture_output=True, text=True)

    def test_refuses_without_approval(self):
        self.assertNotEqual(self.run_tool('apply', ok=False).returncode, 0)
        self.assertEqual(self.f.read_bytes(), self.base)

    def test_apply_changes_only_ir_resolution_then_restores(self):
        shutil.copy2(self.f, self.d / 'scripts/rt_base.py'); base = load_runtime(self.d / 'scripts/rt_base.py', 'rt_base')
        p = self.run_tool('apply'); self.assertEqual(p.returncode, 0, p.stderr)
        new = load_runtime(self.f, 'rt_over')
        ir = new.driver_args('ir')
        self.assertIn('ir_width:=640', ir); self.assertIn('ir_height:=480', ir); self.assertIn('ir_fps:=30', ir)
        self.assertNotIn('ir_width:=320', ir)
        strip = lambda a: [x for x in a if not x.startswith(str(base.RUNTIME))]
        for mode in ('depth', 'concurrent', 'depth_cloud'):
            self.assertEqual(strip(new.driver_args(mode)), strip(base.driver_args(mode)))
        diff = [i for i, (a, b) in enumerate(zip(self.base.splitlines(), self.f.read_bytes().splitlines())) if a != b]
        self.assertEqual(len(diff), 1)
        self.assertNotEqual(self.run_tool('apply').returncode, 0)          # second apply refused
        p = self.run_tool('restore'); self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.f.read_bytes(), self.base)

    def test_baseline_rebuild_is_the_verified_hash(self):
        import hashlib
        self.assertEqual(hashlib.sha256(self.base).hexdigest(), '454dd25fd0e5bafbb25b63983af865cca78a01354547e4129c2e2016b8023151')
        self.assertEqual(hashlib.sha256((ROOT / 'scripts/atlas_vision3d_runtime.py').read_bytes()).hexdigest(),
                         'fc807489b06699d73efdd246913849a3d11315d6bfcba707eedd0e1381c9b5aa')   # deployed production hash

    def test_refuses_unknown_runtime(self):
        self.f.write_bytes(self.base + b'\n# edited\n')
        self.assertNotEqual(self.run_tool('apply').returncode, 0)


if __name__ == '__main__':
    unittest.main()
