import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'tools/diagnostics'
spec = importlib.util.spec_from_file_location('loc_profile', ROOT / 'localization_cpu_once.py')
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)


class LocalizationProfileTests(unittest.TestCase):
    def helper(self):
        return L.configure(L.load_helper(ROOT / 'native_dashboard_cpu_once.py'))

    def test_exact_target_and_current_hashes(self):
        m = self.helper()
        self.assertEqual(m.TARGET_UNIT, 'atlas-localization-monitor.service')
        self.assertEqual(m.HASHES[m.TARGET_SCRIPT], L.MONITOR_SHA)
        self.assertEqual(m.HASHES['scripts/atlas_localization_verify_core.py'], L.CORE_SHA)
        self.assertEqual(m.STAGE, L.STAGE)

    def test_bounded_threads_not_gil_only(self):
        command = self.helper().python_command(1948, Path('/tmp/test.json'))
        for flag in ['--gil', '--native', '--idle', '--locals', '--subprocesses']:
            self.assertNotIn(flag, command)
        for flag in ['--threads', '--nonblocking']:
            self.assertIn(flag, command)
        self.assertEqual(command[command.index('--rate')+1], '20')
        self.assertEqual(command[command.index('--duration')+1], '10')

    def test_strict_entry(self):
        for args in [['--pid', '1'], ['--python-gil'], ['--diagnostic-cpu-report-only'] * 2]:
            with patch.object(L.sys, 'argv', ['loc', *args]), self.assertRaises(SystemExit):
                L.main()
        m = self.helper()
        with patch.object(L.sys, 'argv', ['loc']), patch.object(L, 'load_helper', return_value=m), patch.object(m, 'main', return_value=0):
            self.assertEqual(L.main(), 0)
            self.assertEqual(m.parse_options(L.sys.argv[1:]), (True, False))

    def test_owner_cpu_exception_is_explicit_and_local(self):
        m = self.helper()
        with patch.object(L.sys, 'argv', ['loc', '--diagnostic-cpu-report-only']), \
                patch.object(L, 'load_helper', return_value=m), patch.object(m, 'main', return_value=0):
            self.assertEqual(L.main(), 0)
            self.assertEqual(m.parse_options(L.sys.argv[1:]), (True, True))
        self.assertEqual(m.checked_cpu(76.5), 76.5)
        self.assertIsNone(m.checked_cpu(76.5, True))
        for invalid in (float('nan'), float('inf'), -1, 101, None):
            with self.assertRaises(RuntimeError):
                m.checked_cpu(invalid, True)

    def test_exception_does_not_remove_other_checks(self):
        m = self.helper()
        samples = [c for c in m.main.__code__.co_consts
                   if hasattr(c, 'co_name') and c.co_name == 'sample']
        self.assertEqual(len(samples), 1)
        for name in ('require_cpu', 'safety_snapshot', 'check', 'extra_safety',
                     'require_off', 'require_target_threads'):
            self.assertIn(name, samples[0].co_names)
        self.assertIn('Sampling deadline missed', samples[0].co_consts)
        self.assertIn('Safety check deadline missed', samples[0].co_consts)

    def test_tampered_helper_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.py'
            path.write_text('raise AssertionError()')
            with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
                L.load_helper(path)

    def test_metadata_and_extra_protection(self):
        m = self.helper()
        self.assertIn('PYTHON_ALL_THREADS', m.main.__code__.co_consts)
        self.assertIn('python-threads.json', m.main.__code__.co_consts)
        self.assertIn(('atlas-voice-companion.service', 'atlas-safety-status.service'), m.main.__code__.co_consts)


if __name__ == '__main__':
    unittest.main()
