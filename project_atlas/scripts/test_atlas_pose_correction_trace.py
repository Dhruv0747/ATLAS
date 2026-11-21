import math
import unittest
import numpy as np
from atlas_pose_correction_trace import sample, wrapped


class TraceTest(unittest.TestCase):
    def test_interpolation(self):
        series=np.array([[0,0,0,0],[2,2,4,1]])
        np.testing.assert_allclose(sample(series,1),[1,2,.5])

    def test_reject_extrapolation(self):
        series=np.array([[0,0],[2,2]])
        self.assertIsNone(sample(series,-1))
        self.assertIsNone(sample(series,3))

    def test_angle_wrap(self):
        self.assertAlmostEqual(math.degrees(wrapped(math.radians(358))),-2)


if __name__=='__main__': unittest.main()
