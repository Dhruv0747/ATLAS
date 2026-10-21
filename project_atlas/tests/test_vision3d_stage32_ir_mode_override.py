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
        shutil.copy2(ROOT / 'scripts/atlas_vision3d_runtime.py', self.f)
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
        base = load_runtime(ROOT / 'scripts/atlas_vision3d_runtime.py', 'rt_base')
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

    def test_refuses_unknown_runtime(self):
        self.f.write_bytes(self.base + b'\n# edited\n')
        self.assertNotEqual(self.run_tool('apply').returncode, 0)


if __name__ == '__main__':
    unittest.main()
