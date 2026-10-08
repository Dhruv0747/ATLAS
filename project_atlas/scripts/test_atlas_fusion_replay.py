"""Offline checks; run in a sourced ROS Humble environment."""
import unittest
import yaml

from atlas_fusion_replay import ALLOWED, configurations


class FusionReplayTest(unittest.TestCase):
    def test_only_xy_selection_changes(self):
        source = {'atlas_ekf': {'ros__parameters': {
            'odom0': '/yahboom/odom',
            'imu0': '/im10a/imu/bias_corrected_candidate',
            'odom0_config': [True, True] + [False] * 13,
            'transform_time_offset': 0.2}}}
        raw = yaml.safe_dump(source)
        variants = configurations(raw)
        baseline = variants['pose_velocity']['atlas_ekf']['ros__parameters']
        candidate = variants['velocity_only']['atlas_ekf']['ros__parameters']
        self.assertTrue(baseline['use_sim_time'])
        self.assertEqual(baseline['odom0_config'][:2], [True, True])
        self.assertEqual(candidate['odom0_config'][:2], [False, False])
        candidate['odom0_config'][:2] = [True, True]
        self.assertEqual(candidate, baseline)
        self.assertEqual(yaml.safe_dump(source), raw)

    def test_rejects_unexpected_source(self):
        with self.assertRaises(ValueError):
            configurations(yaml.safe_dump({'atlas_ekf': {'ros__parameters': {
                'odom0': '/unexpected', 'imu0': '/unexpected'}}}))

    def test_no_command_or_recorded_fused_pose_topics(self):
        self.assertEqual(ALLOWED, {'/scan', '/tf', '/tf_static', '/yahboom/odom',
                                  '/im10a/imu/bias_corrected_candidate'})


if __name__ == '__main__':
    unittest.main()
