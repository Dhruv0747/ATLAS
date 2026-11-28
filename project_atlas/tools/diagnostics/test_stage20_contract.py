import copy
import unittest
from stage20_contract import checkpoint_errors, ready_for_candidates

class ContractTests(unittest.TestCase):
    def complete(self):
        e = {k:True for k in ('startup_before_sources','consumer_order_verified',
            'parameters_verified','map_verified','service_events_complete',
            'tf_history_complete','loss_accounting_complete','amcl_startup_ensemble_verified',
            'baseline_failure_reproduced')}
        e.update(ekf_state=[0.0]*15, ekf_covariance=[0.0]*225,
                 actual_relative_reference={'wheel':[1,2,3]})
        return e
    def test_schema_not_proof_of_physics(self):
        self.assertTrue(ready_for_candidates(self.complete()))
    def test_missing_proof_fail_closed(self):
        for key in self.complete():
            with self.subTest(key=key):
                e=self.complete(); del e[key]
                self.assertFalse(ready_for_candidates(e))
    def test_output_covariance_not_full_state(self):
        e=self.complete(); e['ekf_covariance']=[0]*36
        self.assertIn('full_225_covariance', checkpoint_errors(e))
    def test_nonfinite(self):
        for key in ('ekf_state','ekf_covariance'):
            e=self.complete(); e[key][0]=float('nan')
            self.assertFalse(ready_for_candidates(e))
    def test_single_particle_cloud_not_checkpoint(self):
        e=self.complete(); e['amcl_startup_ensemble_verified']=False
        self.assertFalse(ready_for_candidates(e))
    def test_zero_jumps_not_reproduction(self):
        e=self.complete(); e['baseline_failure_reproduced']=False
        self.assertFalse(ready_for_candidates(e))
    def test_parameters_and_map_mismatch(self):
        for key in ('parameters_verified','map_verified'):
            e=self.complete(); e[key]=False
            self.assertFalse(ready_for_candidates(e))

if __name__=='__main__': unittest.main()
