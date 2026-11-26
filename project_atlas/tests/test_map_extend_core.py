"""Add-only map extension (owner 2026-11-26: "the saved map is right, don't disturb it; add new places as I drive").
Pure; no ROS. Saved cells must never change; only unknown cells are filled from an aligned new SLAM piece."""
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import atlas_map_extend_core as ex  # noqa: E402

RES = 0.05
# World: room A (saved map) x[0,3] y[0,2.5]; corridor x[3,4] y[1,1.8]; room B (new) x[4,6.5] y[0,3]; wall 0.1 m.
ROOMS = [(0.0, 3.0, 0.0, 2.5), (3.0, 4.0, 1.0, 1.8), (4.0, 6.5, 0.0, 3.0)]
DOORS = [(2.9, 3.1, 1.1, 1.7), (3.9, 4.1, 1.1, 1.7)]          # gaps between the spaces


def world(x, y, rooms=ROOMS, doors=DOORS, extra_walls=()):
    """100 occupied / 0 free / -1 unknown for a world point."""
    for (x0, x1, y0, y1) in extra_walls:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return 100
    inside = [r for r in rooms if r[0] - 0.05 <= x <= r[1] + 0.05 and r[2] - 0.05 <= y <= r[3] + 0.05]
    if not inside:
        return -1
    for (x0, x1, y0, y1) in doors:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return 0
    for r in inside:
        if r[0] + 0.05 < x < r[1] - 0.05 and r[2] + 0.05 < y < r[3] - 0.05:
            return 0
    return 100


def make_grid(ox, oy, w_m, h_m, fn):
    W, H = int(round(w_m / RES)), int(round(h_m / RES))
    data = [0] * (W * H)
    for gy in range(H):
        for gx in range(W):
            data[gy * W + gx] = fn(ox + (gx + 0.5) * RES, oy + (gy + 0.5) * RES)
    return ex.Grid(W, H, RES, ox, oy, data)


def old_map():
    """Saved map: room A + the corridor's first half (the rest of the house is unknown)."""
    return make_grid(-0.5, -0.5, 4.0, 3.5, lambda x, y: world(x, y) if x <= 3.5 else -1)


def new_piece(T, extra_walls=(), rooms=ROOMS, doors=DOORS, seen=lambda x, y: x >= 2.0):
    """A SLAM piece in its own frame: new-frame point p maps to world as T(p). Sees x >= 2.0 (part of A + B)."""
    tx, ty, th = T
    c, s = math.cos(th), math.sin(th)

    def fn(px, py):
        wx, wy = tx + c * px - s * py, ty + s * px + c * py
        return world(wx, wy, rooms, doors, extra_walls) if seen(wx, wy) else -1
    # the new frame's grid must cover the seen world area after the inverse transform
    return make_grid(-3.5, -3.5, 8.0, 8.0, fn)


T_TRUE = (2.6, 0.9, math.radians(7.0))


class AlignTests(unittest.TestCase):
    def test_recovers_transform_from_rough_start(self):
        old, new = old_map(), new_piece(T_TRUE)
        init = (T_TRUE[0] + 0.2, T_TRUE[1] - 0.15, T_TRUE[2] + math.radians(4))
        T, match, overlap = ex.align(old, new, init)
        self.assertAlmostEqual(T[0], T_TRUE[0], delta=0.05)
        self.assertAlmostEqual(T[1], T_TRUE[1], delta=0.05)
        self.assertAlmostEqual(math.degrees(T[2]), 7.0, delta=1.0)
        self.assertGreater(match, 0.9)
        self.assertGreater(overlap, 100)


class MergeTests(unittest.TestCase):
    def test_saved_cells_never_change_and_new_room_is_added(self):
        old, new = old_map(), new_piece(T_TRUE)
        r = ex.evaluate(old, new, (T_TRUE[0] + 0.1, T_TRUE[1] + 0.1, T_TRUE[2] - math.radians(2)))
        self.assertTrue(r['ok'], r['failures'])
        g, s = r['grid'], r['stats']
        self.assertEqual(s['saved_cells_changed'], 0)
        dx = int(round((old.ox - g.ox) / RES))
        dy = int(round((old.oy - g.oy) / RES))
        for gy in range(old.h):                      # bit-exact copy of every saved cell, known or unknown-filled
            for gx in range(old.w):
                v = old.data[gy * old.w + gx]
                if v != -1:
                    self.assertEqual(g.data[(gy + dy) * g.w + gx + dx], v)
        self.assertEqual(g.value_at(5.2, 1.5), 0)    # room B floor
        self.assertEqual(g.value_at(6.5, 1.5), 100)  # room B far wall
        self.assertAlmostEqual(s['added_free_m2'], 2.4 * 2.9 + 0.5 * 0.7, delta=1.5)
        self.assertGreaterEqual(s['contact_cells'], 5)

    def test_output_grows_to_hold_the_new_area(self):
        old, new = old_map(), new_piece(T_TRUE)
        g = ex.evaluate(old, new, T_TRUE)['grid']
        self.assertGreater(g.ox + g.w * RES, 6.5)
        self.assertAlmostEqual((old.ox - g.ox) / RES, round((old.ox - g.ox) / RES), places=6)   # whole-cell shift
        self.assertAlmostEqual((old.oy - g.oy) / RES, round((old.oy - g.oy) / RES), places=6)


class SafetyTests(unittest.TestCase):
    def test_bad_start_is_refused(self):
        old, new = old_map(), new_piece(T_TRUE)
        r = ex.evaluate(old, new, (T_TRUE[0] + 2.0, T_TRUE[1] - 1.5, T_TRUE[2] + math.radians(60)))
        self.assertFalse(r['ok'])
        self.assertTrue(any('does not line up' in f for f in r['failures']), r['failures'])

    def test_conflicting_new_walls_are_refused(self):
        """The new piece claims walls where the saved map is free (wrong alignment or a different place)."""
        old = old_map()
        walls = [(2.2 + 0.25 * k, 2.3 + 0.25 * k, 0.2, 2.3) for k in range(4)]   # 4 fake walls across room A
        new = new_piece(T_TRUE, extra_walls=walls)
        r = ex.evaluate(old, new, T_TRUE)
        self.assertFalse(r['ok'])
        self.assertTrue(any('disagrees with the saved map' in f for f in r['failures']), r['failures'])

    def test_disconnected_piece_is_refused(self):
        """No doorway between the saved map and the new room: the new area does not connect."""
        old = old_map()
        new = new_piece(T_TRUE, doors=[(2.9, 3.1, 1.1, 1.7)], seen=lambda x, y: x >= 2.0)
        r = ex.evaluate(old, new, T_TRUE)
        self.assertFalse(r['ok'])
        self.assertTrue(any('not connected' in f for f in r['failures']), r['failures'])

    def test_nothing_new_is_refused(self):
        old = old_map()
        new = new_piece(T_TRUE, seen=lambda x, y: 2.0 <= x <= 3.4)
        r = ex.evaluate(old, new, T_TRUE)
        self.assertFalse(r['ok'])
        self.assertTrue(any('nothing new' in f for f in r['failures']), r['failures'])

    def test_resolution_mismatch(self):
        old = old_map()
        new = ex.Grid(10, 10, 0.1, 0, 0, [0] * 100)
        with self.assertRaises(ValueError):
            ex.evaluate(old, new, (0, 0, 0))

    def test_failure_text_english(self):
        old, new = old_map(), new_piece(T_TRUE)
        r = ex.evaluate(old, new, (T_TRUE[0] + 2.0, T_TRUE[1] - 1.5, T_TRUE[2] + 1.0))
        for f in r['failures']:
            self.assertFalse(any('ऀ' <= ch <= 'ॿ' for ch in f), f)


class MapIoTests(unittest.TestCase):
    def test_roundtrip_and_205_is_unknown(self):
        g = old_map()
        with tempfile.TemporaryDirectory() as d:
            y = ex.write_map(g, Path(d) / 'm')
            g2 = ex.read_map(y)
        self.assertEqual((g2.w, g2.h, g2.res), (g.w, g.h, g.res))
        self.assertAlmostEqual(g2.ox, g.ox, places=6)
        self.assertEqual(g2.data, g.data)
        self.assertIn(-1, g2.data)


if __name__ == '__main__':
    unittest.main()
