import math
import unittest
from stage18_motion_model import geometry, integrate, consistency
from atlas_encoder_selection import four_wheel_path_scales


class Stage18ModelTests(unittest.TestCase):
    def test_symmetric_model_matches_preserved_legacy(self):
        for angle in (-30, -10, 0, 10, 30):
            g=geometry(math.radians(angle), -math.radians(angle), .367, .26)
            self.assertAlmostEqual(g['lateral_ratio'], 0)
            legacy=four_wheel_path_scales(g['curvature'], .367, .26,
                ('rear_left','rear_right','front_left','front_right'))
            for a,b in zip(legacy,g['scales']): self.assertAlmostEqual(a,b)

    def test_crab_motion_exposes_legacy_omitted_lateral(self):
        g=geometry(math.radians(20),math.radians(20),.367,.26)
        self.assertEqual(g['curvature'],0)
        p=integrate(0,0,0,1,g['lateral_ratio'],0)
        self.assertAlmostEqual(p[1],math.tan(math.radians(20)))
        self.assertGreater(g['scales'][0],1)

    def test_asymmetric_axles_obey_no_lateral_slip(self):
        g=geometry(.25,-.12,.367,.26)
        for x,y,a in zip((-.367/2,)*2+(.367/2,)*2,(.13,-.13,.13,-.13),g['wheel_angles']):
            self.assertAlmostEqual(-math.sin(a)*(1-g['curvature']*y)+
                math.cos(a)*(g['lateral_ratio']+g['curvature']*x),0)

    def test_reverse_is_inverse_without_global_sign_flip(self):
        g=geometry(.2,-.15,.367,.26)
        p=integrate(0,0,0,.4,g['lateral_ratio'],.4*g['curvature'])
        p=integrate(*p,-.4,g['lateral_ratio'],-.4*g['curvature'])
        for v in p: self.assertAlmostEqual(v,0)

    def test_bad_geometry_rejected(self):
        for args in ((float('nan'),0,.367,.26),(0,0,0,.26),(1.5,0,.367,.26)):
            with self.assertRaises(ValueError): geometry(*args)

    def evaluate(self, **changes):
        p=dict(wheel_yaw=.13,gyro_yaw=-.33,lidar_yaw=-.28,gyro_coverage=1,
            lidar_valid=True,gyro_uncertainty=.035,lidar_uncertainty=.035,
            sync_uncertainty=.05,max_rate=.4,wheel_uncertainty=.05)
        p.update(changes);return consistency(**p)['classification']

    def test_independent_reference_agreement_detects_wrong_wheel(self):
        self.assertEqual(self.evaluate(),'WHEEL_SUSPECT')

    def test_reference_disagreement_never_selects_winner(self):
        self.assertEqual(self.evaluate(lidar_yaw=.3),'REFERENCES_DISAGREE')

    def test_missing_stale_and_uncertain_are_not_healthy(self):
        self.assertEqual(self.evaluate(gyro_coverage=.5),'UNKNOWN')
        self.assertEqual(self.evaluate(lidar_yaw=None),'UNKNOWN')
        self.assertEqual(self.evaluate(lidar_valid=False),'UNKNOWN')
        self.assertEqual(self.evaluate(wheel_uncertainty=2),'CONSISTENT_WITH_ASSUMED_BOUNDS')


if __name__=='__main__': unittest.main()
