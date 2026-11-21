import math
import unittest

from atlas_localization_display import summarize_amcl_pose


class LocalizationDisplayTest(unittest.TestCase):
    def covariance(self, xy=0.01, yaw_deg=5.0):
        values = [0.0] * 36
        values[0] = xy * xy / 2.0
        values[7] = xy * xy / 2.0
        values[35] = math.radians(yaw_deg) ** 2
        return values

    def test_confident_pose_is_not_marked_uncertain(self):
        result = summarize_amcl_pose(0.0, 0.0, 0.0, self.covariance())
        self.assertFalse(result["uncertain"])
        self.assertFalse(result["large_step"])

    def test_invalid_covariance_fails_closed_for_display(self):
        covariance = self.covariance()
        covariance[0] = float("nan")
        result = summarize_amcl_pose(0.0, 0.0, 0.0, covariance)
        self.assertTrue(result["uncertain"])
        self.assertIsNone(result["xy_std_m"])

    def test_recorded_stationary_correction_is_visible(self):
        result = summarize_amcl_pose(
            1.57, -0.24, math.radians(8.3),
            self.covariance(1.25, 59.6),
            previous=(3.74, -0.65, math.radians(138.5)),
        )
        self.assertTrue(result["uncertain"])
        self.assertTrue(result["large_step"])
        self.assertAlmostEqual(result["last_step_m"], 2.208, places=2)
        self.assertAlmostEqual(result["last_step_deg"], 130.2, places=1)

    def test_yaw_wrap_is_not_a_false_jump(self):
        result = summarize_amcl_pose(
            0.0, 0.0, math.radians(-179.0), self.covariance(),
            previous=(0.0, 0.0, math.radians(179.0)),
        )
        self.assertFalse(result["large_step"])
        self.assertAlmostEqual(result["last_step_deg"], 2.0, places=1)

    def test_all_recorded_post_stop_steps_are_visible(self):
        # Rounded coordinates/headings from the Oct 9 Hall-to-Dhruv bag.
        steps = [
            ((3.17, -1.04, 97.0), (3.57, -0.65, 143.6)),
            ((3.74, -0.65, 138.5), (1.57, -0.24, 8.3)),
            ((1.57, -0.24, 8.3), (0.30, -1.11, 68.6)),
            ((0.30, -1.11, 68.6), (1.58, -0.24, 8.3)),
            ((1.56, -0.25, 8.5), (0.35, -1.11, 61.0)),
        ]
        for before, after in steps:
            with self.subTest(after=after):
                result = summarize_amcl_pose(
                    after[0], after[1], math.radians(after[2]),
                    self.covariance(1.1, 55),
                    previous=(before[0], before[1], math.radians(before[2])),
                )
                self.assertTrue(result["large_step"])
                self.assertTrue(result["uncertain"])


if __name__ == "__main__":
    unittest.main()
