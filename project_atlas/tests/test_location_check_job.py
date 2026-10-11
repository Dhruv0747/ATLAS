import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from atlas_location_check_job import LocationCheckJob, CheckAborted, evidence_error


def good():
    return dict(scan_age_s=.2,scan_receipt_age_s=.1,odom_age_s=.1,imu_age_s=.1,
                amcl_age_s=.2,map_id='abc',loaded_map_id='abc',stationary_epoch=1,
                localization_epoch=1,scan_stamp=123.,stationary=True,stop_latched=True,
                commands_zero=True,tf_at_scan=True,tf_chain_consistent=True,
                coverage_qualified=True,amcl_pose=[1.,2.,0.])


class JobTests(unittest.TestCase):
    def setUp(self):
        self.now=10.
        self.job=LocationCheckJob(clock=lambda:self.now)

    def test_complete_never_authorizes_navigation_or_correction(self):
        token=self.job.start(good())
        self.assertTrue(self.job.finish(token,dict(state='VERIFIED'),good()))
        result=self.job.snapshot()
        self.assertFalse(result['navigation_authorized'])
        self.assertFalse(result['correction_enabled'])

    def test_concurrent(self):
        self.job.start(good())
        with self.assertRaises(ValueError): self.job.start(good())

    def test_cancel_keeps_slot_until_worker_exits(self):
        token=self.job.start(good());self.job.cancel(token)
        with self.assertRaises(ValueError): self.job.start(good())
        self.assertFalse(self.job.finish(token,dict(state='VERIFIED'),good()))
        self.assertEqual(self.job.snapshot()['state'],'CANCELLED')
        self.job.start(good())

    def test_timeout_keeps_slot(self):
        token=self.job.start(good());self.now+=31
        self.assertEqual(self.job.snapshot()['state'],'TIMED_OUT')
        with self.assertRaises(ValueError): self.job.start(good())
        self.assertFalse(self.job.finish(token,dict(state='VERIFIED'),good()))

    def test_old_result_cannot_replace_new(self):
        old=self.job.start(good());self.job.cancel(old);self.job.finish(old)
        new=self.job.start(good())
        self.assertFalse(self.job.finish(old,dict(state='VERIFIED'),good()))
        self.assertEqual(self.job.snapshot()['request_id'],new)

    def test_missing_final_evidence(self):
        token=self.job.start(good())
        self.assertFalse(self.job.finish(token,dict(state='VERIFIED')))

    def test_all_evidence_fields_required(self):
        for key in good():
            with self.subTest(key=key):
                e=good();del e[key]
                self.assertIsNotNone(evidence_error(e))

    def test_stale_future_nonfinite_ages(self):
        for key in ('scan_age_s','scan_receipt_age_s','odom_age_s','imu_age_s','amcl_age_s'):
            for value in (-1,99,math.nan,math.inf):
                with self.subTest(key=key,value=value):
                    e=good();e[key]=value
                    self.assertIsNotNone(evidence_error(e))

    def test_changed_evidence_invalidates(self):
        for key,value in [('map_id','changed'),('stationary_epoch',2),('localization_epoch',2),
                          ('stationary',False),('tf_at_scan',False),('coverage_qualified',False),
                          ('amcl_pose',[2.,2.,0.]),('amcl_pose',[1.,2.,.2])]:
            with self.subTest(key=key):
                job=LocationCheckJob();token=job.start(good());e=good();e[key]=value
                self.assertFalse(job.finish(token,dict(state='VERIFIED'),e))
                self.assertEqual(job.snapshot()['state'],'STALE')

    def test_result_copy_isolated(self):
        token=self.job.start(good());s=self.job.snapshot();s['evidence']['map_id']='bad'
        self.assertEqual(self.job.snapshot()['evidence']['map_id'],'abc')

    def test_confirmation_not_implemented(self):
        self.assertFalse(hasattr(self.job,'reseed'))

    def test_bad_stamp(self):
        for value in (0,-1,math.nan,math.inf,True):
            e=good();e['scan_stamp']=value
            self.assertIsNotNone(evidence_error(e))

    def test_completed_result_is_historical(self):
        token=self.job.start(good())
        self.job.finish(token,dict(state='VERIFIED'),good())
        self.assertTrue(self.job.snapshot()['historical_result'])
        self.assertIn('result_age_s',self.job.snapshot())

if __name__=='__main__': unittest.main()
