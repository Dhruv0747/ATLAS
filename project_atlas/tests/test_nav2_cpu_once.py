import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'tools/diagnostics/nav2_cpu_once.py'
spec = importlib.util.spec_from_file_location('nav2_profile', SOURCE)
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)


class Nav2ProfilerTests(unittest.TestCase):
    def test_exact_helper_and_native_bounds(self):
        # Linux-only pwd import in reviewed helper: stub only for offline loading.
        import types
        with patch.dict('sys.modules', {'pwd': types.ModuleType('pwd')}):
            m = N.load_helper(SOURCE.with_name('native_dashboard_cpu_once.py'))
        command = m.command(8000, Path('/tmp/test'), [8100, 8200])
        self.assertIn('cpu-clock:u', command)
        self.assertIn('--no-inherit', command)
        self.assertEqual(command[-1], '10')
        self.assertEqual(command[command.index('-F') + 1], '19')
        self.assertEqual(m.TARGET_UNIT, 'atlas-localization.service')
        self.assertEqual(m.checked_cpu(76), 76)

    def test_wrong_helper_hash_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'helper'; p.write_text('pass')
            with self.assertRaises(RuntimeError): N.load_helper(p)

    def test_no_python_or_unknown_option(self):
        for args in (['--ignore-all'], ['--python-gil'],
                     ['--diagnostic-cpu-report-only', '--diagnostic-cpu-report-only']):
            with patch('sys.argv', ['nav2', *args]):
                with self.assertRaises(SystemExit): N.main()

    def test_cpu_report_exception_is_explicit_and_forwarded(self):
        from unittest.mock import Mock
        for args in ([], ['--diagnostic-cpu-report-only']):
            helper=Mock(); helper.main.return_value=0
            with patch('sys.argv', ['nav2', *args]), patch.object(N,'load_helper',return_value=helper):
                self.assertEqual(N.main(),0)
                helper.main.assert_called_once_with()
                self.assertEqual(__import__('sys').argv[1:],args)

    def test_exact_launch_rejects_other_ros_command(self):
        with patch.object(Path, 'read_bytes', return_value=b'python3\0ros2\0topic\0list\0'):
            with self.assertRaises(RuntimeError): N.verify_launch(2)
        with patch.object(Path, 'read_bytes', return_value=b'\0'.join(N.LAUNCH)+b'\0'):
            N.verify_launch(2)

    def test_membership_must_include_launcher(self):
        with patch.object(Path, 'read_text', return_value='3\n4\n'):
            with self.assertRaises(RuntimeError): N.group_snapshot(2, lambda p: {})

    def test_allowlist_does_not_include_motor_or_camera(self):
        self.assertEqual(len(N.BINARIES), 8)
        self.assertTrue(all('/lib/nav2_' in p for p in N.BINARIES))


if __name__ == '__main__': unittest.main()
