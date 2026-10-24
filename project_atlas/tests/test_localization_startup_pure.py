import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).parents[1] / 'tools/diagnostics/benchmark_localization_startup_pure.py'
spec = importlib.util.spec_from_file_location('startup_bench', PATH)
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class StartupTests(unittest.TestCase):
    def test_stage_order_and_measurements(self):
        rows = []
        wall = iter([1, 1.4]); cpu = iter([2, 2.1])
        result = object()
        self.assertIs(B.measure('stage', lambda: result, rows,
                                lambda: next(wall), lambda: next(cpu)), result)
        self.assertAlmostEqual(rows[0]['wall_s'], .4)
        self.assertAlmostEqual(rows[0]['cpu_s'], .1)
        self.assertEqual(rows[0]['outcome'], 'PASSED')

    def test_failure_not_hidden(self):
        rows = []
        error = RuntimeError('construction failed')
        def fail():
            raise error
        with self.assertRaises(RuntimeError) as caught:
            B.measure('service_construction', fail, rows)
        self.assertIs(caught.exception, error)
        self.assertEqual(rows[0]['outcome'], 'FAILED')

    def test_no_ros_or_live_operations(self):
        source = PATH.read_text()
        for forbidden in ('rclpy.init(', 'subprocess.', 'systemctl', 'urllib', 'write_text('):
            self.assertNotIn(forbidden, source)
        self.assertIn('PC-only benchmark; ARM64 execution not approved', source)


if __name__ == '__main__':
    unittest.main()
