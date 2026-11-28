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

    # ---- step 4 part B (workload timing) ----
    OFFSETS = {'imu': 0.0, 'ekf': 0.0, 'tf_odom_base': 0.2, 'tf_map_odom': 1.0}

    @staticmethod
    def streams(seconds=10.0, imu_age=0.005, ekf_age=0.07, tf_raw=-0.19, map_raw=-0.85, gap_at=None):
        def rows(hz, age):
            out = [(k / hz, age) for k in range(int(seconds * hz))]
            return [(t + (0.6 if gap_at is not None and t >= gap_at else 0.0), a) for t, a in out]
        return {'imu': rows(10, imu_age), 'ekf': rows(10, ekf_age), 'tf_odom_base': rows(10, tf_raw),
                'tf_map_odom': rows(7.4, map_raw)}

    def test_workload_like_the_live_rover_passes(self):     # 2026-11-23 15 s probe under the full stack
        w = g.evaluate_workload(self.streams(), 10.0, self.OFFSETS, [(24.0, 25.9), (-26.0, -26.7)], [], 13.4)
        self.assertEqual(w['failed'], [], w)
        self.assertAlmostEqual(w['measured']['tf_odom_base']['age_p95_s'], 0.01, places=2)

    def test_workload_failures(self):
        w = g.evaluate_workload(self.streams(ekf_age=0.4), 10.0, self.OFFSETS, [(25, 25), (-25, -25)], [])
        self.assertIn('ekf_age', w['failed'])
        w = g.evaluate_workload(self.streams(gap_at=5.0), 10.0, self.OFFSETS, [(25, 25), (-25, -25)], [])
        self.assertIn('imu_rate', w['failed'])
        # an unexplained future stamp (offset not configured) fails the age check
        w = g.evaluate_workload(self.streams(), 10.0, dict(self.OFFSETS, tf_odom_base=0.0), [(25, 25)], [])
        self.assertIn('tf_odom_base_age', w['failed'])
        w = g.evaluate_workload(self.streams(), 10.0, self.OFFSETS, [(10.0, 25.0)], ['atlas-camera'])
        self.assertIn('ekf_heading_agrees', w['failed']); self.assertIn('full_workload_running', w['failed'])
        self.assertIn('ekf_heading_agrees', g.evaluate_workload(self.streams(), 10.0, self.OFFSETS, [], [])['failed'])

    def test_pause_between_arcs_is_not_a_gap(self):
        # 2026-11-23 part B runs 1-2: every stream showed the same ~1.2 s "gap" = the pause between the two arcs
        def two_arcs(hz, age):
            return [(k / hz, age, 1) for k in range(int(4 * hz))] + [(5.2 + k / hz, age, 2) for k in range(int(4 * hz))]
        st = {'imu': two_arcs(10, 0.01), 'ekf': two_arcs(10, 0.05), 'tf_odom_base': two_arcs(10, -0.19),
              'tf_map_odom': two_arcs(8, -0.85)}
        w = g.evaluate_workload(st, 8.0, self.OFFSETS, [(25, 25), (-25, -25)], [])
        self.assertEqual(w['failed'], [], w)
        self.assertLess(w['measured']['imu']['max_gap_s'], 0.2)
        # a real gap inside one arc is still caught
        st['ekf'] = [r for r in st['ekf'] if not (r[2] == 2 and 6.0 < r[0] < 6.6)]
        self.assertIn('ekf_rate', g.evaluate_workload(st, 8.0, self.OFFSETS, [(25, 25), (-25, -25)], [])['failed'])

    def test_timing_starts_after_warmup_and_stops_with_the_drive(self):
        src = (ROOT / 'tools' / 'drive' / 'turn_ground_check.py').read_text(encoding='utf-8')
        self.assertIn('if t_on is None and t >= TIMING_WARMUP_S:', src)
        self.assertLess(src.index('n.timing_on = False; n.active_s'), src.index('n.call(n.disarm_c, 0.5)'))

    def test_map_odom_limit_is_back_to_0_5(self):
        self.assertEqual(g.AGE_P95_MAX_S['tf_map_odom'], 0.50)
        # PASS run 3 (0.256 s real age) passes; runs 1-2 values (0.755 s) fail
        ok = g.evaluate_workload(self.streams(map_raw=-0.744), 10.0, self.OFFSETS, [(25, 25), (-25, -25)], [])
        self.assertNotIn('tf_map_odom_age', ok['failed'])
        bad = g.evaluate_workload(self.streams(map_raw=-0.245), 10.0, self.OFFSETS, [(25, 25), (-25, -25)], [])
        self.assertIn('tf_map_odom_age', bad['failed'])

    def test_part_b_needs_turns_and_timing(self):
        left = g.evaluate_arc(arc(+1), +1, 'YAW', settle_s=0.5)
        right = g.evaluate_arc(arc(-1), -1, 'YAW', settle_s=0.5)
        ok_w = g.evaluate_workload(self.streams(), 10.0, self.OFFSETS, [(25, 25), (-25, -25)], [])
        self.assertEqual(g.combine_part_b(g.evaluate([left, right]), ok_w)['verdict'], 'PASS')
        bad_w = g.evaluate_workload(self.streams(ekf_age=0.4), 10.0, self.OFFSETS, [(25, 25), (-25, -25)], [])
        r = g.combine_part_b(g.evaluate([left, right]), bad_w)
        self.assertEqual(r['verdict'], 'FAIL'); self.assertIn('timing:ekf_age', r['failed'])
        self.assertEqual(g.combine_part_b(g.evaluate([left]), ok_w)['verdict'], 'FAIL')

    def test_configured_offsets_read_from_repo_config(self):
        off = g.configured_offsets(ROOT)
        self.assertEqual(off['tf_odom_base'], 0.2)        # atlas_ekf.yaml transform_time_offset
        self.assertEqual(off['tf_map_odom'], 1.0)         # nav2_params.yaml amcl transform_tolerance

    def test_workload_mode_records_step4b_not_stage2(self):
        src = (ROOT / 'tools' / 'drive' / 'turn_ground_check.py').read_text(encoding='utf-8')
        self.assertIn('atlas_master_plan.record_stage4b(res, out.name)', src)
        self.assertIn("'imu_workload_check_'", src)

    def test_tool_records_on_the_master_plan_and_stops_after_a_guard(self):
        src = (ROOT / 'tools' / 'drive' / 'turn_ground_check.py').read_text(encoding='utf-8')
        self.assertIn('atlas_master_plan.record_stage2(res, out.name)', src)
        self.assertIn("if arc.get('aborted') or arc['end_reason'] != 'YAW':", src)
        tree = ast.parse(src)
        self.assertTrue(any(isinstance(n, ast.Constant) and n.value == '/cmd_vel_commission' for n in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main()
