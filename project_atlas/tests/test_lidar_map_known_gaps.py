"""2026-11-16 map-known LiDAR gaps (pure; no ROS)."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import atlas_lidar_availability as ala  # noqa: E402


def room(wall_x=2.0, w=100, h=100, res=0.05, unknown_box=None):
    """Free square map (origin -2.5,-2.5) with a vertical wall at x = wall_x."""
    data = [0] * (w * h)
    for gy in range(h):
        for gx in range(w):
            x = -2.5 + (gx + 0.5) * res; y = -2.5 + (gy + 0.5) * res
            if abs(x - wall_x) < res or gx in (0, w - 1) or gy in (0, h - 1):
                data[gy * w + gx] = 100
            if unknown_box and unknown_box[0] <= x <= unknown_box[1] and unknown_box[2] <= y <= unknown_box[3]:
                data[gy * w + gx] = -1
    return ala.OccGrid(w, h, res, -2.5, -2.5, data)


def scan(blank_deg=()):
    """Robot-frame full scan at 3 m with the given robot-frame degree rays blanked (inf)."""
    ranges = []
    for k in range(360):
        robot_deg = (k + 0.5 - 180 + 180) % 360         # angle_min -pi, yaw 180 -> robot = laser + 180
        ranges.append(float('inf') if int(robot_deg) in blank_deg else 3.0)
    return NS(header=NS(frame_id='laser_frame', stamp=NS(sec=100, nanosec=0)), range_min=.15, range_max=12.,
              angle_min=-math.pi, angle_increment=math.pi / 180, ranges=ranges)


class MapKnownTests(unittest.TestCase):
    def test_threshold_is_owner_value(self):
        self.assertEqual(ala.MAP_GAP_MIN_M, 0.4)
        self.assertEqual(ala.map_known_bins({0}, room(wall_x=0.6), (0.0, 0.0, 0.0)), {0})   # 0.65 m from laser

    def test_far_mapped_wall_explains_bin(self):
        g = room(wall_x=2.0)
        self.assertEqual(ala.map_known_bins({0, 71}, g, (0.0, 0.0, 0.0)), {0, 71})

    def test_close_wall_does_not_explain(self):
        g = room(wall_x=0.3)
        self.assertEqual(ala.map_known_bins({0}, g, (0.0, 0.0, 0.0)), set())

    def test_unknown_cells_do_not_explain(self):
        g = room(wall_x=2.0, unknown_box=(1.0, 1.4, -0.5, 0.5))
        self.assertEqual(ala.map_known_bins({0}, g, (0.0, 0.0, 0.0)), set())

    def test_pose_yaw_is_used(self):
        g = room(wall_x=2.0)
        # facing +y (yaw 90 deg): bin 0 now looks up to the map border at y = +2.45 -> still a wall >= 1 m
        self.assertEqual(ala.map_known_bins({0}, g, (0.0, 0.0, math.pi / 2)), {0})
        # facing -x toward the left border at 2.45 m, but from x = -2.2 it is only ~0.2 m away
        self.assertEqual(ala.map_known_bins({0}, g, (-2.2, 0.0, math.pi)), set())

    def test_reason_uses_explain_for_few_bins_only(self):
        g = ala.LidarAvailability(); g.update(scan(blank_deg=set(range(0, 5))), 10.0)   # bin 0 empty
        g.update  # noqa
        base = g.reason(0.1, 0.0, 100.1, 10.1)
        self.assertIn('unobserved', base)
        self.assertIsNone(g.reason(0.1, 0.0, 100.1, 10.1, explain=lambda m: m))
        self.assertEqual(g.map_explained, 1)
        many = ala.LidarAvailability(); many.update(scan(blank_deg=set(range(0, 20)) | set(range(340, 360))), 10.0)
        self.assertIn('unobserved', many.reason(0.1, 0.0, 100.1, 10.1, explain=lambda m: m))   # > 3 bins

    def test_explain_errors_fail_closed(self):
        g = ala.LidarAvailability(); g.update(scan(blank_deg=set(range(0, 5))), 10.0)
        def boom(_):
            raise RuntimeError('x')
        self.assertIn('unobserved', g.reason(0.1, 0.0, 100.1, 10.1, explain=boom))
        self.assertIn('unobserved', g.reason(0.1, 0.0, 100.1, 10.1, explain=lambda m: {99}))   # foreign bins ignored

    def test_camera_obstacle_closer_than_wall_vetoes(self):
        g = room(wall_x=2.0)                                   # wall ~2.05 m from the laser at bin 0
        self.assertEqual(ala.map_known_bins({0}, g, (0.0, 0.0, 0.0), obstacles={0: 1.0}), set())
        self.assertEqual(ala.map_known_bins({0}, g, (0.0, 0.0, 0.0), obstacles={0: 2.0}), {0})   # = the wall
        self.assertEqual(ala.map_known_bins({0}, g, (0.0, 0.0, 0.0), obstacles={5: 0.5}), {0})   # other bin

    def test_coverage_obstacles_per_lidar_bin_and_freshness(self):
        n = 120; amin = math.radians(-30.0); inc = math.radians(0.5)
        ranges = [float('inf')] * n; inten = [0.0] * n
        k = int(round((math.radians(1.0) - amin) / inc))          # obstacle 1.2 m straight ahead (base_link)
        ranges[k] = 1.2; inten[k] = 1.0
        msg = NS(header=NS(frame_id='base_link'), angle_min=amin, angle_increment=inc, ranges=ranges, intensities=inten)
        g = ala.LidarAvailability(); g.update_coverage(msg, 10.0)
        obs = g.obstacles(10.1)
        self.assertIn(0, obs); self.assertAlmostEqual(obs[0], 1.25, delta=0.01)    # + 0.05 m laser offset
        self.assertEqual(g.obstacles(10.0 + ala.COVER_TIMEOUT_S + 0.1), {})          # stale camera: no veto data
        g.update_coverage(NS(header=NS(frame_id='camera')), 11.0)                    # bad message clears it
        self.assertEqual(g.obstacles(11.0), {})

    def test_sweep_extent_side_vs_front(self):
        e = ala.sweep_extent(0.15, 0.0)
        front, side = ala.required_wall_distance(0, e), ala.required_wall_distance(18, e)   # 0 deg, 90 deg left
        self.assertGreater(front, 0.5)                       # driving toward it: bumper + travel + margin
        self.assertLess(side, 0.3)                           # beside the body: body edge + margin
        self.assertEqual(ala.SWEEP_EXTENT_MARGIN_M, 0.05)
        self.assertGreaterEqual(ala.required_wall_distance(36, ala.sweep_extent(0.0, 0.0)), ala.MAP_GAP_FLOOR_M)

    def test_turn_swings_rear_out(self):
        straight = ala.required_wall_distance(27, ala.sweep_extent(0.15, 0.0))      # 135 deg (rear-left)
        right_turn = ala.required_wall_distance(27, ala.sweep_extent(0.15, -0.5))
        self.assertGreaterEqual(right_turn, straight)

    def test_extent_used_by_map_known_bins(self):
        g = room(wall_x=0.45)                                 # wall ~0.5 m ahead of the laser
        self.assertEqual(ala.map_known_bins({0}, g, (0.0, 0.0, 0.0)), {0})            # fixed 0.4 m: explained
        self.assertEqual(ala.map_known_bins({0}, g, (0.0, 0.0, 0.0), extent=ala.sweep_extent(0.15, 0.0)), set())

    def test_bad_grid_rejected(self):
        with self.assertRaises(ValueError):
            ala.OccGrid(0, 1, 0.05, 0, 0, [])



class MuxExplainerTests(unittest.TestCase):
    """guard_map_explainer extracted from the real mux source: only a fresh, confident AMCL pose may explain gaps."""
    @staticmethod
    def explainer():
        import ast
        tree = ast.parse((Path(__file__).parents[1] / 'scripts' / 'atlas_cmd_vel_mux.py').read_text())
        fn = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'guard_map_explainer'][0]
        scope = {'lidar_avail': ala}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'mux', 'exec'), scope)
        return scope['guard_map_explainer']

    def mux(self, **kw):
        base = dict(map_grid=room(2.0), localization_pose=(0.0, 0.0, 0.0), localization_rx=10.0,
                    localization_xy_std_m=0.05, localization_yaw_std_deg=3.0)
        base.update(kw)
        return NS(**base)

    def test_confident_pose_explains(self):
        fn = self.explainer()(self.mux(), 11.0)
        self.assertEqual(fn({0}), {0})

    def test_camera_obstacle_reaches_explainer(self):
        guard = NS(obstacles=lambda now: {0: 1.0})
        fn = self.explainer()(self.mux(lidar_availability=guard), 11.0)
        self.assertEqual(fn({0}), set())

    def test_gates(self):
        f = self.explainer()
        self.assertIsNone(f(self.mux(map_grid=None), 11.0))
        self.assertIsNone(f(self.mux(localization_pose=None), 11.0))
        self.assertIsNone(f(self.mux(), 10.0 + ala.MAP_POSE_MAX_AGE_S + 0.1))          # stale AMCL
        self.assertIsNone(f(self.mux(localization_xy_std_m=0.2), 11.0))               # not confident
        self.assertIsNone(f(self.mux(localization_yaw_std_deg=12.0), 11.0))

if __name__ == '__main__':
    unittest.main()
