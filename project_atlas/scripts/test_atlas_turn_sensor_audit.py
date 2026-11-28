"""Run with ROS Humble, numpy and scipy available; no ROS node is started."""
import unittest

import numpy as np

from atlas_turn_sensor_audit import event_time, icp


class ScanFitTest(unittest.TestCase):
    def test_explicit_scan_offset_does_not_select_tf_correction(self):
        corrections = [(1, 0, 0), (2, 10, 0)]
        scans = [(100, None)]
        self.assertEqual(event_time(corrections, scans, 5), 105)
        self.assertEqual(event_time(corrections, scans), 2)

    def test_known_transform(self):
        points = np.random.default_rng(42).uniform(-2, 2, (300, 2))
        angle = 0.08
        rotation = np.array([[np.cos(angle), -np.sin(angle)],
                             [np.sin(angle), np.cos(angle)]])
        moved = (points - np.array([0.02, -0.03])) @ rotation
        fit = icp(points, moved, angle)
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit['yaw_deg'], np.degrees(angle), places=5)
        self.assertLess(fit['rmse_m'], 1e-8)

    def test_insufficient_points(self):
        self.assertIsNone(icp(np.zeros((5, 2)), np.zeros((5, 2)), 0))


if __name__ == '__main__':
    unittest.main()
