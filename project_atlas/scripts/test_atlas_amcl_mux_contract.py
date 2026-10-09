"""Non-actuating contract checks: candidate does NOT pass deployment gate.

Execute the repository mux guard itself, with an initially fresh confident
pose and controlled clocks. No ROS imports, nodes, services or motor output.
These tests preserve rejection evidence rather than pretending it is a fix.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
import unittest

from atlas_amcl_update_gate import AmclUpdateGate


def mux_guard():
    tree = ast.parse(Path(__file__).with_name('atlas_cmd_vel_mux.py').read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == 'localization_guard')
    scope = {'Optional': Optional}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<real-mux-guard>', 'exec'), scope)
    return scope['localization_guard']


class MuxContractTests(unittest.TestCase):
    def setUp(self):
        self.guard = mux_guard()
        self.node = SimpleNamespace(localization_rx=100.0, localization_timeout=2.5,
            operating_mode='LOCALIZATION', localization_jump_fault=None,
            localization_xy_std_m=.01, localization_max_xy_std_m=.25,
            localization_yaw_std_deg=1, localization_max_yaw_std_deg=20)

    def test_stationary_pause_blocks_at_2_51_seconds(self):
        gate = AmclUpdateGate()
        for t in (100,101,102,103):
            self.assertFalse(gate.allow(0,0,0,t,t))
        self.assertIsNone(self.guard(self.node,102.5))
        self.assertIn('LOCALIZATION STALE',self.guard(self.node,102.51))

    def test_slow_creep_blocks_before_candidate_request(self):
        gate = AmclUpdateGate()
        # 1 mm/s is below both candidate cumulative 5 mm and AMCL 5 cm
        # thresholds during the first three seconds. Even assuming perfect
        # scans/TF, no fresh pose is guaranteed before the mux deadline.
        for elapsed in range(4):
            self.assertFalse(gate.allow(elapsed*.001,0,0,100+elapsed,100+elapsed))
        self.assertIn('LOCALIZATION STALE',self.guard(self.node,103))

    def test_one_premotion_refresh_does_not_cover_later_pause(self):
        self.node.localization_rx=200
        self.assertIsNone(self.guard(self.node,201))
        self.assertIn('LOCALIZATION STALE',self.guard(self.node,203))

    def test_fresh_pose_does_not_clear_latched_jump(self):
        self.node.localization_rx=103
        self.node.localization_jump_fault='recorded jump'
        self.assertIn('LOCALIZATION JUMP',self.guard(self.node,103))

    def test_uncertainty_still_blocks_fresh_pose(self):
        self.node.localization_xy_std_m=1.2
        self.assertIn('UNCERTAINTY',self.guard(self.node,100))


if __name__ == '__main__':
    unittest.main()
