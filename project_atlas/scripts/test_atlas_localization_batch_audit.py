import math
import unittest

from atlas_localization_batch_audit import integrated, jump_context, jumps, pose_stability


class BatchAuditTest(unittest.TestCase):
    def test_integral_uses_common_interpolated_endpoints(self):
        samples = [(0.0, 0.0), (1.0, 2.0), (2.0, 0.0)]
        self.assertAlmostEqual(integrated(samples, 0.5, 1.5), math.degrees(1.5))

    def test_integral_rejects_extrapolation(self):
        self.assertIsNone(integrated([(0, 0), (1, 1)], -0.1, 0.5))

    def test_amcl_jump_threshold_is_strict(self):
        samples = [(0, 0, 0), (1, .5, 0), (2, 1.2, 0)]
        self.assertEqual(jumps(samples), [(2, .7)])

    def test_sparse_amcl_pose_is_not_a_motion_jump(self):
        self.assertEqual(jumps([(0, 0, 0), (5, 2, 0)]), [])

    def test_jump_context_distinguishes_stationary_sensors_from_amcl_step(self):
        amcl = [(0, 0, 0, 0, .04), (1, 1, 0, math.pi / 2, .09)]
        wheel = [(0, 2, 3, 0), (1, 2, 3, 0)]
        gyro = [(0, 0), (1, 0)]
        result = jump_context(amcl, wheel, gyro, [.2, .8], -.5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["amcl_step_m"], 1)
        self.assertEqual(result[0]["amcl_heading_step_deg"], 90)
        self.assertEqual(result[0]["wheel_translation_m"], 0)
        self.assertEqual(result[0]["gyro_turn_deg"], 0)
        self.assertEqual(result[0]["scans_between_poses"], 2)

    def test_jump_context_does_not_invent_missing_wheel_motion(self):
        amcl = [(0, 0, 0, 0, 0), (1, 1, 0, 0, 0)]
        result = jump_context(amcl, [(5, 0, 0, 0)], [], [], None)
        self.assertIsNone(result[0]["wheel_translation_m"])
        self.assertIsNone(result[0]["gyro_turn_deg"])

    def test_last_window_pose_stability(self):
        result = pose_stability([(0, 0, 0), (10, 2, 0), (11, 2.1, 0),
                                 (21, 2.1, 0), (22, 2.4, 0)])
        self.assertEqual(result["last_window_span_m"], .4)
        self.assertEqual(result["last_window_max_step_m"], .3)
        self.assertEqual(result["last_window_coverage_s"], 12)


if __name__ == "__main__":
    unittest.main()
