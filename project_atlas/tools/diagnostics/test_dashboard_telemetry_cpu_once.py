import tempfile
import unittest
from pathlib import Path
import dashboard_telemetry_cpu_once as W


class FixedProfileTests(unittest.TestCase):
    def test_strict_arguments(self):
        for target in W.TARGETS:
            self.assertEqual(W.parse([target, '--diagnostic-cpu-report-only']), target)
        for args in ([], ['dashboard'], ['other', '--diagnostic-cpu-report-only'],
                     ['telemetry', '--disable-safety']):
            with self.assertRaises(ValueError): W.parse(args)

    def test_targets_guards_and_bounded_command(self):
        for target, expected in W.TARGETS.items():
            m = W.load_helper(Path(__file__).with_name('native_dashboard_cpu_once.py'), target)
            self.assertEqual((m.TARGET_UNIT, m.TARGET_SCRIPT), expected)
            self.assertEqual(len(m.EXTRA_UNITS), 11)
            self.assertIn('web/v2/material.css', m.HASHES)
            self.assertIn('tools/vision3d/stationary_gate.py', m.HASHES)
            self.assertEqual(m.parse_options(['--python-gil', '--diagnostic-cpu-report-only']), (True, True))
            self.assertIsNone(m.checked_cpu(90, True))
            with self.assertRaises(RuntimeError): m.checked_cpu(float('nan'), True)
            cmd = m.python_command(123, Path('/tmp/output.json'))
            self.assertIn('--nonblocking', cmd)
            self.assertIn('--gil', cmd)
            self.assertEqual(cmd[cmd.index('--duration')+1], '10')
            self.assertEqual(cmd[cmd.index('--rate')+1], '20')

    def test_corrupt_helper_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'helper.py'
            path.write_text('raise AssertionError("must not execute")')
            with self.assertRaises(RuntimeError): W.load_helper(path, 'dashboard')


if __name__ == '__main__': unittest.main()
