import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

DIR = Path(__file__).parents[1] / 'tools/diagnostics'
def load(name):
    spec = importlib.util.spec_from_file_location(name, DIR/(name+'.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod
S = load('localization_startup_jetson')
P = load('package_localization_startup')


class PackageTests(unittest.TestCase):
    def test_strict_cpu(self):
        self.assertEqual(S.check_cpu(75), 75)
        for x in (75.001, float('nan'), -1, None, 101):
            with self.assertRaises(RuntimeError): S.check_cpu(x)

    def test_path_escape_and_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError): S.verify(Path(d), {'../bad':'x'})
            p = Path(d)/'file'; p.write_text('a')
            with self.assertRaises(RuntimeError): S.verify(Path(d), {'file':'x'})

    def test_finished_process_never_signalled(self):
        proc = Mock(); proc.poll.return_value = 0
        with patch.object(S.os, 'killpg', create=True) as kill:
            S.stop_owned(proc); kill.assert_not_called()

    def test_worker_is_pinned_and_compileable(self):
        source = (DIR/'benchmark_localization_ros_startup.py').read_text()
        worker = P.worker_source(source)
        compile(worker, '<worker>', 'exec')
        self.assertIn("event='BEGIN'", worker)
        self.assertIn('ATLAS_STARTUP_SUPERVISED', worker)
        self.assertIn('Client.call_async = forbidden', worker)
        self.assertIn('value.cancel()', worker)
        self.assertNotIn('ex.add_node(app)', worker)
        with self.assertRaises(ValueError): P.worker_source('unknown')

    def test_supervisor_scope(self):
        source = (DIR/'localization_startup_jetson.py').read_text()
        for text in ('No CPU override', "ROS_DOMAIN_ID='214'", 'start_new_session=True',
                     'launched>20', "range(10)", "sample('cleanup_postflight')",
                     "'mission_sample_time'", "'atlas-mission-control.service'", "P.extra_safety(ros)"):
            self.assertIn(text, source)
        for text in ("'restart'", "'reboot'", 'chmod', '--diagnostic-cpu-report-only'):
            self.assertNotIn(text, source)


if __name__ == '__main__': unittest.main()
