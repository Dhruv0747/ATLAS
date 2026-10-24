import tempfile
import unittest
import importlib.util
from pathlib import Path
import dashboard_telemetry_cpu_once as W


class FixedProfileTests(unittest.TestCase):
    def gate(self):
        path = Path(__file__).parents[1]/'vision3d'/'stationary_gate.py'
        spec = importlib.util.spec_from_file_location('isolated_gate', path)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        gate.UNITS = tuple(dict.fromkeys(gate.UNITS + W.UNITS))
        return gate

    def service_rows(self):
        return '\n\n'.join('Id='+unit+'\nMainPID=94624\nNRestarts=0\nActiveState=active'
                           for unit in W.UNITS)

    def test_actual_parser_accepts_canonical_systemd_ids(self):
        gate = self.gate()
        self.assertTrue(all(unit.endswith('.service') for unit in gate.UNITS))
        rows = gate.parse_services(self.service_rows())
        self.assertEqual(len(rows), 11)
        self.assertIn('rover-status-web.service', rows)

    def test_original_short_name_failure_reproduced(self):
        gate = self.gate()
        gate.UNITS = tuple(u.removesuffix('.service') if u == 'rover-status-web.service' else u
                           for u in gate.UNITS)
        with self.assertRaisesRegex(RuntimeError, 'incomplete/duplicate'):
            gate.parse_services(self.service_rows())

    def test_missing_duplicate_and_unknown_still_rejected(self):
        gate = self.gate()
        raw = self.service_rows()
        blocks = raw.split('\n\n')
        for invalid in ('\n\n'.join(blocks[:-1]), raw+'\n\n'+blocks[0],
                        raw.replace('rover-status-web.service', 'unapproved.service')):
            with self.assertRaises(RuntimeError): gate.parse_services(invalid)

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
