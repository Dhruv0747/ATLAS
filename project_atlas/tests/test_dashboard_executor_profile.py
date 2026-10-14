import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'tools/diagnostics/analyze_dashboard_executor_profile.py'
spec = importlib.util.spec_from_file_location('profile_analysis', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProfileTests(unittest.TestCase):
    def test_weighted_paths_and_leaf(self):
        result = module.analyze('_spin (atlas_status_web.py:663);_wait_for_ready_callbacks (rclpy/executors.py:678) 4\n_spin_status (atlas_status_web.py:437);callback (x.py:1) 2')
        self.assertEqual(result['samples'], 6)
        self.assertEqual(result['call_paths'], {'main': 4, 'status': 2})
        self.assertEqual(result['categories_installed_line_mapping']['leaf_wait_generator'], 4)
        self.assertIn('not available', result['linux_tid_attribution'])

    def test_source_identity_required(self):
        sample = '_wait_for_ready_callbacks (rclpy/executors.py:678) 4'
        key = 'wait_return_boundary_not_cpu_attribution'
        for identity in (None, 'wrong'):
            self.assertNotIn(key, module.analyze(sample, identity)['categories_installed_line_mapping'])
        self.assertEqual(module.analyze(sample, module.EXECUTOR_SHA256)['categories_installed_line_mapping'][key], 4)

    def test_inclusive_not_leaf(self):
        result = module.analyze('_wait_for_ready_callbacks (rclpy/executors.py:674);add_to_wait_set (rclpy/qos_event.py:114) 3', module.EXECUTOR_SHA256)
        self.assertEqual(result['categories_installed_line_mapping']['construction'], 3)
        self.assertNotIn('leaf_wait_generator', result['categories_installed_line_mapping'])

    def test_bad_counts(self):
        for text in ('x 0', 'x -1', 'x bad', 'missing'):
            with self.assertRaises(ValueError):
                module.analyze(text)

    def test_empty(self):
        self.assertEqual(module.analyze('\n')['samples'], 0)
