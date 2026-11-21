"""Guided mapping assistant: per-area map quality (pure; no ROS). 2026-11-16."""
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import atlas_map_quality_core as mq  # noqa: E402

RES = 0.05
LASER = (-0.05, 0.0, math.pi)          # ATLAS laser_frame in base_link (mux: LASER_X -0.05, yaw 180)


def room(w_m=4.0, h_m=3.0, door=None, unknown_outside=True):
    """Free rectangle [0,w]x[0,h] with walls; origin (-0.5,-0.5); unknown outside. door = (y0, y1) gap in the
    right wall (x = w) opening into unknown."""
    W, H = int((w_m + 1.0) / RES), int((h_m + 1.0) / RES)
    data = [-1 if unknown_outside else 0] * (W * H)
    for gy in range(H):
        for gx in range(W):
            x, y = -0.5 + (gx + 0.5) * RES, -0.5 + (gy + 0.5) * RES
            inside = -0.05 <= x <= w_m + 0.05 and -0.05 <= y <= h_m + 0.05
            if not inside:
                continue
            wall = x < 0.05 or x > w_m - 0.05 or y < 0.05 or y > h_m - 0.05
            if wall and door and x > w_m - 0.05 and door[0] <= y <= door[1]:
                data[gy * W + gx] = 0
                continue
            data[gy * W + gx] = 100 if wall else 0
    return mq.Grid(W, H, RES, -0.5, -0.5, data)


def simulate(grid, pose, n=360, max_r=8.0):
    """LiDAR ranges (angle_min -pi, 1 deg) by stepping each ray until an occupied cell."""
    x, y, yaw = pose
    lx = x + LASER[0] * math.cos(yaw)
    ly = y + LASER[0] * math.sin(yaw)
    ranges = []
    for i in range(n):
        a = yaw + LASER[2] - math.pi + i * 2 * math.pi / n
        r = 0.05
        hit = float('inf')
        while r < max_r:
            c = grid.cell(lx + r * math.cos(a), ly + r * math.sin(a))
            if c is None or grid.value(*c) == -1:
                break
            if grid.value(*c) >= 65:
                hit = r
                break
            r += 0.02
        ranges.append(hit)
    return ranges


def feed(tracker, grid, pose, t, truth=None, force=False):
    ranges = simulate(grid, truth or pose)
    return tracker.add_scan(t, pose, LASER, -math.pi, 2 * math.pi / 360, ranges, 0.15, 12.0, grid, force=force)


LOOP = [(0.6, 0.6, 0.0), (1.5, 0.6, 0.0), (2.5, 0.6, 0.0), (3.3, 0.8, math.pi / 2), (3.3, 1.8, math.pi / 2),
        (3.2, 2.4, math.pi), (2.2, 2.4, math.pi), (1.2, 2.4, math.pi), (0.6, 2.2, -math.pi / 2),
        (0.6, 1.4, -math.pi / 2), (0.65, 0.65, 0.0)]


class QualityTests(unittest.TestCase):
    def drive(self, grid, poses=LOOP, t0=0.0):
        tr = mq.QualityTracker()
        for i, p in enumerate(poses):
            feed(tr, grid, p, t0 + i)
        return tr

    def test_full_loop_is_ready_for_review(self):
        g = room()
        tr = self.drive(g)
        s = tr.summary(g, robot=LOOP[-1])
        self.assertEqual(s['weak'], 0, s['tiles'])
        self.assertTrue(s['ready'], s['verdict_text'])
        self.assertIn('Map ready for review: stop the session when parked', s['prompts'])
        self.assertGreater(s['counts']['ACCEPTED'], 10)

    def test_not_ready_until_back_at_start(self):
        g = room()
        tr = self.drive(g, LOOP[:6])
        s = tr.summary(g, robot=LOOP[5])
        self.assertFalse(s['ready'])
        self.assertIn('drive back to the start', s['verdict_text'])

    def test_single_viewpoint_is_weak(self):
        g = room()
        tr = mq.QualityTracker()
        feed(tr, g, (0.6, 0.6, 0.0), 0.0)
        verdict, reason, m = tr.tile_verdict(g, tr.tile_of(3.9, 2.9))     # far corner seen once
        self.assertEqual(verdict, 'WEAK')
        self.assertIn('too few positions', reason)

    def test_wrong_pose_gives_weak_scan_match(self):
        g = room()
        tr = mq.QualityTracker()
        fit_ok = feed(tr, g, (1.5, 1.5, 0.0), 0.0)
        fit_bad = feed(tr, g, (1.5, 1.5, 0.0), 1.0, truth=(1.9, 1.2, 0.15), force=True)
        self.assertGreater(fit_ok, 0.95)
        self.assertLess(fit_bad, 0.7)
        tr2 = mq.QualityTracker()
        for i in range(4):
            feed(tr2, g, (1.5 + 0.2 * i, 1.5, 0.0), i, truth=(1.9 + 0.2 * i, 1.2, 0.15))
        verdict, reason, _ = tr2.tile_verdict(g, tr2.tile_of(1.9, 1.5))
        self.assertEqual(verdict, 'WEAK')
        self.assertIn('scan match weak', reason)

    def test_pose_jump_needs_recheck(self):
        g = room()
        tr = self.drive(g)
        key = tr.tile_of(2.2, 2.4)
        self.assertEqual(tr.tile_verdict(g, key)[0], 'ACCEPTED')
        self.assertTrue(tr.add_jump(100.0, (2.2, 2.4), 1.3, 13.0))
        verdict, reason, m = tr.tile_verdict(g, key)
        self.assertEqual(verdict, 'WEAK')
        self.assertEqual(reason, 'position jumped 1.3 m here')
        s = tr.summary(g, robot=(2.0, 2.3, 0.0))
        self.assertIn('Position jumped here: stop, wait for GO, then continue slowly', s['prompts'])
        self.assertFalse(s['ready'])
        for i in range(3):                                             # drive here again: 3 good samples
            feed(tr, g, (2.0 + 0.15 * i, 2.35, math.pi), 101.0 + i)
        self.assertEqual(tr.tile_verdict(g, key)[0], 'ACCEPTED')
        self.assertFalse(tr.add_jump(110.0, (2.2, 2.4), 0.1, 1.0))    # small correction: ignored

    def test_frontier_reported_and_blocks_ready(self):
        g = room(door=(1.0, 1.8))
        tr = self.drive(g)
        fronts = tr.frontiers(g)
        self.assertTrue(fronts)
        self.assertAlmostEqual(fronts[0]['length_m'], 0.8, delta=0.15)
        self.assertAlmostEqual(fronts[0]['x'], 4.0, delta=0.15)
        s = tr.summary(g, robot=(3.3, 1.4, 0.0))
        self.assertTrue(any(p.startswith('Unexplored opening') for p in s['prompts']), s['prompts'])
        self.assertFalse(tr.summary(g, robot=LOOP[-1])['ready'])

    def test_decimation(self):
        g = room()
        tr = mq.QualityTracker()
        self.assertIsNotNone(feed(tr, g, (1.0, 1.0, 0.0), 0.0))
        self.assertIsNone(feed(tr, g, (1.0, 1.0, 0.0), 2.0))           # did not move
        self.assertIsNone(feed(tr, g, (1.5, 1.0, 0.0), 0.2))           # too soon
        self.assertIsNotNone(feed(tr, g, (1.5, 1.0, 0.0), 1.0))
        self.assertEqual(tr.samples, 2)

    def test_pose_jumps_from_map_odom(self):
        series = [(0, 0.0, 0.0, 0.0), (1, 0.02, 0.0, 0.0), (2, 1.3, 0.2, math.radians(13)), (3, 1.31, 0.2, 0.22)]
        j = mq.pose_jumps(series)
        self.assertEqual(len(j), 1)
        self.assertEqual(j[0][0], 2)
        self.assertAlmostEqual(j[0][1], math.hypot(1.28, 0.2), places=3)

    def test_text_is_english(self):
        g = room(door=(1.0, 1.8))
        tr = self.drive(g)
        tr.add_jump(50.0, (1.5, 0.6), 0.8, 9.0)
        s = tr.summary(g, robot=(1.4, 0.7, 0.0))
        texts = [s['verdict_text']] + s['prompts'] + [t[3] for t in s['tiles']]
        for text in texts:
            self.assertFalse(any('ऀ' <= ch <= 'ॿ' for ch in text), text)

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            mq.Grid(2, 2, 0.05, 0, 0, [0, 0, 0])
        tr = mq.QualityTracker()
        g = room()
        self.assertIsNone(tr.add_scan(0, (float('nan'), 0, 0), LASER, -math.pi, 0.01, [1.0] * 10, 0.1, 5, g))
        self.assertEqual(tr.summary(g)['verdict_text'], 'Waiting for the first scan')


if __name__ == '__main__':
    unittest.main()
