"""Configuration contract, not a simulated full RPP action."""
import math
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).parents[2]
class InflationContract(unittest.TestCase):
    def setUp(self):
        self.paths=[ROOT/'project_atlas/config/nav2_params.yaml',ROOT/'project_atlas_ws/src/tortoisebot_bringup/config/nav2_params.yaml']
        self.cfg=yaml.safe_load(self.paths[0].read_text())
    def test_both_copies_identical(self):
        self.assertEqual(yaml.safe_load(self.paths[1].read_text()),self.cfg)
    def test_cost_conversion_matches_local_inflation(self):
        pp=self.cfg['controller_server']['ros__parameters']['FollowPath']
        local=self.cfg['local_costmap']['local_costmap']['ros__parameters']
        self.assertEqual(pp['inflation_cost_scaling_factor'],local['inflation_layer']['cost_scaling_factor'])
        self.assertTrue(pp['use_collision_detection'])
        self.assertEqual(local['inflation_layer']['inflation_radius'],.28)
    def test_inverse_cost_roundtrip(self):
        factor=self.cfg['controller_server']['ros__parameters']['FollowPath']['inflation_cost_scaling_factor']
        for distance in (.20,.22,.24,.26,.28):
            cost=int(252*math.exp(-15*(distance-.18)))
            corrected=.18-math.log(cost/252)/factor
            old=.18-math.log(cost/252)/3
            self.assertLess(abs(corrected-distance),.002)
            self.assertGreater(old,corrected)
if __name__=='__main__':unittest.main()
