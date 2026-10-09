import math
import unittest
from types import SimpleNamespace as NS
import numpy as np
from atlas_competing_pose_evidence import inverse, interpolate, integrate_gyro, wrap, points_for_parity, particle_support


class CompetingEvidenceTests(unittest.TestCase):
    def test_inverse_transform(self):
        p=np.array([2.,3.,math.pi/2]); inv=inverse(p)
        self.assertTrue(np.allclose(inv,[-3.,2.,-math.pi/2]))

    def test_heading_wrap_residual(self):
        self.assertAlmostEqual(math.degrees(abs(wrap(math.radians(179)-math.radians(-179)))),2)

    def test_pose_interpolation_shortest_yaw(self):
        p=interpolate([(0,np.array([0.,0.,math.radians(179)])),
                       (.2,np.array([2.,4.,math.radians(-179)]))],.1)
        self.assertTrue(np.allclose(p,[1,2,math.pi]))

    def test_no_pose_extrapolation_or_large_gap(self):
        rows=[(0,np.zeros(3)),(1,np.ones(3))]
        self.assertIsNone(interpolate(rows,-1))
        self.assertIsNone(interpolate(rows,2))
        self.assertIsNone(interpolate(rows,.5))

    def test_constant_gyro_exact_boundaries(self):
        rows=[(t,2.) for t in np.arange(0,2.1,.1)]
        self.assertAlmostEqual(integrate_gyro(rows,.15,1.85),3.4)

    def test_gyro_missing_or_duplicate_is_unknown(self):
        self.assertIsNone(integrate_gyro([],0,1))
        self.assertIsNone(integrate_gyro([(0,1),(0,2),(1,1)],0,1))
        self.assertIsNone(integrate_gyro([(0,1),(.1,1)],0,1))

    def test_gyro_gap_is_not_bridged(self):
        self.assertIsNone(integrate_gyro([(0,1),(.1,1),(1,1)],0,1))

    def test_nonfinite_gyro_is_unknown(self):
        self.assertIsNone(integrate_gyro([(0,1),(.1,float('nan'))],0,.1))

    def test_invalid_beam_does_not_change_holdout_parity(self):
        scan=NS(ranges=[1,float('nan'),2,3],range_min=.1,range_max=10,
                angle_min=0,angle_increment=0)
        self.assertTrue(np.allclose(points_for_parity(scan,0),[[1,0],[2,0]]))
        self.assertTrue(np.allclose(points_for_parity(scan,1),[[3,0]]))

    def test_xy_support_alone_cannot_establish_heading_support(self):
        result=particle_support(np.array([[0.,0.,math.pi],[1,1,0]]),
                                np.array([.9,.1]),np.zeros(3))
        self.assertEqual(result['count_within_0_5m'],1)
        self.assertEqual(result['count_within_0_5m_and_20deg'],0)
        self.assertEqual(result['weight_within_0_5m_and_20deg'],0)


if __name__=='__main__':
    unittest.main()
