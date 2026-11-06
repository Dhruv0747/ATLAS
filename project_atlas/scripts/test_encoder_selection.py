"""Stationary/offline tests only: never opens a serial port or publishes ROS."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from atlas_encoder_selection import (
    WHEEL_NAMES, EncoderDeltaEstimator, EncoderLinkMonitor, feedback_state,
    four_wheel_path_scales, validate_selection,
)


class EncoderSelectionTests(unittest.TestCase):
    def test_explicit_single_channel_exclusion(self):
        self.assertEqual(validate_selection(dict(excluded_encoders=[3], navigation_validated=False, packet_timeout_s=1)), ((2,), False, 1.0))
        self.assertEqual(validate_selection(dict(excluded_encoders=[4], navigation_validated=False, packet_timeout_s=1)), ((3,), False, 1.0))

    def test_bad_config_fails_closed(self):
        for conf in (None, {}, dict(excluded_encoders=[3, 4]), dict(excluded_encoders=[True]), dict(excluded_encoders=[5]), dict(excluded_encoders=[3, 3]), dict(excluded_encoders=[4], navigation_validated='false', packet_timeout_s=1), dict(excluded_encoders=[4], navigation_validated=False, packet_timeout_s=2)):
            with self.assertRaises(ValueError): validate_selection(conf)

    def test_three_can_be_qualified_without_four(self):
        excluded, valid, _ = validate_selection(dict(excluded_encoders=[3], navigation_validated=True, packet_timeout_s=1))
        self.assertTrue(valid)
        self.assertEqual(feedback_state(excluded, [], True, False, True, 0)[:2], ('DEGRADED', .5))

    def test_physical_mapping(self):
        self.assertEqual(WHEEL_NAMES, ('back_left', 'back_right', 'front_left', 'front_right'))

    def test_dead_or_noisy_m3_has_no_effect(self):
        for m3 in (0, 100000, -100000, math.nan):
            estimator = EncoderDeltaEstimator()
            estimator.update([0, 0, 0, 0], [0, 1, 3])
            self.assertAlmostEqual(estimator.update([.1, .1, m3, .1], [0, 1, 3]), .1)

    def test_dynamic_consensus_rejects_whichever_channel_is_weak(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0, 0, 0, 0], [0, 1, 2, 3])
        self.assertAlmostEqual(estimator.update([.1, .101, .02, .099], range(4)), .1)
        self.assertEqual(estimator.last_accepted, (0, 1, 3))
        self.assertEqual(estimator.last_rejected, (2,))

        self.assertAlmostEqual(estimator.update([.2, .201, .12, .109], range(4)), .1)
        self.assertEqual(estimator.last_accepted, (0, 1, 2))
        self.assertEqual(estimator.last_rejected, (3,))

    def test_two_versus_two_fails_closed(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0, 0, 0, 0], range(4))
        self.assertEqual(estimator.update([.1, .1, 0, 0], range(4)), 0.0)
        self.assertEqual(estimator.last_accepted, ())
        self.assertEqual(estimator.last_rejected, (0, 1, 2, 3))

    def test_turn_geometry_normalizes_inside_and_outside_wheels(self):
        positions = ('rear_left', 'rear_right', 'front_left', 'front_right')
        scales = four_wheel_path_scales(2.0, 0.367, 0.260, positions)
        self.assertAlmostEqual(scales[0], scales[2])
        self.assertAlmostEqual(scales[1], scales[3])
        self.assertLess(scales[0], scales[1])
        estimator = EncoderDeltaEstimator()
        estimator.update([0.0] * 4, range(4), scales)
        raw = [0.1 * value for value in scales]
        self.assertAlmostEqual(estimator.update(raw, range(4), scales), 0.1)
        self.assertEqual(estimator.last_accepted, (0, 1, 2, 3))

    def test_turn_geometry_still_rejects_one_weak_channel(self):
        positions = ('rear_left', 'rear_right', 'front_left', 'front_right')
        scales = four_wheel_path_scales(-1.5, 0.367, 0.260, positions)
        estimator = EncoderDeltaEstimator()
        estimator.update([0.0] * 4, range(4), scales)
        raw = [0.1 * value for value in scales]
        raw[2] *= 0.1
        self.assertAlmostEqual(estimator.update(raw, range(4), scales), 0.1)
        self.assertEqual(estimator.last_rejected, (2,))

    def test_low_speed_turn_quantization_keeps_three_commissioned_channels(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0.0] * 4, [0, 1, 2])
        # Regression from the 2026-10-02 bounded right-arc stop.  These are
        # already normalized body-centre increments from M1/M2/M3.
        distance = estimator.update(
            [0.002807, 0.005141, 0.001250, 0.0], [0, 1, 2]
        )
        self.assertAlmostEqual(distance, 0.002807)
        self.assertEqual(estimator.last_accepted, (0, 1, 2))

    def test_low_speed_tolerance_does_not_accept_real_split(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0.0] * 4, [0, 1, 2])
        self.assertEqual(
            estimator.update([0.002, 0.0085, -0.0045, 0.0], [0, 1, 2]),
            0.0,
        )
        self.assertEqual(estimator.last_accepted, ())

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

    def test_link_requalifies_after_real_packet_loss(self):
        monitor = EncoderLinkMonitor(1.0, 3.0)
        self.assertEqual(monitor.update(10.0, 10.1), (True, True))
        self.assertEqual(monitor.update(12.9, 13.1), (True, False))
        self.assertEqual(monitor.update(12.9, 14.1), (False, False))
        self.assertEqual(monitor.stale_events, 1)
        self.assertEqual(monitor.update(14.2, 14.2), (True, True))
        self.assertEqual(monitor.recoveries, 1)
        self.assertEqual(monitor.update(17.2, 17.2), (True, False))

    def test_consensus_failure_is_not_transport_loss(self):
        estimator = EncoderDeltaEstimator()
        estimator.update([0, 0, 0, 0], range(4))
        estimator.update([.1, .1, 0, 0], range(4))
        self.assertEqual(estimator.last_accepted, ())
        self.assertEqual(estimator.last_rejected, (0, 1, 2, 3))
        monitor = EncoderLinkMonitor(1.0, 0.0)
        self.assertEqual(monitor.update(5.0, 5.01), (True, False))
        self.assertEqual(monitor.stale_events, 0)

    def test_qualifying(self):
        self.assertEqual(feedback_state((3,), [], True, True, False, 0)[:2], ('QUALIFYING', 0))

    def test_normal_four_unchanged(self):
        self.assertEqual(feedback_state((), [], True, False, False, 0)[:2], ('READY', 1))
        self.assertEqual(feedback_state((), [1], True, False, True, 2)[:2], ('DEGRADED', .5))
        self.assertEqual(feedback_state((), [1], True, False, True, 6)[:2], ('CRITICAL', 0))

    def test_empty_static_exclusion_is_valid_for_dynamic_consensus(self):
        self.assertEqual(
            validate_selection(dict(excluded_encoders=[], navigation_validated=False, packet_timeout_s=1)),
            ((), False, 1.0),
        )

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
                               'encoder_state': state, 'encoder_age': age,
                               'recovery_three_encoder_ready': False,
                               'selected': SimpleNamespace(name='NAV2')})
        self.assertTrue(blocked(False))
        self.assertFalse(blocked(True))
        self.assertTrue(blocked(True, age=2))
        self.assertTrue(blocked(True, state='CRITICAL'))


if __name__ == '__main__':
    unittest.main()
