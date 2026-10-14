"""Real-baseline contract tests; no ROS, replay launch or production writes."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import yaml
from stage19_contract import candidate_gate, variants

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class MinimalWheelPoseCandidateTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((HERE / 'fixtures/minimal_wheel_pose_candidate.json').read_text())
        self.raw = (ROOT / self.manifest['baseline_path']).read_bytes()
        self.config = yaml.safe_load(self.raw)

    def test_exact_reviewed_baseline_identity(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), self.manifest['baseline_sha256'])

    def test_real_configuration_changes_only_two_pose_flags(self):
        original = copy.deepcopy(self.config)
        built = variants(self.config)
        a = built['A']['atlas_ekf']['ros__parameters']
        b = built['B']['atlas_ekf']['ros__parameters']
        self.assertEqual(self.config, original)
        self.assertEqual(b['odom0_config'], self.manifest['candidate_odom0_config'])
        self.assertEqual(b['imu0_config'], self.manifest['candidate_imu0_config'])
        self.assertEqual([i for i, (x, y) in enumerate(zip(a['odom0_config'], b['odom0_config'])) if x != y], [0, 1])
        b['odom0_config'][:2] = [True, True]
        self.assertEqual(a, b)  # Includes all covariance, timing, queues and frame settings.
        baseline = original['atlas_ekf']['ros__parameters']
        a.pop('use_sim_time')
        self.assertEqual(a, baseline)

    def test_no_new_sensor_authority_or_live_permission(self):
        b = variants(self.config)['B']['atlas_ekf']['ros__parameters']
        self.assertEqual([i for i, selected in enumerate(b['imu0_config']) if selected], [11])
        self.assertEqual([i for i, selected in enumerate(b['odom0_config']) if selected], [6, 7])
        self.assertEqual(b['transform_time_offset'], 0.2)
        self.assertTrue(b['odom0_relative'])
        for key in ('allow_live_deployment', 'allow_motor_commands', 'amcl_improvement_claim'):
            self.assertIs(self.manifest[key], False)

    def test_local_pose_and_particle_outputs_do_not_unlock_historical_replay(self):
        # Public output is not the saved cross-covariance/relative-anchor/RNG checkpoint.
        partial = {'baseline_reproduced': False, 'ekf_initial_reference_verified': False,
                   'amcl_initial_state_verified': False, 'historical_parameters_verified': False,
                   'timing_fidelity_verified': False, 'odom_present': True,
                   'particles_present': True, 'raw_encoders_present': True}
        self.assertFalse(candidate_gate(partial))


if __name__ == '__main__':
    unittest.main()
