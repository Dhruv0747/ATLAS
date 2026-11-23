"""Pure parts of tools/drive/turn_ground_check.py (Stage-2 gentle turns). No ROS. 2026-11-23."""
import ast
import math
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

    @staticmethod
    def world_to_base(points, yaw_deg, direction):
        """Rover pose after turning yaw_deg on the commanded arc; return the world points in base_link."""
        th = math.radians(yaw_deg) * direction
        R = g.RADIUS_M
        px, py = R * math.sin(abs(th)), direction * R * (1 - math.cos(th))
        out = []
        for x, y in points:
            dx, dy = x - px, y - py
            out.append((dx * math.cos(th) + dy * math.sin(th), -dx * math.sin(th) + dy * math.cos(th)))
        return out

    def test_recorded_side_wall_case_does_not_stop_the_arc(self):
        # 2026-11-23 run 1: wall ~0.6 m to the side of the turn. Sweep the whole 25 deg turn both ways.
        for d in (+1, -1):
            wall = [(x / 100, d * 0.60) for x in range(-50, 300, 2)]
            for k in range(0, 26):
                pts = self.world_to_base(wall, k, d)
                self.assertGreaterEqual(g.swept_clearance(pts, d, 25 - k), g.STOP_CLEAR_M, (d, k))

    def test_obstacle_on_the_curve_is_seen_and_distance_shrinks(self):
        for d in (+1, -1):
            # a post exactly on the arc 0.45 m (arc length) ahead of the bumper
            phi = (g.FRONT_BUMPER_X_M + 0.45) / g.RADIUS_M
            post = [(g.RADIUS_M * math.sin(phi), d * g.RADIUS_M * (1 - math.cos(phi)))]
            c0 = g.swept_clearance(post, d, 25)
            self.assertAlmostEqual(c0, 0.45, places=2)
            c1 = g.swept_clearance(self.world_to_base(post, 15, d), d, 10)   # 0.45 - 0.175 m travelled
            self.assertLess(c1, c0)
            self.assertLess(c1, g.STOP_CLEAR_M)          # would stop the arc

    def test_straight_ahead_and_inner_side_count_but_far_and_behind_do_not(self):
        b = g.FRONT_BUMPER_X_M
        for d in (+1, -1):
            self.assertLess(g.swept_clearance([(b + 0.2, 0.0)], d, 25), g.STOP_CLEAR_M)   # in front of the bumper
            self.assertEqual(g.swept_clearance([(-0.4, 0.0)], d, 25), float('inf'))       # behind
            self.assertEqual(g.swept_clearance([(b + 0.3, -d * 1.0)], d, 25), float('inf'))  # far on the other side
            self.assertEqual(g.swept_clearance([(3.0, 0.0)], d, 25), float('inf'))        # beyond the 25 deg path

    def test_tool_records_on_the_master_plan_and_stops_after_a_guard(self):
        src = (ROOT / 'tools' / 'drive' / 'turn_ground_check.py').read_text(encoding='utf-8')
        self.assertIn('atlas_master_plan.record_stage2(res, out.name)', src)
        self.assertIn("if arc.get('aborted') or arc['end_reason'] != 'YAW':", src)
        tree = ast.parse(src)
        self.assertTrue(any(isinstance(n, ast.Constant) and n.value == '/cmd_vel_commission' for n in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
