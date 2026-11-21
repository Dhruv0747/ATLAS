import math
import unittest
import numpy as np
from stage18_motion_consistency import relative, scan_motion


class Stage18ReplayTests(unittest.TestCase):
    def test_source_time_interpolation_wraps_heading(self):
        a=np.array([[0,0,0,math.radians(179)],[.2,.1,0,math.radians(-179)]])
        r=relative(a,.05,.15)
        self.assertAlmostEqual(math.degrees(r[2]),1)

    def test_no_extrapolation_or_stale_pose(self):
        a=np.array([[0,0,0,0],[1,1,0,0]])
        self.assertIsNone(relative(a,0,.8))
        self.assertIsNone(relative(a,-.1,.1))
        self.assertIsNone(relative(a,0,2))
        a=np.array([[0,0,0,0],[.1,0,0,0],[.9,1,0,0],[1,1,0,0]])
        self.assertIsNone(relative(a,.05,.95))

    def test_neutral_icp_recovers_signed_motion_without_wheel_prior(self):
        rng=np.random.default_rng(18)
        a=rng.uniform(-2,2,(300,2));h=-.08;dx,dy=.07,.01
        rot=np.array([[math.cos(h),math.sin(h)],[-math.sin(h),math.cos(h)]])
        b=(a-[dx,dy])@rot.T
        result=scan_motion(a,b)
        self.assertTrue(result['valid'])
        for got,want in zip(result['motion'],(dx,dy,h)): self.assertAlmostEqual(got,want,places=5)

    def test_sparse_scan_cannot_claim_reference_agreement(self):
        a=np.zeros((10,2))
        self.assertFalse(scan_motion(a,a)['valid'])


if __name__=='__main__': unittest.main()
