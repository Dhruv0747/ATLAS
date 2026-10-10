"""Pure tests for the 2026-10-10 localization-motion investigation tools.

No ROS graph, bag, network or actuator is used.
"""
import math
import unittest

import numpy as np

import atlas_amcl_motion_replay_extract as extract
import atlas_motion_localization_audit as audit
import atlas_odometry_icp_scale_check as icpcheck


class SegmentTests(unittest.TestCase):
    def test_moving_and_stopped_segments_with_short_blip_merged(self):
        samples = [(t * 0.1, 0.0, 0.0) for t in range(30)]          # 0.0-2.9 s stopped
        samples += [(3.0 + t * 0.1, 0.3, 0.0) for t in range(30)]   # 3.0-5.9 s moving
        samples += [(6.0, 0.0, 0.0)]                                # 0 s stop blip
        samples += [(6.1 + t * 0.1, 0.3, 0.0) for t in range(10)]
        segs = audit.segments(samples)
        self.assertEqual([s['state'] for s in segs], ['stopped', 'moving'])
        self.assertAlmostEqual(segs[1]['end'], 7.0)

    def test_uncertain_rule_matches_dashboard(self):
        self.assertTrue(audit.uncertain(0.26, 5))
        self.assertTrue(audit.uncertain(0.1, 21))
        self.assertFalse(audit.uncertain(0.25, 20))


class ExtractTests(unittest.TestCase):
    def test_rescale_scales_translation_not_heading(self):
        # 1 m forward, turn 90 deg in place, 1 m forward
        series = [(0, 0, 0, 0), (1, 1, 0, 0), (2, 1, 0, math.pi / 2), (3, 1, 1, math.pi / 2)]
        out = extract.rescale(series, 1.6)
        self.assertAlmostEqual(out[1][1], 1.6)
        self.assertAlmostEqual(out[3][1], 1.6)
        self.assertAlmostEqual(out[3][2], 1.6)
        self.assertAlmostEqual(out[3][3], math.pi / 2)

    def test_interpolate_wraps_heading_and_clamps(self):
        series = [(0, 0, 0, math.radians(179)), (1, 1, 0, math.radians(-179))]
        x, _, yaw = extract.interpolate(series, 0.5)
        self.assertAlmostEqual(x, 0.5)
        self.assertAlmostEqual(abs(math.degrees(yaw)), 180, places=5)
        self.assertEqual(extract.interpolate(series, 9)[0], 1)


class IcpTests(unittest.TestCase):
    def test_icp_recovers_known_motion(self):
        rng = np.random.default_rng(3)
        # L-shaped room corner, both walls, 0.02 m spacing
        a = np.r_[np.c_[np.linspace(-2, 2, 200), np.full(200, 2.0)],
                  np.c_[np.full(200, 2.5), np.linspace(-2, 2, 200)],
                  np.c_[np.linspace(-2, 2, 200), np.full(200, -1.5)]]
        dx, dy, th = 0.12, -0.03, math.radians(4)
        c, s = math.cos(th), math.sin(th)
        # points seen after moving by (dx, dy, th): b = R^T (a - t)
        b = (a - [dx, dy]) @ np.array([[c, -s], [s, c]])
        b += rng.normal(0, 0.003, b.shape)
        r = icpcheck.icp(b, a, (0.0, 0.0, 0.0))
        self.assertAlmostEqual(r[0], dx, delta=0.01)
        self.assertAlmostEqual(r[1], dy, delta=0.01)
        self.assertAlmostEqual(math.degrees(r[2]), 4, delta=0.3)


if __name__ == '__main__':
    unittest.main()
