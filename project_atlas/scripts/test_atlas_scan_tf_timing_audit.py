"""Offline numerical checks; no ROS node is created."""
import math
import unittest

from atlas_scan_tf_timing_audit import interpolate, stats


class TimingAuditTest(unittest.TestCase):
    def test_wrap_interpolation(self):
        value = interpolate([(0, math.radians(179)), (1, math.radians(-179))], [0.5])
        self.assertAlmostEqual(abs(value[0]), math.pi)

    def test_no_extrapolation(self):
        self.assertIsNone(interpolate([(1, 0), (2, 1)], [0]))
        self.assertIsNone(interpolate([(1, 0), (2, 1)], [3]))

    def test_known_time_shift(self):
        original = [(0, 0), (1, 0.5), (2, 1)]
        shifted = [(t+0.2, y) for t,y in original]
        self.assertAlmostEqual(interpolate(original, [1])[0] - interpolate(shifted, [1])[0], 0.1)

    def test_empty_statistics(self):
        self.assertEqual(stats([]), {'n': 0})


if __name__ == '__main__':
    unittest.main()
