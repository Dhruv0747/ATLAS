import unittest
import numpy as np
from atlas_scan_rotation_sensitivity import rotate


class RotationTest(unittest.TestCase):
    def test_zero_and_quarter_turn(self):
        points = np.array([[1., 0.], [0., 1.]])
        np.testing.assert_allclose(rotate(points, np.zeros(2)), points)
        np.testing.assert_allclose(rotate(points, np.full(2, np.pi/2)), [[0,1],[-1,0]], atol=1e-10)

    def test_norm_preserved(self):
        points = np.array([[1., 2.], [-3., 1.]])
        np.testing.assert_allclose(np.linalg.norm(rotate(points, np.array([.2,-.4])),axis=1), np.linalg.norm(points,axis=1))


if __name__ == '__main__':
    unittest.main()
