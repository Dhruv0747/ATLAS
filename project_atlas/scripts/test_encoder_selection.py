"""Stationary/offline tests only: never opens a serial port or publishes ROS."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from atlas_encoder_selection import (
    WHEEL_NAMES, EncoderDeltaEstimator, feedback_state, validate_selection,
)


class EncoderSelectionTests(unittest.TestCase):
    def test_explicit_m4_exclusion(self):
        self.assertEqual(validate_selection(dict(excluded_encoders=[4], navigation_validated=False, packet_timeout_s=1)), ((3,), False, 1.0))

    def test_bad_config_fails_closed(self):
        for conf in (None, {}, dict(excluded_encoders=[3, 4]), dict(excluded_encoders=[True]), dict(excluded_encoders=[4], navigation_validated='false', packet_timeout_s=1), dict(excluded_encoders=[4], navigation_validated=False, packet_timeout_s=2)):
            with self.assertRaises(ValueError): validate_selection(conf)

    def test_three_can_be_qualified_without_four(self):
        excluded, valid, _ = validate_selection(dict(excluded_encoders=[4], navigation_validated=True, packet_timeout_s=1))
        self.assertTrue(valid)
        self.assertEqual(feedback_state(excluded, [], True, False, True, 0)[:2], ('DEGRADED', .5))

    def test_physical_mapping(self):
        self.assertEqual(WHEEL_NAMES, ('back_left', 'back_right', 'front_left', 'front_right'))

    def test_dead_or_noisy_m4_has_no_effect(self):
        for m4 in (0, 100000, -100000, math.nan):
            estimator = EncoderDeltaEstimator()
            estimator.update([0, 0, 0, 0], [0, 1, 2])
            self.assertAlmostEqual(estimator.update([.1, .1, .1, m4], [0, 1, 2]), .1)

    def test_reverse(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0]*4, [0, 1, 2])
        self.assertAlmostEqual(estimator.update([-.2, -.2, -.2, 0], [0, 1, 2]), -.2)

    def test_selection_change_no_cumulative_jump(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0, 10, 20, 30], [0, 1, 2, 3])
        self.assertAlmostEqual(estimator.update([1, 11, 21, 0], [0, 1, 2]), 1)

    def test_stale_reconnect_no_catchup_jump(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0]*4, [0, 1, 2])
        self.assertEqual(estimator.update([0]*4, []), 0)
        self.assertEqual(estimator.update([100]*4, [0, 1, 2]), 0)
        self.assertEqual(estimator.update([101]*4, [0, 1, 2]), 1)

    def test_second_fault_no_two_encoder_fallback(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0]*4, [0, 1, 2])
        self.assertEqual(estimator.update([1, 1, 0, 0], [0, 1]), 0)
        self.assertEqual(feedback_state((3,), [2], True, False, True, .01)[:2], ('CRITICAL', 0))

    def test_shared_stale_stops_even_at_rest(self):
        self.assertEqual(feedback_state((3,), [], False, False, False, 0)[:2], ('CRITICAL', 0))

    def test_qualifying(self):
        self.assertEqual(feedback_state((3,), [], True, True, False, 0)[:2], ('QUALIFYING', 0))

    def test_normal_four_unchanged(self):
        self.assertEqual(feedback_state((), [], True, False, False, 0)[:2], ('READY', 1))
        self.assertEqual(feedback_state((), [1], True, False, True, 2)[:2], ('DEGRADED', .5))
        self.assertEqual(feedback_state((), [1], True, False, True, 6)[:2], ('CRITICAL', 0))

    def test_packet_getter_returns_atomic_pair(self):
        tree = ast.parse(Path(__file__).with_name('Rosmaster_Lib.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Rosmaster')
        getter = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'get_motor_encoder_sample')
        scope = {}
        exec(compile(ast.Module(body=[getter], type_ignores=[]), '<getter>', 'exec'), scope)
        pair = ((1, 2, 3, 4), 12.3)
        self.assertIs(scope['get_motor_encoder_sample'](SimpleNamespace(_encoder_sample=pair)), pair)

    def test_real_mux_requires_validation_but_permits_qualified_three(self):
        tree = ast.parse(Path(__file__).with_name('atlas_cmd_vel_mux.py').read_text(encoding='utf-8'))
        guard = next(n.test for n in ast.walk(tree) if isinstance(n, ast.If)
                     and 'autonomy_ready' in ast.unparse(n.test)
                     and 'encoder_age' in ast.unparse(n.test))
        code = compile(ast.Expression(guard), '<mux guard>', 'eval')
        def blocked(ready, state='DEGRADED', age=.1):
            return eval(code, {'self': SimpleNamespace(encoder_health={'autonomy_ready': ready}),
                               'encoder_state': state, 'encoder_age': age})
        self.assertTrue(blocked(False))
        self.assertFalse(blocked(True))
        self.assertTrue(blocked(True, age=2))
        self.assertTrue(blocked(True, state='CRITICAL'))


if __name__ == '__main__':
    unittest.main()
