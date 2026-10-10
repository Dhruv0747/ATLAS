"""Offline tests of the mission-start scan check; no ROS or actuators.

Core functions run directly. Mission-control methods are extracted from the
real source (as in test_atlas_mission_sparse_pose_contract.py) and run
against stubs.
"""
import ast
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

import atlas_scan_fit_core as core

HALF = 2.0  # square room, walls at +/-2 m


def room_points(step=0.05):
    pts = []
    n = int(round(2 * HALF / step))
    for i in range(n + 1):
        v = -HALF + i * step
        pts += [(v, -HALF), (v, HALF), (-HALF, v), (HALF, v)]
    return pts


def room_scan(pose, count=360):
    """Ranges seen from ``pose`` (laser at robot centre, same heading)."""
    ranges = []
    for i in range(count):
        a = pose[2] - math.pi + i * 2 * math.pi / count
        c, s = math.cos(a), math.sin(a)
        hits = []
        for wall, d in ((HALF, c), (-HALF, c)):
            if abs(d) > 1e-9:
                hits.append((wall - pose[0]) / d)
        for wall, d in ((HALF, s), (-HALF, s)):
            if abs(d) > 1e-9:
                hits.append((wall - pose[1]) / d)
        ranges.append(min(t for t in hits if t > 0))
    return NS(angle_min=-math.pi, angle_increment=2 * math.pi / count, ranges=ranges,
              range_min=0.15, range_max=12.0)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.index = core.OccupiedIndex(room_points(), 0.05)
        self.policy = core.ScanFitPolicy()

    def points(self, scan):
        return core.unused_beam_points(scan.angle_min, scan.angle_increment, scan.ranges,
                                       scan.range_min, scan.range_max, self.policy)

    def test_correct_pose_passes(self):
        pose = (0.3, -0.4, 0.7)
        r = core.evaluate(self.points(room_scan(pose)), pose, (0, 0, 0), self.index, 0.1)
        self.assertTrue(r.ok, r.reason)
        self.assertGreaterEqual(r.fit_fraction, 0.99)

    def test_half_metre_offset_is_refused(self):
        truth = (0.3, -0.4, 0.7)
        believed = (0.3 + 0.5 * math.cos(0.7), -0.4 + 0.5 * math.sin(0.7), 0.7)
        r = core.evaluate(self.points(room_scan(truth)), believed, (0, 0, 0), self.index, 0.1)
        self.assertFalse(r.ok)
        self.assertIn('may have been moved', r.reason)

    def test_heading_error_is_refused(self):
        truth = (0.0, 0.0, 0.3)
        r = core.evaluate(self.points(room_scan(truth)), (0, 0, 0.3 + math.radians(25)),
                          (0, 0, 0), self.index, 0.1)
        self.assertFalse(r.ok)

    def test_stale_missing_or_sparse_scan_refused(self):
        pts = self.points(room_scan((0, 0, 0)))
        self.assertIn('stale', core.evaluate(pts, (0, 0, 0), (0, 0, 0), self.index, 2.0).reason)
        self.assertIn('no LiDAR', core.evaluate(pts, (0, 0, 0), (0, 0, 0), self.index, None).reason)
        self.assertIn('too few', core.evaluate(pts[:10], (0, 0, 0), (0, 0, 0), self.index, 0.1).reason)

    def test_nonfinite_pose_refused(self):
        pts = self.points(room_scan((0, 0, 0)))
        self.assertFalse(core.evaluate(pts, (float('nan'), 0, 0), (0, 0, 0), self.index, 0.1).ok)

    def test_amcl_beams_excluded(self):
        scan = room_scan((0, 0, 0))
        pts = self.points(scan)
        self.assertEqual(len(pts), 360 - 60)  # AMCL samples every 6th of 360 beams

    def test_out_of_range_returns_skipped(self):
        scan = room_scan((0, 0, 0))
        scan.ranges[1] = float('inf')
        scan.ranges[2] = 0.1
        self.assertEqual(len(self.points(scan)), 360 - 60 - 2)

    def test_index_matches_brute_force_within_search(self):
        pts = room_points()
        for q in ((1.9, 0.05), (0.0, 0.0), (1.8, 1.8), (-1.95, -1.7)):
            brute = min(math.hypot(px - q[0], py - q[1]) for px, py in pts)
            got = self.index([q])[0]
            if brute <= 0.30:
                self.assertAlmostEqual(got, brute)
            else:
                self.assertGreater(got, 0.30)

    def test_pgm_rows_map_bottom_up(self):
        with tempfile.TemporaryDirectory() as d:
            yaml_path, pgm_path = Path(d, 'm.yaml'), Path(d, 'm.pgm')
            # 3 x 2 image; only the TOP-LEFT pixel occupied (value 0).
            pgm_path.write_bytes(b'P5\n3 2\n255\n' + bytes([0, 254, 254, 254, 254, 254]))
            yaml_path.write_text('image: m.pgm\nmode: trinary\nresolution: 1.0\n'
                                 'origin: [10.0, 20.0, 0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
            self.assertEqual(core.load_occupied_points(yaml_path, pgm_path), ((10.5, 21.5),))
            self.assertEqual(core.load_occupied_index(yaml_path, pgm_path)([(10.5, 21.5)]), [0.0])


class MissionIntegrationTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name('atlas_mission_control.py')
        self.source = path.read_text()
        names = {'update_latest_scan', 'require_scan_map_agreement'}
        methods = [n for n in ast.walk(ast.parse(self.source))
                   if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in methods}, names)
        self.clock = [100.0]
        scope = {'math': math, 'time': NS(monotonic=lambda: self.clock[0]),
                 'rclpy': NS(time=NS(Time=lambda: 0), duration=NS(Duration=lambda seconds: seconds)),
                 'unused_beam_points': core.unused_beam_points,
                 'evaluate_scan_fit': core.evaluate,
                 'LaserScan': object}
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), 'exec'), scope)
        self.messages = []
        self.pose = {'frame_id': 'map', 'x': 0.3, 'y': -0.4, 'qx': 0.0, 'qy': 0.0,
                     'qz': math.sin(0.35), 'qw': math.cos(0.35)}
        laser = NS(transform=NS(translation=NS(x=0.0, y=0.0), rotation=NS(x=0, y=0, z=0, w=1)))
        self.node = NS(scan_fit_gate_enabled=True, scan_fit_policy=core.ScanFitPolicy(),
                       latest_scan=None, latest_scan_received_at=None,
                       active_mapping_session=lambda: None,
                       current_pose=lambda: dict(self.pose),
                       tf_buffer=NS(lookup_transform=lambda *a, **k: laser),
                       scan_fit_map_index=lambda: core.OccupiedIndex(room_points(), 0.05),
                       status=self.messages.append)
        self.receive = lambda msg: scope['update_latest_scan'](self.node, msg)
        self.check = lambda: scope['require_scan_map_agreement'](self.node)

    def test_fresh_matching_scan_passes_and_reports(self):
        self.receive(room_scan((0.3, -0.4, 0.7)))
        self.clock[0] += 0.2
        self.check()
        self.assertTrue(self.messages and self.messages[-1].startswith('SCAN CHECK OK'))

    def test_moved_robot_is_refused(self):
        self.receive(room_scan((0.3 - 0.5 * math.cos(0.7), -0.4 - 0.5 * math.sin(0.7), 0.7)))
        with self.assertRaisesRegex(RuntimeError, 'navigation blocked'):
            self.check()

    def test_no_scan_and_stale_scan_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'no LiDAR'):
            self.check()
        self.receive(room_scan((0.3, -0.4, 0.7)))
        self.clock[0] += 5.0
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            self.check()

    def test_tf_failure_refused(self):
        self.receive(room_scan((0.3, -0.4, 0.7)))

        def fail(*a, **k):
            raise RuntimeError('no transform')
        self.node.tf_buffer = NS(lookup_transform=fail)
        with self.assertRaisesRegex(RuntimeError, 'scan check blocked'):
            self.check()

    def test_non_map_frame_refused(self):
        self.pose['frame_id'] = 'odom'
        with self.assertRaisesRegex(RuntimeError, 'no map-frame pose'):
            self.check()

    def test_disabled_or_mapping_session_skips(self):
        self.node.scan_fit_gate_enabled = False
        self.check()
        self.node.scan_fit_gate_enabled = True
        self.node.active_mapping_session = lambda: {'id': 'x'}
        self.check()

    def test_every_saved_map_dispatch_calls_the_check(self):
        pair = ('self.require_known_saved_map_start()\n'
                '        self.require_scan_map_agreement()')
        self.assertEqual(self.source.count('self.require_known_saved_map_start()\n'), 3)
        self.assertEqual(self.source.count(pair), 3)


if __name__ == '__main__':
    unittest.main()
