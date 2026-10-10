import math
import unittest

import numpy as np

from atlas_amcl_weak_hypothesis_trace import (
    AMCL, beam_indices, distance_field, likelihood_field, resample_survival, support_mask, wrap)


def wall_world():
    """5 m x 5 m map at 0.05 m with one wall at x = 2.0 m."""
    grid = np.zeros((100, 100), dtype=bool)
    grid[:, 40] = True
    return distance_field(grid, 0.05, AMCL['laser_likelihood_max_dist']), (0.0, 0.0), 0.05


def forward_scan(distance, count=360):
    """Ranges that hit a wall `distance` ahead along the beam at bearing 0 only."""
    ranges = np.full(count, np.inf)
    ranges[180] = distance
    return (-math.pi, 2 * math.pi / count, ranges, 0.15, 12.0)


class WeakHypothesisTraceTests(unittest.TestCase):
    def test_wrap_and_joint_support(self):
        self.assertAlmostEqual(float(wrap(math.radians(190))), math.radians(-170))
        particles = np.array([[0.4, 0, math.radians(19)], [0.4, 0, math.radians(21)], [0.6, 0, 0]])
        self.assertEqual(support_mask(particles, (0, 0, 0)).tolist(), [True, False, False])

    def test_support_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            support_mask(np.array([[np.nan, 0, 0]]), (0, 0, 0))

    def test_amcl_beam_step_matches_integer_division(self):
        idx = beam_indices(360, 60)
        self.assertEqual(idx[1] - idx[0], 6)
        self.assertEqual(len(idx), 60)

    def test_distance_field_is_capped(self):
        field, _, _ = wall_world()
        self.assertAlmostEqual(field[50, 40], 0.0)
        self.assertAlmostEqual(field[50, 0], 2.0)

    def test_empty_map_rejected(self):
        with self.assertRaises(ValueError):
            distance_field(np.zeros((3, 3), dtype=bool), 0.05, 2.0)

    def test_correct_pose_scores_higher(self):
        field, origin, res = wall_world()
        scan = forward_scan(1.0)
        identity = np.zeros(3)
        poses = np.array([[1.0, 2.5, 0.0], [0.7, 2.5, 0.0], [1.0, 2.5, math.radians(30)]])
        w = likelihood_field(poses, scan, identity, field, origin, res)
        self.assertGreater(w[0], w[1])
        self.assertGreater(w[0], w[2])

    def test_max_and_short_ranges_are_skipped(self):
        field, origin, res = wall_world()
        ranges = np.full(360, 12.0)
        ranges[0] = 0.1  # <= range_min becomes range_max and is skipped
        w = likelihood_field(np.array([[1.0, 2.5, 0.0]]), (-math.pi, 2 * math.pi / 360, ranges, 0.15, 12.0),
                             np.zeros(3), field, origin, res)
        self.assertEqual(float(w[0]), 1.0)

    def test_off_map_uses_max_distance(self):
        field, origin, res = wall_world()
        w = likelihood_field(np.array([[1.0, 2.5, math.pi]]), forward_scan(5.0), np.zeros(3), field, origin, res)
        expected = 1.0 + (AMCL['z_hit'] * math.exp(-4.0 / (2 * 0.04)) + AMCL['z_rand'] / 12.0) ** 3
        self.assertAlmostEqual(float(w[0]), expected)

    def test_laser_offset_and_yaw_applied(self):
        field, origin, res = wall_world()
        # Laser 0.1 m behind base and facing backwards, like ATLAS (x=-0.05, yaw=pi).
        laser = np.array([-0.1, 0.0, math.pi])
        robot = np.array([[1.0, 2.5, math.pi]])  # faces -x, so the laser faces +x
        # Base faces -x, so "0.1 m behind" puts the laser at x=1.1: wall 0.9 m away.
        good = likelihood_field(robot, forward_scan(0.9), laser, field, origin, res)
        sign_error = likelihood_field(robot, forward_scan(1.1), laser, field, origin, res)
        no_offset = likelihood_field(robot, forward_scan(1.0), laser, field, origin, res)
        self.assertGreater(float(good[0]), float(sign_error[0]))
        self.assertGreater(float(good[0]), float(no_offset[0]))

    def test_neutral_full_membership_never_extinct(self):
        ends, _ = resample_survival(np.ones((5, 10)), [10] * 5, np.ones(10, bool), trials=50, seed=1)
        self.assertTrue(np.all(ends == 10))

    def test_resampling_is_reproducible(self):
        args = (np.ones((4, 20)), [20, 15, 10, 8], np.arange(20) < 3)
        a, _ = resample_survival(*args, trials=30, seed=7)
        b, _ = resample_survival(*args, trials=30, seed=7)
        self.assertTrue(np.array_equal(a, b))

    def test_strongly_favoured_particle_takes_over(self):
        w = np.ones((10, 50))
        w[:, 0] = 50.0
        _, tracked = resample_survival(w, [50] * 10, np.zeros(50, bool), trials=20, seed=3, track_index=0)
        self.assertTrue(np.all(tracked > 40))

    def test_invalid_weights_rejected(self):
        with self.assertRaises(ValueError):
            resample_survival(np.zeros((1, 3)), [3], np.zeros(3, bool), trials=1, seed=0)
        with self.assertRaises(ValueError):
            resample_survival(np.ones((2, 3)), [3], np.zeros(3, bool), trials=1, seed=0)


if __name__ == '__main__':
    unittest.main()
