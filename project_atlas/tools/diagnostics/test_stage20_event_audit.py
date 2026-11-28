import unittest
from stage20_event_audit import audit_events

class AuditTests(unittest.TestCase):
    def fixture(self):
        ekf=[{'phase':p,'seq':i+1,'monotonic_ns':10+i,'source':'/yahboom/odom_pose',
            'source_ns':100,'state':[0]*15,'covariance':[0]*225} for i,p in enumerate(
                ['constructed_uninitialized','relative_reference_created','measurement_before','measurement_after'])]
        amcl=[{'phase':p,'seq':i+1,'monotonic_ns':20+i} for i,p in enumerate(
            ['initial_pose_received','particles_initialized','scan_tf_accepted',
             'weights_before_resample_decision','resample_before','resample_after'])]
        return ekf,amcl,{('/yahboom/odom',100)},0
    def test_complete_synthetic_ledger_not_fidelity(self):
        r=audit_events(*self.fixture());self.assertTrue(r['startup_ledger_mechanics_verified']);self.assertFalse(r['replay_fidelity_verified'])
    def test_late_start_missing_sequence_or_input(self):
        for change in ('seq','input','late'):
            e,a,s,t=self.fixture()
            if change=='seq':e[0]['seq']=2
            if change=='input':s=set()
            if change=='late':t=100
            self.assertFalse(audit_events(e,a,s,t)['startup_ledger_mechanics_verified'])
    def test_incomplete_state_or_phase(self):
        e,a,s,t=self.fixture();e[-1]['covariance']=[0]*36
        self.assertFalse(audit_events(e,a,s,t)['startup_ledger_mechanics_verified'])
    def test_native_parameter_alias_requires_snapshot(self):
        e,a,s,t=self.fixture()
        for event in e:event['source']='odom0_pose'
        self.assertFalse(audit_events(e,a,s,t)['startup_ledger_mechanics_verified'])
        self.assertTrue(audit_events(e,a,s,t,{'odom0':'/yahboom/odom'})['startup_ledger_mechanics_verified'])
        e,a,s,t=self.fixture();a.pop()
        self.assertFalse(audit_events(e,a,s,t)['startup_ledger_mechanics_verified'])

if __name__=='__main__':unittest.main()
