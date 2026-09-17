import math
import unittest
from atlas_im10a_shadow_test import parameters, accepted_gyro

class ShadowTest(unittest.TestCase):
    def test_isolated_and_yaw_rate_only(self):
        live=dict(publish_tf=True,transform_time_offset=.2,odom0='/yahboom/odom')
        p=parameters(live,True)
        self.assertFalse(p['publish_tf'])
        self.assertEqual(p['imu0_config'],[False]*11+[True]+[False]*3)
        self.assertTrue(p['imu0'].startswith('/atlas_imu_shadow/'))
        self.assertTrue(live['publish_tf'])
        self.assertNotIn('imu0',parameters(live,False))

    def test_bad_samples_rejected(self):
        def good(**kw):
            args=dict(frame='im10a_sensor_unvalidated',stamp=10.,now=10.1,previous=9.,xyz=(0.,0.,.1))
            args.update(kw)
            return accepted_gyro(**args)
        self.assertTrue(good())
        for kw in [dict(frame='bad'),dict(now=11.),dict(now=9.),dict(previous=10.),dict(xyz=(0.,0.,math.nan)),dict(xyz=(0.,0.,40.))]:
            self.assertFalse(good(**kw))

if __name__=='__main__': unittest.main()
