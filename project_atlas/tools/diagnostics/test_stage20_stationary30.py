import unittest
from stage20_capture import stationary_health,public_profile,final_reason,STATIONARY_CONTINUOUS,STATIONARY_ONCE

class StationaryTests(unittest.TestCase):
    def test_stop_at_deadline_not_complete(self):
        for stop in ('sigterm','nonstationary_control_state','invalid_source_freshness'):
            self.assertEqual(final_reason('duration_complete',[stop]),stop)
        self.assertEqual(final_reason('writer_error',['sigterm']),'writer_error')
        self.assertEqual(final_reason('duration_complete',[]),'duration_complete')
    def test_legacy_unchanged(self):
        self.assertEqual(public_profile(120,500,False),'legacy_public_120')
        with self.assertRaises(ValueError):public_profile(30,500,False)
    def test_explicit_exact_duration(self):
        self.assertEqual(public_profile(30,500,True),'stationary_30_v1')
        for duration,quota in ((31,500),(120,500),(30,64)):
            with self.assertRaises(ValueError):public_profile(duration,quota,True)
    def test_missing_not_free(self):
        self.assertTrue(stationary_health({},10)['missing'])
    def test_stale_continuous(self):
        seen=dict.fromkeys(STATIONARY_CONTINUOUS+STATIONARY_ONCE,10)
        self.assertFalse(stationary_health(seen,11)['stale'])
        seen['/scan']=8
        self.assertIn('/scan',stationary_health(seen,11)['stale'])
    def test_event_driven_amcl_not_forced(self):
        seen=dict.fromkeys(STATIONARY_CONTINUOUS,20)
        seen.update(dict.fromkeys(STATIONARY_ONCE,1))
        self.assertEqual(stationary_health(seen,21),{'missing':[],'stale':[]})
    def test_future_receipt_rejected(self):
        self.assertIn('/scan',stationary_health({'/scan':30},20)['stale'])

if __name__=='__main__':unittest.main()
