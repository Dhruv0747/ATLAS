import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from atlas_map_waypoint import check_point, heading_towards

META = {'resolution': 0.05, 'origin': [0.0, 0.0, 0.0], 'occupied_thresh': 0.65, 'free_thresh': 0.25, 'negate': 0}


def room(w=60, h=40, wall_x=None, unknown=None):
    """free room (254) with a 1-cell occupied border (0); optional wall column / unknown patch (205)."""
    px = []
    for row in range(h):
        gy = h - 1 - row
        for gx in range(w):
            v = 254
            if gx in (0, w - 1) or gy in (0, h - 1) or gx == wall_x:
                v = 0
            if unknown and unknown[0] <= gx < unknown[1] and unknown[2] <= gy < unknown[3]:
                v = 205
            px.append(v)
    return (w, h, px)


class MapWaypointTests(unittest.TestCase):
    def test_open_centre_ok(self):
        self.assertIsNone(check_point(1.5, 1.0, room(), META))

    def test_outside_refused(self):
        self.assertIn('outside', check_point(-1, 1, room(), META))
        self.assertIn('outside', check_point(10, 1, room(), META))
        self.assertEqual(check_point(float('nan'), 1, room(), META), 'invalid point')

    def test_occupied_and_unknown_refused(self):
        self.assertIn('occupied', check_point(1.0, 1.0, room(wall_x=20), META))
        self.assertIn('unknown', check_point(1.0, 1.0, room(unknown=(18, 23, 18, 23)), META))

    def test_too_close_to_wall_refused(self):
        g = room(wall_x=30)                      # wall at x = 1.50-1.55 m
        self.assertIn('too close', check_point(1.30, 1.0, g, META))
        self.assertIsNone(check_point(1.05, 1.0, g, META))

    def test_rotated_origin(self):
        meta = dict(META, origin=[0.0, 0.0, math.pi / 2])
        self.assertIsNone(check_point(-1.0, 1.5, room(), meta))

    def test_heading(self):
        self.assertAlmostEqual(heading_towards((0, 0), (0, 1)), math.pi / 2)
        self.assertEqual(heading_towards((0, 0), (0.01, 0), 0.7), 0.7)


if __name__ == '__main__':
    unittest.main()
