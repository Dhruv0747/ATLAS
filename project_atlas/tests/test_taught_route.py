"""Taught route (2026-11-22): reversed route faces the new travel direction; route builder keeps clearance and
centres doorways. No ROS: mission control's helper is extracted from the source, the builder runs on a toy map."""
import ast
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools' / 'drive'))
import atlas_lidar_availability as la  # noqa: E402
import teach_route_build as trb  # noqa: E402


def load_reversed_route():
    src = (ROOT / 'scripts' / 'atlas_mission_control.py').read_text()
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'reversed_route')
    ns = {'math': math}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'mc', 'exec'), ns)
    return ns['reversed_route'], src


def corridor(width=0.8, length=4.0):
    """Free corridor along -y from (0, 0), walls at x = +-width/2, unknown elsewhere."""
    res, ox, oy, w, h = 0.05, -1.0, -length - 0.5, 40, int((length + 1.0) / 0.05)
    data = []
    for gy in range(h):
        for gx in range(w):
            x, y = ox + (gx + .5) * res, oy + (gy + .5) * res
            if abs(x) >= width / 2:
                data.append(100)
            elif -length <= y <= 0.4:
                data.append(0)
            else:
                data.append(-1)
    return la.OccGrid(w, h, res, ox, oy, data)


class ReversedRouteTests(unittest.TestCase):
    def test_reverse_flips_yaw_and_order(self):
        rev, _ = load_reversed_route()
        pts = [{'x': 0.0, 'y': 0.0, 'yaw': -math.pi / 2}, {'x': 0.0, 'y': -1.0, 'yaw': -math.pi / 2}]
        out = rev(pts)
        self.assertEqual([p['y'] for p in out], [-1.0, 0.0])
        for p in out:
            self.assertAlmostEqual(p['yaw'], math.pi / 2, places=6)
        self.assertEqual(pts[0]['yaw'], -math.pi / 2)          # input not modified

    def test_dispatch_uses_reversed_route_for_dhruv_room(self):
        _, src = load_reversed_route()
        self.assertIn('points = reversed_route(points)', src)
        self.assertNotIn('points = list(reversed(points))', src)


class BuilderTests(unittest.TestCase):
    def rows(self, x_offset):
        # owner drove 0.12 m off-centre with poor AMCL; the builder must centre the narrow corridor
        return [{'x': x_offset, 'y': -0.1 * i, 'yaw': -math.pi / 2, 'xy_std_m': 0.3, 'stop_latched': False}
                for i in range(30)]

    def test_narrow_corridor_is_centred_and_clear(self):
        g = corridor(width=0.8)
        wps = [trb.nudge(g, w) for w in trb.build(self.rows(0.12), g, narrow_m=1.4, step_m=0.25)]
        self.assertGreater(len(wps), 5)
        for w in wps:
            self.assertLess(abs(w['x']), 0.03, w)               # centred
            self.assertGreaterEqual(trb.min_clearance(g, w['x'], w['y'], w['yaw']), 0.05, w)

    def test_end_pose_cuts_wandering_and_sets_yaw(self):
        g = corridor(width=1.0)
        rows = self.rows(0.0) + [{'x': 0.0, 'y': -2.0 + 0.1 * i, 'yaw': math.pi / 2, 'xy_std_m': 0.1,
                                   'stop_latched': False} for i in range(5)]
        wps = trb.build(rows, g, end=(0.0, -2.0, -90.0))
        self.assertEqual((wps[-1]['x'], wps[-1]['y']), (0.0, -2.0))
        self.assertAlmostEqual(wps[-1]['yaw'], -math.pi / 2, places=3)
        self.assertTrue(all(w['y'] >= -2.0 - 1e-6 for w in wps))

    def test_latched_samples_dropped(self):
        g = corridor(width=1.0)
        rows = self.rows(0.0)
        for r in rows[10:]:
            r['stop_latched'] = True
        wps = trb.build(rows, g)
        self.assertTrue(all(w['y'] > -1.0 for w in wps))

    def test_pgm_loader_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            pgm = Path(d) / 'm.pgm'
            # 3x2 image, top row: free, occupied, unknown ; bottom row: occupied x3
            pgm.write_bytes(b'P5\n3 2\n255\n' + bytes([254, 0, 205, 0, 0, 0]))
            (Path(d) / 'm.yaml').write_text('image: m.pgm\nmode: trinary\nresolution: 0.05\n'
                                            'origin: [-1.0, -2.0, 0.0]\nnegate: 0\noccupied_thresh: 0.65\n'
                                            'free_thresh: 0.196\n')
            g, image = trb.load_map(Path(d) / 'm.yaml')
            self.assertEqual((g.w, g.h, g.res, g.ox, g.oy), (3, 2, 0.05, -1.0, -2.0))
            self.assertEqual(g.data, [100, 100, 100, 0, 100, -1])   # bottom row first


if __name__ == '__main__':
    unittest.main()
