"""Offline contract tests of actual mission methods; no ROS or actuators.

The saved amcl_refresh_contract_20261009_postrefresh result contains only
two pose messages. These tests bound that result without inventing extra
poses or treating processing events as independent position estimates.
"""
import ast
import math
from pathlib import Path
from types import SimpleNamespace as NS
import unittest


class SparsePoseContractTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name('atlas_mission_control.py')
        names = {'angle_delta', 'localization_stability',
                 'require_confident_localization'}
        methods = [n for n in ast.walk(ast.parse(path.read_text()))
                   if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in methods}, names)
        for method in methods:
            method.decorator_list = []
        scope = {'math': math, 'time': NS(monotonic=lambda: 100.)}
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), 'exec'), scope)
        self.node = NS(localization_samples=[], localization_quality=(.01, 1.),
                       localization_stability_window_s=8.,
                       localization_max_xy_std_m=.25,
                       localization_max_yaw_std_deg=20.,
                       localization_max_stationary_shift_m=.10,
                       localization_max_stationary_yaw_deg=5.,
                       angle_delta=scope['angle_delta'])
        self.node.localization_stability = lambda: scope['localization_stability'](self.node)
        self.check = lambda: scope['require_confident_localization'](self.node)

    def samples(self, times, x=0., yaw=0.):
        self.node.localization_samples = [(t, x, 0., yaw) for t in times]

    def test_saved_two_pose_count_cannot_pass_even_best_case_timing(self):
        self.samples([92., 100.])
        with self.assertRaisesRegex(RuntimeError, 'stability window'):
            self.check()

    def test_one_additional_preflight_refresh_still_insufficient(self):
        self.samples([92., 96., 100.])
        with self.assertRaisesRegex(RuntimeError, 'stability window'):
            self.check()

    def test_four_samples_require_time_coverage(self):
        self.samples([99., 99.2, 99.4, 100.])
        with self.assertRaisesRegex(RuntimeError, 'stability window'):
            self.check()

    def test_baseline_covered_stable_samples_pass(self):
        self.samples([93., 95., 97., 100.])
        self.check()

    def test_covered_position_jump_remains_blocked(self):
        self.samples([93., 95., 97., 100.])
        self.node.localization_samples[-1] = (100., 2.206, 0., 0.)
        with self.assertRaisesRegex(RuntimeError, 'still moving'):
            self.check()

    def test_heading_change_remains_blocked(self):
        self.samples([93., 95., 97., 100.])
        self.node.localization_samples[-1] = (100., 0., 0., math.radians(10))
        with self.assertRaisesRegex(RuntimeError, 'still moving'):
            self.check()

    def test_uncertainty_remains_blocked(self):
        self.samples([93., 95., 97., 100.])
        self.node.localization_quality = (1., 1.)
        with self.assertRaisesRegex(RuntimeError, 'uncertain'):
            self.check()


if __name__ == '__main__':
    unittest.main()
