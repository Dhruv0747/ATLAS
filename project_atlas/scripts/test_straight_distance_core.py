#!/usr/bin/env python3

import math
import unittest

from atlas_straight_distance_core import (
    IncrementalPlanarDistance,
    corridor_clearance_progress,
    conservative_progress,
    forward_clearance_progress,
    robust_corridor_range,
)


class IncrementalPlanarDistanceTest(unittest.TestCase):
    def test_accumulates_distance_independent_of_heading(self):
        tracker = IncrementalPlanarDistance()
        self.assertTrue(tracker.update(0.0, 0.0))
        self.assertTrue(tracker.update(0.03, 0.04))
        self.assertTrue(tracker.update(0.00, 0.08))
        self.assertAlmostEqual(tracker.distance_m, 0.10, places=6)

    def test_rejects_nonfinite_and_implausible_jump(self):
        tracker = IncrementalPlanarDistance(max_step_m=0.10)
        self.assertTrue(tracker.update(1.0, 1.0))
        self.assertFalse(tracker.update(math.nan, 1.0))
        self.assertFalse(tracker.update(2.0, 1.0))
        self.assertEqual(tracker.rejected_updates, 2)
        self.assertEqual(tracker.distance_m, 0.0)
        self.assertTrue(tracker.update(1.06, 1.0))
        self.assertAlmostEqual(tracker.distance_m, 0.06, places=6)

    def test_robust_corridor_range_ignores_single_near_ray(self):
        self.assertAlmostEqual(
            robust_corridor_range([0.42, 1.98, 2.00, 2.02, 2.04]),
            2.00,
        )

    def test_clearance_progress_never_goes_negative(self):
        self.assertAlmostEqual(forward_clearance_progress(2.0, 1.73), 0.27)
        self.assertEqual(forward_clearance_progress(2.0, 2.1), 0.0)
        self.assertEqual(forward_clearance_progress(math.inf, 2.1), 0.0)

    def test_same_corridor_progress_supports_rear_sector(self):
        self.assertAlmostEqual(corridor_clearance_progress(1.50, 1.31), 0.19)

    def test_conservative_progress_uses_farther_measurement(self):
        self.assertAlmostEqual(conservative_progress(0.173, 0.284), 0.284)
        self.assertAlmostEqual(conservative_progress(0.205, 0.190), 0.205)


if __name__ == "__main__":
    unittest.main()
