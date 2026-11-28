import ast
import math
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Optional
import unittest
from atlas_localization_refresh_gate import RefreshRequestGate


class RefreshTests(unittest.TestCase):
    def test_one_request_until_fresh_motion(self):
        gate=RefreshRequestGate(); health={'processing_state':'PROCESSING'}
        gate.observe_odom(0,0,0,100,100)
        self.assertTrue(gate.claim(health,100,True,True))
        for t in (101,102,103):
            gate.observe_odom(0,0,0,t,t)
            self.assertFalse(gate.claim(health,t,True,True))
        gate.observe_odom(.01,0,0,104,104)
        self.assertTrue(gate.claim(health,104,True,True))

    def test_missing_stale_health_and_invalid_estimate_do_not_request(self):
        gate=RefreshRequestGate(); health={'processing_state':'PROCESSING'}
        self.assertFalse(gate.claim(health,100,True,True))
        gate.observe_odom(0,0,0,100,100)
        for h,t,m,v in ((health,101,True,True),(health,100,False,True),
                        (health,100,True,False),({},100,True,True)):
            self.assertFalse(gate.claim(h,t,m,v))

    def test_clock_reset_does_not_rearm(self):
        gate=RefreshRequestGate(); health={'processing_state':'PROCESSING'}
        gate.observe_odom(0,0,0,100,100); gate.claim(health,100,True,True)
        gate.observe_odom(0,0,0,1,1)
        self.assertFalse(gate.claim(health,1,True,True))


class ActualMuxIntegrationTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).with_name('atlas_cmd_vel_mux.py')
        tree=ast.parse(path.read_text())
        names={'localization_guard','navigation_localization_guard'}
        methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in names]
        scope={'math':math,'Optional':Optional,'Twist':object,'Empty':lambda:object()}
        exec(compile(ast.Module(body=methods,type_ignores=[]),str(path),'exec'),scope)
        self.calls=[]; self.health={'processing_state':'PROCESSING'}
        self.ros_now=103
        self.node=NS(localization_rx=100.,localization_timeout=2.5,
            operating_mode='LOCALIZATION',localization_jump_fault=None,
            localization_xy_std_m=.01,localization_max_xy_std_m=.25,
            localization_yaw_std_deg=1.,localization_max_yaw_std_deg=20.,
            amcl_processing_gate_enabled=True,
            amcl_processing=NS(snapshot=lambda *_:self.health),
            localization_refresh_gate=RefreshRequestGate(),
            localization_refresh_pub=NS(publish=self.calls.append),
            get_clock=lambda:NS(now=lambda:NS(nanoseconds=self.ros_now*10**9)),
            moving=lambda command:bool(command))
        self.node.localization_guard=lambda now:scope['localization_guard'](self.node,now)
        self.guard=lambda command=True:scope['navigation_localization_guard'](self.node,command,self.ros_now)
        self.node.localization_refresh_gate.observe_odom(0,0,0,103,103)

    def test_request_does_not_release_stale_command(self):
        self.assertIn('STALE',self.guard())
        self.assertEqual(len(self.calls),1)
        self.assertIn('STALE',self.guard())
        self.assertEqual(len(self.calls),1)
        self.node.localization_rx=103 # Actual fresh pose callback is required.
        self.assertIsNone(self.guard())

    def test_healthy_processing_never_clears_jump_or_uncertainty(self):
        self.node.localization_rx=103
        self.node.localization_jump_fault='large jump'
        self.assertIn('JUMP',self.guard())
        self.node.localization_jump_fault=None
        self.node.localization_xy_std_m=1
        self.assertIn('UNCERTAINTY',self.guard())
        self.assertEqual(self.calls,[])

    def test_processing_loss_adds_veto_even_with_fresh_pose(self):
        self.node.localization_rx=103
        self.health={'processing_state':'UNAVAILABLE'}
        self.assertIn('PROCESSING UNAVAILABLE',self.guard())
        self.assertEqual(self.calls,[])

    def test_zero_command_cannot_repeat_measurements(self):
        self.assertIn('STALE',self.guard(False))
        self.assertEqual(self.calls,[])

    def test_feature_off_preserves_guard(self):
        self.node.amcl_processing_gate_enabled=False
        self.assertIn('STALE',self.guard())
        self.assertEqual(self.calls,[])


if __name__=='__main__': unittest.main()
