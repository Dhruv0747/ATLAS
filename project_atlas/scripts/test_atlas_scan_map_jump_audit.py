import math
import unittest
import numpy as np
from atlas_scan_map_jump_audit import compose, points_at


class GeometryTest(unittest.TestCase):
    def test_compose_rotated_translation(self):
        np.testing.assert_allclose(compose([1,2,math.pi/2],[1,0,0]),[1,3,math.pi/2],atol=1e-10)

    def test_point_projection(self):
        np.testing.assert_allclose(points_at(np.array([[1.,0.]]),[1,2,math.pi/2]),[[1,3]],atol=1e-10)

    def test_origin_translation_is_not_robot_displacement(self):
        base=[5,0,0]
        angle=.2
        correction=[5-5*math.cos(angle),-5*math.sin(angle),angle]
        self.assertGreater(np.linalg.norm(correction[:2]),.9)
        np.testing.assert_allclose(compose(correction,base)[:2],[5,0],atol=1e-10)


if __name__=='__main__':
    unittest.main()
