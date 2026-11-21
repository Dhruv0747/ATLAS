import unittest
from stage19_contract import variants,keep_transform,INPUTS,OUTPUTS,CRITERIA,relative_pose_xy,candidate_gate
import math


class Stage19Tests(unittest.TestCase):
    def config(self):
        wheel=[False]*15;imu=[False]*15
        for i in (0,1,6,7): wheel[i]=True
        imu[11]=True
        return {'atlas_ekf':{'ros__parameters':{'odom0':'/yahboom/odom',
            'imu0':'/im10a/imu/bias_corrected_candidate','odom0_config':wheel,
            'imu0_config':imu,'transform_time_offset':.2}}}

    def test_one_variable_only_and_no_source_mutation(self):
        c=self.config();v=variants(c)
        self.assertTrue(c['atlas_ekf']['ros__parameters']['odom0_config'][0])
        self.assertEqual(v['B']['atlas_ekf']['ros__parameters']['transform_time_offset'],.2)
        p=v['B']['atlas_ekf']['ros__parameters'];p['odom0_config'][:2]=[True,True]
        self.assertEqual(v['A'],v['B'])

    def test_wrong_sources_and_yaw_authority_rejected(self):
        c=self.config();c['atlas_ekf']['ros__parameters']['odom0']='other'
        with self.assertRaises(ValueError): variants(c)
        c=self.config();c['atlas_ekf']['ros__parameters']['odom0_config'][5]=True
        with self.assertRaises(ValueError): variants(c)

    def test_duplicate_tf_and_actuator_paths_excluded(self):
        for pair in (('map','odom'),('odom','base_link'),('/map','/odom')):
            self.assertFalse(keep_transform(*pair))
        self.assertTrue(keep_transform('base_link','base_footprint'))
        for topic in INPUTS|OUTPUTS: self.assertNotIn('cmd_vel',topic)
        self.assertNotIn('/odom',INPUTS)

    def test_global_claim_requires_faithful_baseline(self):
        self.assertFalse(CRITERIA['production_deployment_authorized'])
        self.assertEqual(CRITERIA['missing_truth'],'UNKNOWN, not a pass')

    def test_relative_reference_rotates_translation_without_fusing_yaw(self):
        self.assertEqual(relative_pose_xy((1,0),(0,0,0)),(1,0))
        x,y=relative_pose_xy((1,0),(0,0,math.pi/2))
        self.assertAlmostEqual(x,0);self.assertAlmostEqual(y,-1)

    def test_cold_start_first_pose_becomes_zero_observation(self):
        self.assertEqual(relative_pose_xy((18.392,-3.654),(18.392,-3.654,-1.94)),(0,0))

    def test_candidates_blocked_by_incomplete_baseline(self):
        self.assertFalse(candidate_gate(None))
        self.assertFalse(candidate_gate({'baseline_reproduced':True}))
        a={k:True for k in ('baseline_reproduced','ekf_initial_reference_verified',
            'amcl_initial_state_verified','historical_parameters_verified','timing_fidelity_verified')}
        self.assertTrue(candidate_gate(a));a['ekf_initial_reference_verified']=False
        self.assertFalse(candidate_gate(a))


if __name__=='__main__': unittest.main()
