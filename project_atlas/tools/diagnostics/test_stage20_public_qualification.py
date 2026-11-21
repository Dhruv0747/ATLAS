import unittest
from stage20_public_package import qualify

class QualificationTests(unittest.TestCase):
    def test_missing_evidence_refused(self):
        with self.assertRaises(ValueError):qualify({'scope':'PARTIAL_PUBLIC_ONLY','binary_overlays':[]},{})
    def test_cannot_qualify_private_overlay(self):
        with self.assertRaises(ValueError):qualify({'scope':'FULL_CHECKPOINT','binary_overlays':['ekf']},{})
    def test_ready_never_means_permission_or_replay(self):
        evidence={name:True for name in ('native_full_duration_rates','kernel_memory_tasks_total_cpu_limits',
            'actual_service_graph','native_production_adapter','cdr_receipt_integrity',
            'scratch_install_activation_rollback','quota_crash_missing_sensor_tests')}
        evidence['scope_reviewed']='PARTIAL_PUBLIC_ONLY'
        result=qualify({'scope':'PARTIAL_PUBLIC_ONLY','binary_overlays':[]},evidence)
        self.assertTrue(result['deployment_ready']);self.assertFalse(result['owner_installation_approved'])
        self.assertFalse(result['full_checkpoint_deployment_ready']);self.assertFalse(result['replay_fidelity_verified'])
if __name__=='__main__':unittest.main()
