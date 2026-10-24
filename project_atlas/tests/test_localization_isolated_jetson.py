import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

path=Path(__file__).resolve().parents[1]/'tools/diagnostics/localization_isolated_jetson.py'
spec=importlib.util.spec_from_file_location('guarded_loc',path)
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)

class GuardTests(unittest.TestCase):
    def test_cpu_strict(self):
        for value in (0,72,75):M.check_cpu(value)
        for value in (75.01,100,float('nan'),float('inf'),None,-1):
            with self.assertRaises(RuntimeError):M.check_cpu(value)
    def test_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'a').write_bytes(b'a')
            M.verify(p,{'a':M.hashlib.sha256(b'a').hexdigest()})
            for values in ({'a':'bad'},{'../a':'bad'}):
                with self.assertRaises(RuntimeError):M.verify(p,values)
    def test_owned_process_only(self):
        p=Mock(pid=123);p.poll.return_value=None
        with patch.object(M.os,'killpg') as kill:
            M.stop_owned(p);kill.assert_called_once_with(123,M.signal.SIGINT)
    def test_no_restart_or_production_domain(self):
        source=path.read_text()
        self.assertIn("ROS_DOMAIN_ID='213'",source)
        self.assertIn("ROS_LOCALHOST_ONLY='1'",source)
        self.assertNotIn("'restart'",source)
        self.assertNotIn('--diagnostic-cpu-report-only',source)

if __name__=='__main__':unittest.main()
