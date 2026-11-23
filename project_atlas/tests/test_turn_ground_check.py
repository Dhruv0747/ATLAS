"""Pure parts of tools/drive/turn_ground_check.py (Stage-2 gentle turns). No ROS. 2026-11-23."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'drive'))
import turn_ground_check as g  # noqa: E402


def arc(direction, yaw_end=25.0, seconds=3.5, v=0.10):
    out, d = [], 0.0
    n = int(seconds * 10)
    for k in range(n):
        t = k / 10
        vv = 0.0 if t < 0.4 else v
        d += vv * 0.1
        out.append({'t': t, 'v': vv, 'd': round(d, 3), 'yaw': direction * yaw_end * k / (n - 1)})
    return out


class TurnCheckTests(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(g.bounded_yaw(25.0), 25.0)
        for bad in (5.0, 40.0, 90.0):
            with self.assertRaises(ValueError):
                g.bounded_yaw(bad)

    def test_commands_stay_inside_the_mux_commission_clamp(self):
        self.assertLessEqual(g.VX, 0.12)
        self.assertLessEqual(g.WZ, 0.15)
        mux = (ROOT / 'scripts' / 'atlas_cmd_vel_mux.py').read_text(encoding='utf-8')
        self.assertIn('command.angular.z = max(-0.15, min(0.15, command.angular.z))', mux)

    def test_good_left_arc_passes(self):
        r = g.evaluate_arc(arc(+1), +1, 'YAW', icp_yaw_deg=23.0, settle_s=0.6)
        self.assertEqual(r['verdict'], 'PASS', r['checks'])
        self.assertEqual(r['direction'], 'LEFT')

    def test_wrong_turn_sign_fails(self):
        r = g.evaluate_arc(arc(-1), +1, 'YAW', settle_s=0.5)
        self.assertFalse(r['checks']['turn_sign_and_size'])
        self.assertEqual(r['verdict'], 'FAIL')

    def test_guard_stop_fails_even_if_turning(self):
        r = g.evaluate_arc(arc(+1, 12.0), +1, 'STOP_LIDAR_0.28M', settle_s=0.4)
        self.assertFalse(r['checks']['ended_by_heading_target'])

    def test_lidar_heading_disagreement_and_slow_stop_fail(self):
        r = g.evaluate_arc(arc(+1), +1, 'YAW', icp_yaw_deg=5.0, settle_s=0.6)
        self.assertFalse(r['checks']['lidar_heading_agrees'])
        r = g.evaluate_arc(arc(+1), +1, 'YAW', settle_s=None)
        self.assertFalse(r['checks']['still_within_1.5s'])

    def test_icp_missing_is_not_required(self):
        r = g.evaluate_arc(arc(+1), +1, 'YAW', icp_yaw_deg=None, settle_s=0.6)
        self.assertNotIn('lidar_heading_agrees', r['checks'])
        self.assertEqual(r['verdict'], 'PASS')

    def test_sequence(self):
        left = g.evaluate_arc(arc(+1), +1, 'YAW', settle_s=0.5)
        right = g.evaluate_arc(arc(-1), -1, 'YAW', settle_s=0.5)
        r = g.evaluate([left, right])
        self.assertEqual(r['verdict'], 'PASS', r['failed'])
        self.assertIn('left +25', r['detail']); self.assertIn('right -25', r['detail'])
        only_left = g.evaluate([left])
        self.assertEqual(only_left['verdict'], 'FAIL')
        self.assertIn('right_arc', only_left['failed'])
        bad_right = g.evaluate_arc(arc(-1, 12.0), -1, 'STOP_SCAN_STALE', settle_s=0.5)
        r = g.evaluate([left, bad_right])
        self.assertIn('right:ended_by_heading_target', r['failed'])

    def test_swept_clearance_looks_only_at_the_turning_side(self):
        bumper = g.FRONT_BUMPER_X_M
        wall_left = [(bumper + 0.5, 0.45)]          # 0.45 m to the left, 0.5 m ahead of the bumper
        self.assertAlmostEqual(g.swept_clearance(wall_left, +1), 0.5)
        self.assertEqual(g.swept_clearance(wall_left, -1), float('inf'))
        self.assertEqual(g.swept_clearance([(bumper + 0.3, -1.0)], +1), float('inf'))   # far to the right
        self.assertEqual(g.swept_clearance([(-0.4, 0.0)], +1), float('inf'))            # behind
        self.assertAlmostEqual(g.swept_clearance([(bumper + 0.2, 0.0)], -1), 0.2)       # straight ahead counts

    def test_tool_records_on_the_master_plan_and_stops_after_a_guard(self):
        src = (ROOT / 'tools' / 'drive' / 'turn_ground_check.py').read_text(encoding='utf-8')
        self.assertIn('atlas_master_plan.record_stage2(res, out.name)', src)
        self.assertIn("if arc.get('aborted') or arc['end_reason'] != 'YAW':", src)
        tree = ast.parse(src)
        self.assertTrue(any(isinstance(n, ast.Constant) and n.value == '/cmd_vel_commission' for n in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
