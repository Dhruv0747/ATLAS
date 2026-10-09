import math
import unittest

from atlas_amcl_turn_divergence import integrated_gyro, summarize, unwrap


class TurnDivergenceTest(unittest.TestCase):
    def test_unwrap_crosses_pi_without_full_revolution(self):
        series = unwrap([(0, math.radians(179)), (1, math.radians(-179))])
        self.assertAlmostEqual(math.degrees(series[-1][1]), 2.0)

    def test_gyro_gap_does_not_integrate_missing_interval(self):
        series = integrated_gyro([(0, 1), (1, 1), (2, 1), (3, 1)])
        self.assertEqual(series[-1][1], 0)
        series = integrated_gyro([(0, 1), (.1, 1), (1, 1)])
        self.assertAlmostEqual(series[-1][1], .1)

    def test_stationary_pose_jump_is_reported_not_called_wheel_motion(self):
        wheel = [(0, 0, 0, 0), (5, .1, 0, 0), (10, .1, 0, 0)]
        fused = list(wheel)
        gyro = [(t / 10, .01) for t in range(101)]
        amcl = [(0, 0, 0, .1), (5, 0, 0, .6), (9, 0, 0, 1.1),
                (9.5, 2, 0, 1.1), (10, 2, 0, 1.0)]
        health = [(2, {'state': 'READY', 'faults': [], 'selected_encoders': [1, 2, 3, 4]}),
                  (7, {'state': 'CRITICAL', 'faults': ['M3'], 'selected_encoders': [1, 2, 4]})]
        result = summarize(wheel, fused, gyro, amcl,
                           [(4, .1, 0), (5, 0, 0)], health,
                           [(2, 'front', 80), (3, 'front', 90), (2, 'rear', 100)])
        self.assertEqual(result['last_nonzero_command_offset_s'], 4)
        self.assertEqual(result['first_amcl_xy_std_above_1_0_offset_s'], 9)
        self.assertEqual(result['large_amcl_steps'][0]['step_m'], 2)
        self.assertEqual(result['window_count'], 2)
        self.assertEqual(result['worst_turn_windows'][0]['encoder_health_samples'], 1)
        self.assertEqual(sum(row['encoder_fault_samples'] for row in result['worst_turn_windows']), 1)
        self.assertIn('[1, 2, 3, 4]', result['worst_turn_windows'][0]['encoder_selection_counts'])
        self.assertEqual(result['worst_turn_windows'][0]['commanded_steering_ranges_deg'],
                         {'front': [80, 90], 'rear': [100, 100]})


if __name__ == '__main__':
    unittest.main()
