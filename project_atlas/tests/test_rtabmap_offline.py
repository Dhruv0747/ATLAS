import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
from rtabmap_offline import admit, isolated_env
from unittest.mock import patch


def fixture():
    c = dict(device_serial='synthetic', source='measured_target', independently_validated=True,
             validation_evidence='SYNTHETIC ONLY', width=32, height=24,
             frame_id='test_optical_frame', k=[30.,0,16,0,30.,12,0,0,1],
             d=[0.]*5, distortion_model='plumb_bob')
    return dict(serial='synthetic', rgb=c, depth=copy.deepcopy(c), depth_encoding='16UC1',
                units_to_m=.001, scale_verified=True, registered_to_rgb=True,
                registration_evidence='synthetic', tf_evidence='synthetic',
                tf_at_all_frame_stamps=True, rgb_stamp=10., depth_stamp=10.,
                info_stamp=10., odom_stamp=10., replay_time=10.1)


class Admission(unittest.TestCase):
    def test_isolation(self):
        with patch.dict('os.environ', {'ROS_DOMAIN_ID':'0','ROS_DISCOVERY_SERVER':'robot:11811'}):
            env=isolated_env()
            self.assertEqual(env['ROS_DOMAIN_ID'],'179')
            self.assertEqual(env['ROS_LOCALHOST_ONLY'],'1')
            self.assertNotIn('ROS_DISCOVERY_SERVER',env)

    def test_safe(self):
        self.assertTrue(admit(fixture()))

    def test_rejections(self):
        changes = [('scale_verified',False),('units_to_m',1.),('registered_to_rgb',False),
                   ('tf_at_all_frame_stamps',False),('tf_evidence',''),('rgb_stamp',9.),
                   ('depth_stamp',10.08),('info_stamp',float('nan')),('odom_stamp',11.)]
        for key,value in changes:
            with self.subTest(key=key):
                m=fixture(); m[key]=value
                with self.assertRaises(ValueError): admit(m)

    def test_missing(self):
        m=fixture(); del m['rgb']
        with self.assertRaises(KeyError): admit(m)

    def test_bad_calibration(self):
        m=fixture(); m['depth']['k'][0]=float('nan')
        with self.assertRaises(ValueError): admit(m)

    def test_boundaries(self):
        m=fixture(); m['replay_time']=10.5
        self.assertTrue(admit(m))
        m['replay_time']=10.5001
        with self.assertRaises(ValueError): admit(m)


if __name__ == '__main__': unittest.main()
