import math
import unittest

from atlas_amcl_axis_sweep import offset_pose, peak


class AxisSweepTests(unittest.TestCase):
    def test_forward_offset_follows_heading(self):
        p = offset_pose((1.0, 2.0, math.pi / 2), 0.5, 0.0)
        self.assertAlmostEqual(p[0], 1.0)
        self.assertAlmostEqual(p[1], 2.5)
        self.assertAlmostEqual(p[2], math.pi / 2)

    def test_left_offset_is_perpendicular(self):
        p = offset_pose((0.0, 0.0, 0.0), 0.0, 0.3)
        self.assertAlmostEqual(p[0], 0.0)
        self.assertAlmostEqual(p[1], 0.3)

    def test_backward_offset_reverses(self):
        p = offset_pose((0.0, 0.0, math.pi), -0.5, 0.0)
        self.assertAlmostEqual(p[0], 0.5)
        self.assertAlmostEqual(p[1], 0.0, places=9)

    def test_peak_picks_largest(self):
        rows = [{'offset_m': -0.1, 'v': 1.0}, {'offset_m': 0.0, 'v': 3.0}, {'offset_m': 0.1, 'v': 2.0}]
        self.assertEqual(peak(rows, 'v'), {'offset_m': 0.0, 'v': 3.0})


if __name__ == '__main__':
    unittest.main()
