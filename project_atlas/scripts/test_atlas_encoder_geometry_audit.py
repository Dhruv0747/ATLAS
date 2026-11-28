"""Checks for the pure helpers used by the offline geometry reconstruction."""
import unittest
from atlas_encoder_selection import EncoderDeltaEstimator, four_wheel_path_scales


class GeometryReplayTest(unittest.TestCase):
    def test_straight_scales(self):
        self.assertEqual(four_wheel_path_scales(0,.367,.260,
            ['rear_left','rear_right','front_left','front_right']),(1.,1.,1.,1.))

    def test_known_arc_recovers_body_distance(self):
        scales=four_wheel_path_scales(2,.367,.260,
            ['rear_left','rear_right','front_left','front_right'])
        est=EncoderDeltaEstimator()
        est.update([0]*4,range(4),scales)
        self.assertAlmostEqual(est.update([.02*s for s in scales],range(4),scales),.02)
        self.assertEqual(len(est.last_accepted),4)

    def test_two_versus_two_remains_rejected(self):
        est=EncoderDeltaEstimator()
        est.update([0]*4,range(4))
        self.assertEqual(est.update([.02,.02,-.02,-.02],range(4)),0)
        self.assertEqual(est.last_accepted,())


if __name__=='__main__':unittest.main()
