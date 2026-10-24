import importlib.util
from pathlib import Path
import unittest
import ast

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

    def test_stale_failure_preserved_with_exact_age(self):
        rows = []
        ros = {'mission_status': {'age': 2.731, 'value': 'READY'}}
        error = RuntimeError('stale required mission_status')
        calls = []
        def check(actual):
            calls.append(actual)
            raise error
        with self.assertRaises(RuntimeError) as caught:
            D.audit_sensor_check(ros, check, rows.append, 'settling', 10, lambda: 11)
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [ros])
        self.assertEqual([r['outcome'] for r in rows], ['PENDING', 'FAILED'])
        self.assertEqual(rows[-1]['receipt_ages']['mission_status'], 2.731)
        self.assertEqual(rows[-1]['snapshot_started'], 10)

    def test_success_returns_original_result(self):
        rows = []
        answer = object()
        self.assertIs(D.audit_sensor_check({}, lambda _: answer, rows.append,
                                         'baseline', 0, lambda: 1), answer)
        self.assertEqual(rows[-1]['outcome'], 'PASSED')

    def test_missing_nonfinite_and_unrelated_payload_not_logged(self):
        rows = []
        ros = {'mission_status': {'age': float('nan'), 'value': 'private text'},
               'lidar': {'age': 0.1, 'value': [1] * 10000}}
        D.audit_sensor_check(ros, lambda _: None, rows.append, 'post', 0, lambda: 1)
        self.assertIsNone(rows[0]['receipt_ages']['mission_status'])
        self.assertIsNone(rows[0]['receipt_ages']['enc_m1'])
        self.assertNotIn('private text', str(rows))
        self.assertLess(len(str(rows)), 1500)

    def test_no_production_freshness_relaxation(self):
        text = PATH.read_text()
        self.assertIn("audit_sensor_check(snap['ros'], P.extra_safety", text)
        self.assertIn("mission=identity('atlas-mission-control.service')", text)
        self.assertNotIn('stale required mission_status', text)

    def test_real_probe_boundary_unchanged(self):
        probe = PATH.parents[1] / 'vision3d/stationary_ros_probe.py'
        tree = ast.parse(probe.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'extra_safety')
        namespace = {'verify_astra_usb_access': lambda: None}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(probe), 'exec'), namespace)
        ros = {k: {'age': 0, 'value': 0} for k in
               ('lidar', 'imu_full', 'enc_m1', 'enc_m2', 'enc_m3', 'enc_m4',
                'camera_info', 'drive_pid', 'mission_status', 'motor_speed')}
        ros['drive_pid']['value'] = {'wheels': [{'output': 0, 'target_mps': 0}] * 4}
        ros['camera_info']['value'] = {'publisher_count': 1}
        ros['mission_status'] = {'age': 2.0, 'value': 'READY'}
        D.audit_sensor_check(ros, namespace['extra_safety'], lambda _: None, 'test', 0)
        for bad in (2.001, None, -1, float('nan')):
            ros['mission_status']['age'] = bad
            with self.assertRaisesRegex(RuntimeError, 'stale required mission_status'):
                D.audit_sensor_check(ros, namespace['extra_safety'], lambda _: None, 'test', 0)


if __name__ == '__main__':
    unittest.main()
