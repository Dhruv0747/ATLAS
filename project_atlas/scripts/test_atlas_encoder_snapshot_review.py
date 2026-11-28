import math
import unittest

import numpy as np

from atlas_encoder_snapshot_review import delayed_command_yaw


class DelayedCommandYawTest(unittest.TestCase):
    def test_delay_selects_prior_command_without_extrapolating(self):
        updates = [
            {'stamp_ns': 1_000_000_000, 'accepted_delta_m': 0.1},
            {'stamp_ns': 2_000_000_000, 'accepted_delta_m': 0.1},
        ]
        times = np.array([0.0, 1.0, 2.0])
        curvature = np.array([0.0, 1.0, -1.0])
        same, used = delayed_command_yaw(updates, times, curvature, 1, 3, 0)
        delayed, delayed_used = delayed_command_yaw(
            updates, times, curvature, 1, 3, .5)
        self.assertEqual(used, 2)
        self.assertEqual(delayed_used, 2)
        self.assertAlmostEqual(same, 0.0)
        self.assertAlmostEqual(delayed, math.degrees(.1))


if __name__ == '__main__':
    unittest.main()
