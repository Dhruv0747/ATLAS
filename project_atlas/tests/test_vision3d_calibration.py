"""Synthetic contract tests, not camera accuracy certification."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
from calibration_validation import validate_calibration, depth_statistics


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.c = dict(device_serial='test', source='measured_target',
                      independently_validated=True, validation_evidence='offline_fixture',
                      width=4, height=4, frame_id='depth_optical_frame',
                      k=[5.,0.,1.5,0.,5.,1.5,0.,0.,1.], d=[0.]*5,
                      distortion_model='plumb_bob')

    def check(self, c):
        return validate_calibration(c, 'test', 4, 4, 'depth_optical_frame')

    def test_valid_document_is_not_accuracy_pass(self):
        self.assertFalse(self.check(self.c)['physical_accuracy_proven_by_this_check'])

    def test_provenance_identity_rejected(self):
        for key, value in [('source','FOV'), ('device_serial','other'),
                           ('independently_validated',False), ('width',640),
                           ('frame_id','camera_link'), ('validation_evidence','')]:
            c=copy.deepcopy(self.c); c[key]=value
            with self.assertRaises(ValueError): self.check(c)

    def test_invalid_matrices_rejected(self):
        for index,value in [(0,0),(4,-1),(2,100),(5,float('inf')),(8,0),(1,1)]:
            c=copy.deepcopy(self.c);c['k'][index]=value
            with self.assertRaises(ValueError):self.check(c)
        c=copy.deepcopy(self.c);c['d'][4]=float('nan')
        with self.assertRaises(ValueError):self.check(c)

    def test_measured_depth_statistics(self):
        r=depth_statistics([[[1000,0],[float('nan'),1020]],[[980,1000],[1000,1000]]],1.,.001,(0,0,2,2))
        self.assertEqual(r['median_m'],1.)
        self.assertEqual(r['invalid_percent'],25.)
        self.assertIsNone(r['accuracy_pass'])

    def test_temporal_variation_and_bias(self):
        r=depth_statistics([[[900]],[[1100]]],1.,.001,(0,0,1,1))
        self.assertAlmostEqual(r['frame_median_population_std_m'],.1)
        self.assertAlmostEqual(r['median_absolute_error_m'],.1)

    def test_invalid_or_unknown_rejected(self):
        for frames,dist,scale,roi in [([],1,.001,(0,0,1,1)),([[[0]]],1,.001,(0,0,1,1)),
                                     ([[[1]]],0,.001,(0,0,1,1)),([[[1]]],1,0,(0,0,1,1)),
                                     ([[[1]]],1,.001,(0,0,2,2))]:
            with self.assertRaises(ValueError):depth_statistics(frames,dist,scale,roi)


if __name__ == '__main__':unittest.main()
