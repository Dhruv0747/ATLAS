import math
import unittest

from atlas_localization_batch_audit import integrated, jumps, pose_stability


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

    def test_last_window_pose_stability(self):
        result = pose_stability([(0, 0, 0), (10, 2, 0), (11, 2.1, 0),
                                 (21, 2.1, 0), (22, 2.4, 0)])
        self.assertEqual(result["last_window_span_m"], .4)
        self.assertEqual(result["last_window_max_step_m"], .3)
        self.assertEqual(result["last_window_coverage_s"], 12)


if __name__ == "__main__":
    unittest.main()
