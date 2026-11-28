"""Geometry used by the EKF A/B comparison (no ROS, no bags)."""
import math, sys, unittest
import numpy as np
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from ekf_ab_compare import compose, rel, sideslip


class Geometry(unittest.TestCase):
    def test_straight_forward_and_reverse_have_zero_sideslip(self):
        self.assertAlmostEqual(sideslip((0.4, 0.0, 0.0)), 0.0)
        self.assertAlmostEqual(sideslip((-0.4, 0.0, 0.0)), 0.0)

    def test_constant_mount_offset_has_same_sign_forward_and_reverse(self):
        e = math.radians(5.5)
        fwd = (0.4 * math.cos(e), 0.4 * math.sin(e), 0.0)
        rev = (-0.4 * math.cos(e), -0.4 * math.sin(e), 0.0)
        self.assertAlmostEqual(sideslip(fwd), 5.5, places=6)
        self.assertAlmostEqual(sideslip(rev), 5.5, places=6)

    def test_pure_arc_has_zero_sideslip(self):
        R, th = 1.0, math.radians(20)            # chord of a circular arc, no lateral slip
        arc = (R * math.sin(th), R * (1 - math.cos(th)), th)
        self.assertAlmostEqual(sideslip(arc), 0.0, places=6)

    def test_rel_is_expressed_in_start_body_frame(self):
        arr = np.array([[0.0, 1.0, 1.0, math.pi / 2], [1.0, 1.0, 2.0, math.pi / 2]])
        f, l, d = rel(arr, 0.0, 1.0)
        self.assertAlmostEqual(f, 1.0); self.assertAlmostEqual(l, 0.0); self.assertAlmostEqual(d, 0.0)

    def test_compose_chains_relative_motions(self):
        x, y, h = compose((1.0, 0.0, math.pi / 2), (1.0, 0.0, 0.0))
        self.assertAlmostEqual(x, 1.0); self.assertAlmostEqual(y, 1.0); self.assertAlmostEqual(h, math.pi / 2)


if __name__ == '__main__':
    unittest.main()
