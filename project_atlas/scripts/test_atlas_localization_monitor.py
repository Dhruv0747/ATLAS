"""Continuous localization check: pure tests (no ROS, no motion).

Numbers come from the 2026-10-10 moving failure and the Oct 9 recordings.
"""
import ast
import json
import math
from pathlib import Path
import tempfile
import time
import unittest

import atlas_localization_verify_core as core
from atlas_localization_monitor import MonitorLogic, relocalize_mode


def verdict(x, y, yaw_deg, fit=1.0, margin=0.13, state='VERIFIED'):
    return core.Verdict(state, (x, y, math.radians(yaw_deg)) if state == 'VERIFIED' else None,
                        'test', fit, margin)


class AssessTests(unittest.TestCase):
    def test_todays_failure_is_lost_with_recovery_pose(self):
        # AMCL (4.131, -0.771, 159.7 deg) fit 0.80; LiDAR unique Dhruv Room (0.175, -1.395, 76 deg)
        r = core.assess_tracking((4.131, -0.771, math.radians(159.7)), 0.80, verdict(0.175, -1.395, 76.0))
        self.assertEqual(r['state'], 'LOST')
        self.assertAlmostEqual(r['recovery_pose']['x'], 0.175)
        self.assertGreater(r['distance_m'], 3.9)

    def test_confirmed_pose_is_verified(self):
        r = core.assess_tracking((6.716, -2.371, math.radians(-114.9)), 1.0, verdict(6.735, -2.335, -114.0))
        self.assertEqual(r['state'], 'VERIFIED')
        self.assertIsNone(r['recovery_pose'])

    def test_half_metre_offset_is_not_verified(self):
        # outbound 1636: AMCL 0.41-0.57 m ahead of the scan-best pose
        r = core.assess_tracking((0.354, -1.023, math.radians(75.8)), 0.604, verdict(0.135, -1.595, 75.0))
        self.assertEqual(r['state'], 'LOST')
        r = core.assess_tracking((0.354, -1.023, math.radians(75.8)), 0.604, verdict(0.30, -1.36, 75.0))
        self.assertEqual(r['state'], 'LOST')            # close but the pose itself fits badly

    def test_heading_off_is_degraded(self):
        r = core.assess_tracking((0.207, -1.476, math.radians(81.0)), 0.811, verdict(0.235, -1.635, 72.0))
        self.assertEqual(r['state'], 'DEGRADED')

    def test_ambiguous_search_never_verifies(self):
        amb = verdict(0, 0, 0, state='UNKNOWN')
        self.assertEqual(core.assess_tracking((0, 0, 0), 0.99, amb)['state'], 'DEGRADED')
        self.assertEqual(core.assess_tracking((0, 0, 0), 0.50, amb)['state'], 'LOST')
        self.assertIsNone(core.assess_tracking((0, 0, 0), 0.50, amb)['recovery_pose'])


class MonitorLogicTests(unittest.TestCase):
    LOST = {'state': 'LOST', 'recovery_pose': {'x': 0.175, 'y': -1.395, 'yaw_deg': 76.0}}

    def parked(self, logic, t0=0.0):
        logic.on_motion(t0, False)
        self.assertFalse(logic.check_due(t0 + 1.0))       # settle first
        self.assertTrue(logic.check_due(t0 + 2.5))

    def test_moving_is_never_verified(self):
        logic = MonitorLogic()
        self.parked(logic)
        logic.on_result(3.0, {'state': 'VERIFIED'}, 'suggest')
        logic.on_motion(4.0, True)
        self.assertEqual(logic.state['state'], 'MOVING_UNVERIFIED')
        self.assertFalse(logic.check_due(4.5))

    def test_suggest_mode_never_reseeds(self):
        logic = MonitorLogic()
        self.parked(logic)
        for t in (3, 40, 80):
            self.assertIsNone(logic.on_result(t, dict(self.LOST), 'suggest'))
        self.assertFalse(logic.state['navigation_authorized'])

    def test_auto_needs_two_agreeing_parked_checks(self):
        logic = MonitorLogic()
        self.parked(logic)
        self.assertIsNone(logic.on_result(3, dict(self.LOST), 'auto'))
        other = {'state': 'LOST', 'recovery_pose': {'x': 3.8, 'y': -0.6, 'yaw_deg': 175.0}}
        self.assertIsNone(logic.on_result(40, other, 'auto'))            # disagrees: no reseed
        reseed = logic.on_result(80, {'state': 'LOST', 'recovery_pose': {'x': 3.85, 'y': -0.62, 'yaw_deg': 176.0}}, 'auto')
        self.assertEqual(reseed['x'], 3.85)
        self.assertTrue(logic.awaiting_confirmation)
        self.assertTrue(logic.check_due(81))                              # re-check right away
        logic.on_result(82, {'state': 'VERIFIED'}, 'auto')
        self.assertFalse(logic.awaiting_confirmation)

    def test_motion_resets_the_lost_streak(self):
        logic = MonitorLogic()
        self.parked(logic)
        logic.on_result(3, dict(self.LOST), 'auto')
        logic.on_motion(5, True)
        self.parked(logic, 10)
        self.assertIsNone(logic.on_result(13, dict(self.LOST), 'auto'))  # first after the move

    def test_mode_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'mode'
            self.assertEqual(relocalize_mode(p), 'suggest')
            p.write_text('auto\n')
            self.assertEqual(relocalize_mode(p), 'auto')
            p.write_text('yes please')
            self.assertEqual(relocalize_mode(p), 'suggest')

    def test_node_never_publishes_velocity(self):
        src = Path(__file__).with_name('atlas_localization_monitor.py').read_text()
        import re
        self.assertNotIn('Twist', src)
        self.assertEqual(re.findall(r'create_publisher\((\w+)', src), ['String'])


class StatusReaderTests(unittest.TestCase):
    def test_reader(self):
        source = Path(__file__).with_name('atlas_status_web.py').read_text()
        fn = next(n for n in ast.parse(source).body
                  if isinstance(n, ast.FunctionDef) and n.name == 'read_localization_check')
        scope = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'web', 'exec'),
             {'Path': Path, 'json': json, 'time': time, 'LOCALIZATION_CHECK_FILE': Path('/nonexistent')}, scope)
        read = scope['read_localization_check']
        self.assertIsNone(read(100.0))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'c.json'
            p.write_text(json.dumps({'state': 'LOST', 'written_unix': 99.0, 'checked_unix': 70.0,
                                     'recovery_pose': {'x': 1}}))
            out = read(100.0, p)
            self.assertEqual(out['value']['state'], 'LOST')
            self.assertEqual(out['value']['check_age_s'], 30.0)
            self.assertEqual(out['age'], 1.0)


if __name__ == '__main__':
    unittest.main()
