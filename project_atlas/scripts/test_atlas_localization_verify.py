"""Startup-localization verification tests; no ROS, bag, network or motion.

Synthetic two-room map: an L-shaped "room A" and a rectangular "room B"
5 m apart, so a scan has one right answer. Covers the Hall cold-start
failure: a claimed (seeded) pose in the wrong room must never be VERIFIED.
"""
import ast
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

import numpy as np

import atlas_localization_verify_core as core

RES = 0.05


def write_map(d, walls, size=(12.0, 6.0), origin=(-1.0, -1.0)):
    w, h = int(size[0] / RES), int(size[1] / RES)
    img = np.full((h, w), 254, np.uint8)                 # free
    for (x0, y0, x1, y1) in walls:                         # occupied segments
        n = int(max(abs(x1 - x0), abs(y1 - y0)) / (RES / 2)) + 1
        for k in range(n + 1):
            x = x0 + (x1 - x0) * k / n
            y = y0 + (y1 - y0) * k / n
            c, r = int((x - origin[0]) / RES), int((y - origin[1]) / RES)
            if 0 <= c < w and 0 <= r < h:
                img[h - 1 - r, c] = 0
    pgm = Path(d) / 'm.pgm'
    pgm.write_bytes(b'P5\n%d %d\n255\n' % (w, h) + img.tobytes())
    yaml = Path(d) / 'm.yaml'
    yaml.write_text(f'image: m.pgm\nmode: trinary\nresolution: {RES}\norigin: [{origin[0]}, {origin[1]}, 0]\n'
                    'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
    return yaml


ROOM_A = [(0, 0, 3, 0), (3, 0, 3, 2), (3, 2, 1.5, 2), (1.5, 2, 1.5, 3.5), (1.5, 3.5, 0, 3.5), (0, 3.5, 0, 0),
          (0.6, 0.6, 1.0, 0.6)]                            # a small obstacle breaks symmetry
SYMMETRIC_B = [(6, 0, 10, 0), (10, 0, 10, 2.5), (10, 2.5, 6, 2.5), (6, 2.5, 6, 0)]
ROOM_B = SYMMETRIC_B + [(8.5, 0.0, 8.5, 0.8), (6, 1.6, 7.0, 1.6), (9.2, 2.5, 9.2, 2.0), (9.2, 2.0, 10, 2.0)]


def ray_scan(walls, pose, count=360, max_r=8.0):
    """Ranges seen from ``pose`` (laser at robot centre, no yaw offset)."""
    out = []
    for i in range(count):
        a = pose[2] - math.pi + i * 2 * math.pi / count
        dx, dy = math.cos(a), math.sin(a)
        best = float('inf')
        for (x0, y0, x1, y1) in walls:
            ex, ey = x1 - x0, y1 - y0
            den = dx * ey - dy * ex
            if abs(den) < 1e-12:
                continue
            t = ((x0 - pose[0]) * ey - (y0 - pose[1]) * ex) / den
            u = ((x0 - pose[0]) * dy - (y0 - pose[1]) * dx) / den
            if t > 0 and 0 <= u <= 1:
                best = min(best, t)
        out.append(best if best <= max_r else float('inf'))
    return -math.pi, 2 * math.pi / count, out


class VerifyCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.map = core.load_map(write_map(cls.tmp.name, ROOM_A + ROOM_B))
        cls.policy = core.VerifyPolicy()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def search(self, truth, walls=ROOM_A + ROOM_B, claimed=None):
        amin, inc, ranges = ray_scan(walls, truth)
        allp, held = core.endpoints(amin, inc, ranges, (0.0, 0.0, 0.0), self.policy)
        hyps = core.global_search(self.map, allp, held, self.policy)
        return core.decide(hyps, len(allp), claimed, self.policy)

    def test_finds_true_room_without_prior(self):
        truth = (8.0, 1.6, math.radians(-100))
        v = self.search(truth)
        self.assertEqual(v.state, 'VERIFIED', v.reason)
        self.assertLess(math.hypot(v.pose[0] - truth[0], v.pose[1] - truth[1]), 0.15)
        self.assertLess(abs(math.degrees(v.pose[2] - truth[2])), 4)

    def test_claim_in_wrong_room_is_unknown(self):
        # the saved "home" seed claims room A while ATLAS is parked in room B
        v = self.search((8.0, 1.6, math.radians(-100)), claimed=(0.8, 1.2, math.radians(77)))
        self.assertEqual(v.state, 'UNKNOWN')
        self.assertIn('disagrees', v.reason)
        self.assertIsNone(v.pose)

    def test_scan_not_on_map_is_unknown(self):
        # a place that is not in the saved map (e.g. furniture rearranged everywhere)
        other = [(-5, -5, 5, -5), (5, -5, 5, 5), (5, 5, -5, 5), (-5, 5, -5, -5)]
        amin, inc, ranges = ray_scan(other, (0.3, 0.2, 0.4))
        ranges = [r * 0.63 if math.isfinite(r) else r for r in ranges]
        allp, held = core.endpoints(amin, inc, ranges, (0, 0, 0), self.policy)
        v = core.decide(core.global_search(self.map, allp, held, self.policy), len(allp), None, self.policy)
        self.assertEqual(v.state, 'UNKNOWN')

    def test_symmetric_room_is_unknown(self):
        # a plain rectangle fits equally well rotated by 180 deg: refuse to guess
        sym = core.load_map(write_map(self.tmp.name, ROOM_A + SYMMETRIC_B))
        amin, inc, ranges = ray_scan(ROOM_A + SYMMETRIC_B, (7.5, 1.0, 0.3))
        allp, held = core.endpoints(amin, inc, ranges, (0, 0, 0), self.policy)
        v = core.decide(core.global_search(sym, allp, held, self.policy), len(allp), None, self.policy)
        self.assertEqual(v.state, 'UNKNOWN')
        self.assertIn('ambiguous', v.reason)

    def test_too_few_returns_is_unknown(self):
        v = core.decide([{'x': 0, 'y': 0, 'yaw': 0, 'fit_heldout': 1.0}], 10, None, self.policy)
        self.assertEqual(v.state, 'UNKNOWN')

    def test_ambiguous_places_are_unknown(self):
        hyps = [{'x': 0, 'y': 0, 'yaw': 0, 'fit_heldout': 0.97},
                {'x': 4, 'y': 0, 'yaw': 0, 'fit_heldout': 0.95}]
        v = core.decide(hyps, 300, None, self.policy)
        self.assertEqual(v.state, 'UNKNOWN')
        self.assertIn('ambiguous', v.reason)

    def test_low_fit_everywhere_is_unknown(self):
        hyps = [{'x': 0, 'y': 0, 'yaw': 0, 'fit_heldout': 0.90}]
        self.assertEqual(core.decide(hyps, 300, None, self.policy).state, 'UNKNOWN')

    def test_median_ignores_single_dropouts(self):
        rows = [[1.0, float('inf'), 2.0], [1.1, 3.0, float('nan')], [0.9, 3.1, 2.1]]
        out = core.median_ranges(rows)
        self.assertAlmostEqual(out[0], 1.0)
        self.assertAlmostEqual(out[1], 3.05)
        self.assertAlmostEqual(out[2], 2.05)

    def test_map_rows_are_bottom_up(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'm.pgm').write_bytes(b'P5\n3 2\n255\n' + bytes([0, 254, 254, 254, 254, 254]))
            (Path(d) / 'm.yaml').write_text('image: m.pgm\nresolution: 1.0\norigin: [10.0, 20.0, 0]\n'
                                            'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
            m = core.load_map(Path(d) / 'm.yaml')
            self.assertTrue(m['occupied'][1, 0])          # top-left pixel = top map row
            self.assertEqual(core.fit(m, np.array([[0.0, 0.0]]), 10.5, 21.5, 0.0, 0.1), 1.0)


class SeederTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).with_name('seed_atlas_localization.py').read_text()

    def test_default_mode_is_unchanged_saved_pose(self):
        self.assertIn('default=configured_seed_mode()', self.source)
        fn = next(n for n in ast.parse(self.source).body
                  if isinstance(n, ast.FunctionDef) and n.name == 'configured_seed_mode')
        with tempfile.TemporaryDirectory() as d:
            mode_file = Path(d) / 'seed_mode'
            env = {}
            scope = {}
            exec(compile(ast.Module(body=[fn], type_ignores=[]), 'seed', 'exec'),
                 {'os': NS(environ=env), 'SEED_MODE_FILE': mode_file}, scope)
            mode = scope['configured_seed_mode']
            self.assertEqual(mode(), 'saved')               # no file, no env
            mode_file.write_text('verify\n')
            self.assertEqual(mode(), 'verify')
            mode_file.write_text('anything-else')
            self.assertEqual(mode(), 'saved')               # unknown values fall back to unchanged behaviour
            env['ATLAS_SEED_MODE'] = 'verify'
            self.assertEqual(mode(), 'verify')

    def test_unknown_returns_before_any_seed_is_sent(self):
        tree = ast.parse(self.source)
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        text = ast.get_source_segment(self.source, main)
        unknown_return = text.index('return  # exit 0: an unverified start')
        self.assertLess(unknown_return, text.index('publisher.publish(message)'))
        self.assertLess(unknown_return, text.index('pose_client.call_async'))

    def test_dry_run_returns_before_any_seed_or_write(self):
        main = next(n for n in ast.parse(self.source).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        text = ast.get_source_segment(self.source, main)
        dry = text.index('if args.dry_run:')
        ret = text.index('return', dry)
        self.assertNotIn('write_verdict', text[dry:ret])
        self.assertLess(ret, text.index('pose_client.call_async'))

    def run_verify(self, verdicts):
        """verify_start_pose with stubbed scans/search returning ``verdicts`` in order."""
        import atlas_localization_verify_core as real
        seq = iter(verdicts)
        fake_core = NS(VerifyPolicy=real.VerifyPolicy, load_map=lambda p: None,
                       median_ranges=lambda rows: [], endpoints=lambda *a: ([], []),
                       global_search=lambda *a: None, decide=lambda *a: next(seq))
        import sys
        saved = sys.modules.get('atlas_localization_verify_core')
        sys.modules['atlas_localization_verify_core'] = fake_core
        try:
            fn = next(n for n in ast.parse(self.source).body
                      if isinstance(n, ast.FunctionDef) and n.name == 'verify_start_pose')
            scope = {}
            scan = NS(header=NS(frame_id='laser_frame'), angle_min=0, angle_increment=0, ranges=[])
            exec(compile(ast.Module(body=[fn], type_ignores=[]), 'seed', 'exec'),
                 {'Path': Path, 'hashlib': __import__('hashlib'), 'math': math, 'time': __import__('time'),
                  'VERIFY_ATTEMPTS': 3, 'VERIFY_BUDGET_S': 60.0,
                  'collect_parked_scans': lambda node: ([scan] * 6, None),
                  'laser_in_base': lambda node, frame: (0, 0, 0)}, scope)
            with tempfile.NamedTemporaryFile(suffix='.yaml') as f:
                return scope['verify_start_pose'](NS(), f.name)
        finally:
            if saved is not None:
                sys.modules['atlas_localization_verify_core'] = saved

    @staticmethod
    def verdict(state, x, y, yaw_deg, fit):
        hyp = {'x': x, 'y': y, 'yaw_deg': yaw_deg, 'fit_heldout': fit}
        return core.Verdict(state, (x, y, math.radians(yaw_deg)) if state == 'VERIFIED' else None,
                            'stub', fit, 0.1, [hyp])

    def test_retry_accepts_consistent_place(self):
        pose, rec = self.run_verify([self.verdict('UNKNOWN', 6.28, -2.08, -95, 0.92),
                                     self.verdict('VERIFIED', 6.24, -2.25, -96, 0.95)])
        self.assertEqual(rec['state'], 'VERIFIED')
        self.assertAlmostEqual(pose['x'], 6.24)
        self.assertEqual(len(rec['attempts']), 2)

    def test_retry_rejects_disagreeing_places(self):
        pose, rec = self.run_verify([self.verdict('UNKNOWN', 0.3, -1.2, 75, 0.91),
                                     self.verdict('VERIFIED', 6.24, -2.25, -96, 0.95)])
        self.assertIsNone(pose)
        self.assertEqual(rec['state'], 'UNKNOWN')
        self.assertIn('disagree', rec['reason'])

    def test_three_unknown_attempts_stay_unknown(self):
        pose, rec = self.run_verify([self.verdict('UNKNOWN', 6.28, -2.08, -95, 0.92)] * 3)
        self.assertIsNone(pose)
        self.assertEqual(len(rec['attempts']), 3)

    def test_verify_failure_is_unknown_not_saved_seed(self):
        scope = {}
        tree = ast.parse(self.source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verify_start_pose')
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'seed', 'exec'),
             {'Path': Path, 'hashlib': __import__('hashlib'), 'math': math, 'time': __import__('time'),
              'VERIFY_ATTEMPTS': 3, 'VERIFY_BUDGET_S': 60.0,
              'collect_parked_scans': lambda node: (None, 'rover moved while the startup scan was collected'),
              'laser_in_base': None}, scope)
        with tempfile.TemporaryDirectory() as d:
            pose, record = scope['verify_start_pose'](NS(), write_map(d, ROOM_A))
        self.assertIsNone(pose)
        self.assertEqual(record['state'], 'UNKNOWN')
        self.assertIn('moved', record['reason'])


class StatusVerdictTests(unittest.TestCase):
    def test_reader_marks_other_boot_and_handles_missing(self):
        source = Path(__file__).with_name('atlas_status_web.py').read_text()
        fn = next(n for n in ast.parse(source).body
                  if isinstance(n, ast.FunctionDef) and n.name == 'read_start_verdict')
        scope = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'web', 'exec'),
             {'Path': Path, 'json': json, 'time': __import__('time'), 'START_VERDICT_FILE': Path('/nonexistent')}, scope)
        read = scope['read_start_verdict']
        self.assertIsNone(read(100.0))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'v.json'
            p.write_text(json.dumps({'state': 'VERIFIED', 'boot_id': 'not-this-boot', 'written_unix': 90.0}))
            out = read(100.0, p)
            self.assertEqual(out['value']['state'], 'VERIFIED')
            self.assertFalse(out['value']['current_boot'])
            self.assertEqual(out['age'], 10.0)
            p.write_text('{broken')
            self.assertIsNone(read(100.0, p))


if __name__ == '__main__':
    unittest.main()
