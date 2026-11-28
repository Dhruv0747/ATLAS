"""Offline Python import/staging semantics. No ATLAS imports, ROS or devices."""
import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RestartlessStagingTests(unittest.TestCase):
    def test_running_import_does_not_change_after_disk_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture_vision_backend.py';p.write_text('ROUTES=("preview",)\n')
            sys.path.insert(0,d)
            try:
                original=importlib.import_module('fixture_vision_backend')
                p.write_text('ROUTES=("preview","features")\n')
                importlib.invalidate_caches()
                self.assertIs(importlib.import_module('fixture_vision_backend'),original)
                self.assertEqual(original.ROUTES,('preview',))
                code='import sys;sys.path.insert(0,sys.argv[1]);import fixture_vision_backend as b;print(b.ROUTES)'
                out=subprocess.check_output([sys.executable,'-I','-B','-c',code,d],text=True,timeout=3)
                self.assertIn('features',out)
            finally:sys.path.remove(d);sys.modules.pop('fixture_vision_backend',None)

    def test_staging_and_discard_leave_live_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);live=root/'live.py';stage=root/'candidate.py'
            live.write_bytes(b'original exact bytes\n');before=live.read_bytes()
            stage.write_bytes(b'candidate disabled\n')
            self.assertEqual(live.read_bytes(),before)
            stage.unlink();self.assertEqual(live.read_bytes(),before)

if __name__=='__main__':unittest.main()
