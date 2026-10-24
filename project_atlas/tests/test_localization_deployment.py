import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).parents[1] / 'tools/diagnostics/deploy_localization_executor_once.py'
spec = importlib.util.spec_from_file_location('deployment', PATH)
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)


class DeploymentTests(unittest.TestCase):
    def test_explicit_exception_only(self):
        self.assertFalse(D.cpu_report_only([]))
        self.assertTrue(D.cpu_report_only(['--installation-cpu-report-only']))
        with self.assertRaises(ValueError):
            D.cpu_report_only(['--ignore-all'])

    def test_cpu_measurement_remains_validated(self):
        for cpu in (float('nan'), -1, 101):
            with self.assertRaises(RuntimeError):
                D.validate_cpu_sample(cpu, True, lambda _: None)
        calls = []
        D.validate_cpu_sample(90, True, calls.append)
        self.assertEqual(calls, [])
        D.validate_cpu_sample(74, False, calls.append)
        self.assertEqual(calls, [74])

    def test_scope_and_protection(self):
        self.assertEqual(D.UNIT, 'atlas-localization-monitor.service')
        for name in ('scripts/atlas_safety_status.py', 'scripts/atlas_voice_companion.py',
                     'scripts/atlas_status_web.py', 'web/v2/material.css',
                     'tools/vision3d/stationary_gate.py', 'scripts/atlas_dashboard_executor_impl.py'):
            self.assertIn(name, D.CHECK)
        text = PATH.read_text()
        self.assertIn('P.extra_safety', text)
        self.assertIn('G.check(', text)
        self.assertIn("if sha(target) != NEW or sha(backup) != BASE:", text)
        self.assertIn("['systemctl', '--user', 'restart', UNIT]", text)


if __name__ == '__main__':
    unittest.main()
