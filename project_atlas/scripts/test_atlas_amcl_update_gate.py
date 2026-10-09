import math
import unittest
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from atlas_amcl_update_gate import AmclUpdateGate


class MissionWiringTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).with_name('atlas_mission_control.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == 'AtlasMissionControl')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                      and n.name == 'request_periodic_localization_update')
        scope = {'math': math, 'EmptyService': NS(Request=lambda: object())}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<mission-method>', 'exec'), scope)
        self.calls = []
        self.ready = True
        self.pending = False
        def call(request):
            self.calls.append(request)
            return NS(done=lambda: not self.pending)
        self.node = NS(nomotion_client=NS(service_is_ready=lambda: self.ready, call_async=call),
                       localization_update_future=None, localization_odom=None,
                       amcl_update_gate=AmclUpdateGate(),
                       get_clock=lambda: NS(now=lambda: NS(nanoseconds=self.now*10**9)))
        self.now = 1
        self.tick = lambda: scope['request_periodic_localization_update'](self.node)

    def odom(self, x=0, frame='odom', norm_w=1):
        self.node.localization_odom = NS(header=NS(frame_id=frame, stamp=NS(sec=self.now, nanosec=0)),
            pose=NS(pose=NS(position=NS(x=x,y=0), orientation=NS(x=0,y=0,z=0,w=norm_w))))

    def test_stationary_then_motion_and_pending_request(self):
        self.odom(); self.tick()
        self.now=2; self.odom(); self.tick()
        self.assertEqual(len(self.calls), 0)
        self.now=3; self.odom(.01); self.pending=True; self.tick()
        self.now=4; self.odom(.02); self.tick()
        self.assertEqual(len(self.calls), 1)
        self.pending=False; self.tick()
        self.assertEqual(len(self.calls), 2)

    def test_invalid_missing_unavailable_stay_closed(self):
        self.tick()
        self.odom(frame='map'); self.tick()
        self.odom(norm_w=0); self.tick()
        self.odom(); self.ready=False; self.tick()
        self.assertEqual(len(self.calls), 0)

    def test_stale_pose_cannot_trigger_service(self):
        self.odom(); self.tick()
        self.now=2; self.odom(.02)
        self.now=4; self.tick()
        self.assertEqual(len(self.calls), 0)


class UpdateGateTests(unittest.TestCase):
    def test_stationary_never_forces_repeated_evidence(self):
        gate = AmclUpdateGate()
        self.assertEqual(sum(gate.allow(1, 2, 0, t, t) for t in range(600)), 0)

    def test_translation_and_turn_independent(self):
        gate = AmclUpdateGate()
        self.assertFalse(gate.allow(0, 0, 0, 1, 1))
        self.assertTrue(gate.allow(.01, 0, 0, 2, 2))
        self.assertTrue(gate.allow(.01, 0, .02, 3, 3))
        self.assertFalse(gate.allow(.01, 0, .02, 4, 4))

    def test_small_progress_accumulates(self):
        gate = AmclUpdateGate()
        self.assertFalse(gate.allow(0, 0, 0, 1, 1))
        self.assertFalse(gate.allow(.002, 0, 0, 2, 2))
        self.assertTrue(gate.allow(.006, 0, 0, 3, 3))

    def test_invalid_stale_future_do_not_consume_progress(self):
        gate = AmclUpdateGate()
        gate.allow(0, 0, 0, 1, 1)
        self.assertFalse(gate.allow(1, 0, 0, 2, 3))
        self.assertFalse(gate.allow(1, 0, 0, 4, 3))
        self.assertFalse(gate.allow(math.nan, 0, 0, 3, 3))
        self.assertTrue(gate.allow(1, 0, 0, 3, 3))

    def test_duplicate_and_clock_reset(self):
        gate = AmclUpdateGate()
        gate.allow(0, 0, 0, 10, 10)
        self.assertFalse(gate.allow(1, 0, 0, 10, 10))
        self.assertFalse(gate.allow(1, 0, 0, 1, 1))
        self.assertFalse(gate.allow(1, 0, 0, 2, 2))
        self.assertTrue(gate.allow(1.1, 0, 0, 3, 3))

    def test_yaw_wrap_is_not_full_turn(self):
        gate = AmclUpdateGate()
        gate.allow(0, 0, math.pi-.001, 1, 1)
        self.assertFalse(gate.allow(0, 0, -math.pi+.001, 2, 2))

    def test_invalid_configuration(self):
        for value in (0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                AmclUpdateGate(translation_m=value)


if __name__ == '__main__':
    unittest.main()
