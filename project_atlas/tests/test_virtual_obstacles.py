"""2026-11-16 owner-confirmed virtual obstacles (sofa / glass table / cabinet the LiDAR cannot see). Pure, no ROS."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import atlas_lidar_availability as ala  # noqa: E402
import atlas_virtual_obstacles as vo  # noqa: E402

CONFIG = Path(__file__).parents[1] / 'config' / 'virtual_obstacles.json'
HALL_PLACE = (1.68, -5.35)          # runtime named place 'hall' (moved to the hall centre 2026-11-16)


def free_grid(w=120, h=120, res=0.05, ox=-1.0, oy=-8.0):
    return ala.OccGrid(w, h, res, ox, oy, [0] * (w * h))


def dist_to_polygon(x, y, poly):
    best = float('inf')
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - x1 - t * dx, y - y1 - t * dy))
    return best


class ConfigTests(unittest.TestCase):
    def test_repo_config_loads_the_owner_objects(self):
        polys = vo.load_polygons(CONFIG)
        names = [n for n, _ in polys]
        self.assertEqual(len(polys), 4)   # 2026-11-22: + dark wood cabinet / open door left of the hall doorway
        self.assertTrue(any('sofa' in n for n in names))
        self.assertTrue(any('table' in n for n in names))
        self.assertTrue(any('doorway' in n for n in names))

    def test_doorway_route_stays_clear(self):
        # round-trip-6 AMCL path through the hall doorway (room -> hall); the doorway polygon keeps >= 0.6 m from it
        route = [(1.0, -0.8), (1.32, -1.76), (1.53, -2.15), (1.9, -2.6), (2.0, -3.0), (1.95, -3.6), (1.9, -4.2)]
        for name, poly in [p for p in vo.load_polygons(CONFIG) if 'doorway' in p[0]]:
            for pt in route:
                self.assertFalse(vo.point_in_polygon(*pt, poly), (name, pt))
                self.assertGreaterEqual(dist_to_polygon(*pt, poly), 0.6, (name, pt))

    def test_hall_place_stays_free_with_clearance(self):
        for name, poly in vo.load_polygons(CONFIG):
            self.assertFalse(vo.point_in_polygon(*HALL_PLACE, poly), name)
            self.assertGreaterEqual(dist_to_polygon(*HALL_PLACE, poly), 0.30, name)

    def test_bad_config_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'v.json'
            p.write_text(json.dumps({'obstacles': [{'polygon': [[0, 0], [1, 0]]}]}))
            with self.assertRaises(ValueError):
                vo.load_polygons(p)
            p.write_text(json.dumps({'obstacles': [{'polygon': [[0, 0], [1, 0], ['nan', 1]]}]}))
            with self.assertRaises(ValueError):
                vo.load_polygons(p)


class OverlayTests(unittest.TestCase):
    def test_marks_inside_only_and_never_clears(self):
        g = free_grid()
        g.data[0] = 100
        g.data[5] = -1
        poly = [('box', [(0.0, -6.0), (0.5, -6.0), (0.5, -5.5), (0.0, -5.5)])]
        data, marked = vo.overlay_data(g.w, g.h, g.res, g.ox, g.oy, g.data, poly)
        self.assertEqual(marked, 100)                  # 10 x 10 cells of 5 cm
        self.assertEqual(data[0], 100)
        self.assertEqual(data[5], -1)
        self.assertEqual(g.data.count(100), 1)         # input not modified
        gx, gy = int((0.25 - g.ox) / g.res), int((-5.75 - g.oy) / g.res)
        self.assertEqual(data[gy * g.w + gx], 100)
        gx2 = int((0.8 - g.ox) / g.res)
        self.assertEqual(data[gy * g.w + gx2], 0)

    def test_polygon_outside_map_is_clipped(self):
        g = free_grid(w=10, h=10, ox=0.0, oy=0.0)
        data, marked = vo.overlay_data(g.w, g.h, g.res, g.ox, g.oy, g.data,
                                       [('x', [(-5, -5), (0.1, -5), (0.1, 0.1), (-5, 0.1)])])
        self.assertEqual(marked, 4)
        self.assertEqual(len(data), 100)

    def test_guard_explains_gap_toward_virtual_sofa(self):
        """Hall attempt 8: goal blocked by an unexplained gap at front-right where the map was unknown/free but the
        black sofa stood. With the virtual sofa, that gap is a known wall at a safe distance."""
        g = free_grid()
        pose = (0.0, -4.0, -math.pi / 2)               # facing -y toward the sofa area
        # free map all the way: the ray leaves the grid -> not explainable
        self.assertEqual(ala.map_known_bins({0}, g, pose), set())
        sofa = [('sofa', [(-0.5, -5.5), (0.5, -5.5), (0.5, -4.9), (-0.5, -4.9)])]
        g2 = vo.overlay_grid(g, sofa)
        self.assertIsInstance(g2, ala.OccGrid)
        self.assertEqual(ala.map_known_bins({0}, g2, pose), {0})          # sofa ~0.85 m away
        close = vo.overlay_grid(g, [('sofa', [(-0.5, -4.3), (0.5, -4.3), (0.5, -4.2), (-0.5, -4.2)])])
        self.assertEqual(ala.map_known_bins({0}, close, pose), set())     # too close: still a veto


if __name__ == '__main__':
    unittest.main()
