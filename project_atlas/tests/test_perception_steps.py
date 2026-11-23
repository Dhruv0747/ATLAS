"""Master-plan steps 8 (YOLO benchmark) and 9 (advisory semantic perception): pure decisions. 2026-11-23."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'perception'))
import yolo_benchmark as yb  # noqa: E402
import semantic_advisory_check as sa  # noqa: E402


def samples(n, cpu=60.0, ram=66.0, temp=64.0, gpu=40.0):
    return [{'cpu_pct': cpu, 'ram_pct': ram, 'temp_c': temp, 'gpu_pct': gpu} for _ in range(n)]


class YoloBenchTests(unittest.TestCase):
    def test_pass(self):
        r = yb.evaluate(True, True, [30.0] * 190 + [60.0] * 10, 20.0, samples(5, cpu=55), samples(20, cpu=62), None, [])
        self.assertEqual(r['verdict'], 'PASS', r)
        self.assertEqual(r['measured']['latency_ms_p95'], 30.0)
        self.assertEqual(r['measured']['rate_hz'], 10.0)

    def test_hot_or_cpu_stop_is_not_advised(self):
        r = yb.evaluate(True, True, [30.0] * 120, 12.0, samples(5), samples(12, temp=70.5), 'TEMP', [])
        self.assertEqual(r['verdict'], 'NOT ADVISED')
        self.assertIn('temp_limit_held', r['blockers'])
        r = yb.evaluate(True, True, [30.0] * 60, 6.0, samples(5), samples(6, cpu=80), 'CPU', [])
        self.assertEqual(r['verdict'], 'NOT ADVISED')
        self.assertIn('cpu_limit_held', r['blockers'])

    def test_slow_or_no_nav_stack_is_not_advised(self):
        r = yb.evaluate(True, True, [150.0] * 100, 20.0, samples(5), samples(20), None, [])
        self.assertEqual(r['verdict'], 'NOT ADVISED')
        self.assertIn('latency_p95_ok', r['blockers'])
        self.assertIn('rate_ok', r['blockers'])
        r = yb.evaluate(True, True, [30.0] * 200, 20.0, samples(5), samples(20), None, ['atlas-nav2'])
        self.assertIn('under_nav_stack', r['blockers'])

    def test_fail(self):
        self.assertEqual(yb.evaluate(False, False, [], 0.0, [], [], None, [])['verdict'], 'FAIL')
        self.assertEqual(yb.evaluate(True, False, [], 0.0, samples(5), [], None, [])['failed'],
                         ['engine_loaded', 'inference_ran'])

    def test_limits(self):
        self.assertEqual(yb.over_limit({'cpu_pct': 80}, 0), (None, 1))
        self.assertEqual(yb.over_limit({'cpu_pct': 80}, 2), ('CPU', 3))
        self.assertEqual(yb.over_limit({'cpu_pct': 60}, 2), (None, 0))
        self.assertEqual(yb.over_limit({'ram_pct': 80.0}, 0)[0], 'RAM')
        self.assertEqual(yb.over_limit({'temp_c': 70.0}, 0)[0], 'TEMP')


ROBOT = {'x': 1.0, 'y': 2.0, 'yaw': math.pi / 2}       # facing map +y


def chair_scene():
    """LiDAR points (base_link): a chair 1.5 m straight ahead, a wall at 2.8 m; YOLO box centred."""
    pts = [(1.5, y / 100.0) for y in range(-15, 16, 3)] + [(2.8, y / 10.0) for y in range(-15, 16)]
    dets = [('chair', 0.8, 560, 720), ('cup', 0.9, 100, 140), ('chair', 0.3, 900, 1000)]
    return dets, pts


class SemanticTests(unittest.TestCase):
    def test_round_confirms_chair_in_map_frame(self):
        dets, pts = chair_scene()
        objs = sa.round_objects(dets, 1280, pts, ROBOT)
        self.assertEqual(len(objs), 1)                  # cup: not a navigation class; weak chair: below 0.45
        label, conf, x, y = objs[0]
        self.assertEqual(label, 'chair')
        self.assertAlmostEqual(x, 1.0, delta=0.05)      # robot faces +y: 1.5 m ahead -> map (1.0, 3.5)
        self.assertAlmostEqual(y, 3.5, delta=0.05)

    def test_detection_without_lidar_support_is_dropped(self):
        self.assertEqual(sa.round_objects([('chair', 0.9, 0, 60)], 1280, [(1.5, 0.0)], ROBOT), [])

    def test_bearing_sign(self):
        self.assertGreater(sa.pixel_to_bearing(0, 1280), 0)          # left of the image = left (+y)
        self.assertAlmostEqual(sa.pixel_to_bearing(640, 1280), 0.0)

    def run_rounds(self, n=10, jitter=0.0, every=1):
        dets, pts = chair_scene()
        rounds = []
        for r in range(n):
            p = [(x + (jitter if r % 2 else -jitter), y) for x, y in pts]
            rounds.append(sa.round_objects(dets, 1280, p, ROBOT) if r % every == 0 else [])
        return rounds

    def test_pass_and_goal_dry_run(self):
        r = sa.evaluate(True, True, True, True, 10, self.run_rounds(), ROBOT, None)
        self.assertEqual(r['verdict'], 'PASS', r)
        g = r['measured']['stable_objects'][0]['advisory_goal']
        self.assertAlmostEqual(g['x'], 1.0, delta=0.05)
        self.assertAlmostEqual(g['y'], 2.8, delta=0.05)    # 1.5 m - 0.70 m standoff
        self.assertAlmostEqual(g['yaw_deg'], 90.0, delta=3.0)    # foreground point is not exactly the box centre
        self.assertIn('none sent', r['detail'])

    def test_unstable_or_rare_objects(self):
        r = sa.evaluate(True, True, True, True, 10, self.run_rounds(jitter=0.3), ROBOT, None)
        self.assertNotEqual(r['verdict'], 'PASS')
        r = sa.evaluate(True, True, True, True, 10, self.run_rounds(every=3), ROBOT, None)   # seen 4/10
        self.assertEqual(r['verdict'], 'NEEDS SCENE')

    def test_preconditions_fail(self):
        for i, key in enumerate(('parked', 'camera_forward', 'localised', 'lidar_live')):
            args = [True, True, True, True]
            args[i] = False
            r = sa.evaluate(*args, 10, self.run_rounds(), ROBOT, None)
            self.assertEqual(r['verdict'], 'FAIL', key)
            self.assertIn(key, r['failed'])
        r = sa.evaluate(True, True, True, True, 3, self.run_rounds(3), ROBOT, 'TEMP')
        self.assertIn('limits_held', r['failed'])
        self.assertIn('yolo_ran', r['failed'])

    def test_close_object_goal_stays(self):
        g = sa.resolve_goal(ROBOT, {'map_x': 1.0, 'map_y': 2.6})
        self.assertEqual((g['x'], g['y']), (1.0, 2.0))

    def test_parse_servo(self):
        self.assertEqual(sa.parse_servo('online via=uno_r4_i2c_hub cam1_us=1801 cam2_us=1501'), (1801, 1501))
        self.assertEqual(sa.parse_servo(None), (None, None))


if __name__ == '__main__':
    unittest.main()
